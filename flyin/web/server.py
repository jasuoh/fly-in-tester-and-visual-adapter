"""``flyin web``: the tester in the browser, on http://127.0.0.1:8042.

Only the standard library is used. The page talks to a small JSON API:

    GET  /api/state             settings, groups, last test, running test
    GET  /api/maps              every map with its target and last result
    GET  /api/map?name=M        the map itself (zones, connections, bound)
    GET  /api/solution?name=M&which=last|previous   a saved solution
    POST /api/run     {name}    run your program on one map, replay it
    POST /api/check   {name, output}                replay a pasted output
    POST /api/test    {only}    start a test (all, groups, some maps)
    GET  /api/test              progress and results of that test
    POST /api/test/stop         stop it after the maps already running
    POST /api/config  {...}     save the settings
    GET  /api/detect?project=P  guess the command of a project
    POST /api/import  {folder}  import the subject's maps
    GET  /api/history           earlier test runs
    GET  /api/rules             RULES.md
    GET  /api/report            evaluation report of the last test (.md)

The server listens on 127.0.0.1 only. Because it runs the command you
configured, every API call must carry the session token of the page
(``X-Flyin-Token``) and a localhost ``Host``: another website open in the
same browser can neither read the page's token nor send that header
without a CORS preflight, which this server never allows.
"""

import json
import secrets
import threading
import time
import webbrowser
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from flyin import api, config, report, subject
from flyin.config import Config
from flyin.tester.bounds import lower_bound
from flyin.tester.cli import score_line
from flyin.tester.mapfile import MapError, read_map, shortest_cost
from flyin.tester.runner import (
    DEFAULT_GROUPS, FAIL, GROUP_ORDER, PASS, WARN, Case, Outcome, Runner,
)
from flyin.tester.targets import SUBJECT_VERSION, TOLERANCE
from flyin.visual.replay import build_replay

STATIC = Path(__file__).resolve().parent / "static"
# the fonts of the pygame visualizer (Geist, OFL), so the page works offline
FONTS = Path(__file__).resolve().parent.parent / "visual" / "assets" / "fonts"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript",
         ".css": "text/css", ".svg": "image/svg+xml", ".ttf": "font/ttf"}
MAX_BODY = 8 * 1024 * 1024
LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")


class WebError(Exception):
    """A request that cannot be answered; becomes a JSON error."""

    def __init__(self, message: str,
                 status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        """Remember the message and the HTTP status."""
        super().__init__(message)
        self.status = status


def case_json(case: Case) -> dict[str, Any]:
    """Return what the page needs to know about a map of the manifest."""
    return {"name": case.name, "group": case.group, "expect": case.expect,
            "target": case.target, "optimum": case.optimum,
            "optional": case.optional_target,
            "required": case.target_required, "level": case.level,
            "note": case.note}


def outcome_json(outcome: Outcome) -> dict[str, Any]:
    """Return one test result as JSON."""
    return {"map": outcome.case.name, "group": outcome.case.group,
            "expect": outcome.case.expect, "status": outcome.status,
            "message": outcome.message, "turns": outcome.turns,
            "best": outcome.best, "target": outcome.case.target,
            "optimum": outcome.case.optimum,
            "required": outcome.case.target_required,
            "optional": outcome.case.optional_target,
            "seconds": round(outcome.seconds, 2),
            "details": list(outcome.details)}


def map_json(case: Case) -> dict[str, Any]:
    """Return a map for drawing, or only its text if it cannot be read
    (maps that must be rejected)."""
    try:
        text = case.path.read_text("utf-8", errors="replace")
    except OSError as error:
        raise WebError(f"cannot read {case.name}: {error}") from error
    data: dict[str, Any] = {"case": case_json(case), "text": text[:200000]}
    try:
        fly_map = read_map(case.path)
    except (MapError, OSError, KeyError, ValueError) as error:
        data["error"] = str(error)
        return data
    data.update(
        nb_drones=fly_map.nb_drones, start=fly_map.start, end=fly_map.end,
        zones=[{"name": z.name, "x": z.x, "y": z.y, "kind": z.kind,
                "max": z.max_drones, "color": z.color}
               for z in fly_map.zones.values()],
        links=[{"a": link.a, "b": link.b, "cap": link.capacity}
               for link in fly_map.links.values()],
        shortest=shortest_cost(fly_map),
    )
    if case.expect == "solve" and fly_map.zones:
        try:
            data["bound"] = lower_bound(fly_map)
        except (KeyError, ValueError):
            data["bound"] = None
    return data


def replay_json(case: Case, text: str) -> dict[str, Any]:
    """Check an output and turn it into moves the page can play.

    ``moves[t]`` lists ``[drone, place]`` for turn ``t + 1``; a place is a
    zone name, or ``"a>b"`` while the drone flies from ``a`` to the
    restricted zone ``b``. Every drone starts in the start zone. Only the
    moves are sent (not every drone in every turn), so 10 000 drones stay
    small; the page rebuilds the positions.
    """
    try:
        fly_map = read_map(case.path)
    except (MapError, OSError, KeyError, ValueError) as error:
        raise WebError(f"the tester cannot read this map: {error}") \
            from error
    replay = build_replay(fly_map, text)
    moves = []
    for record in replay.result.turns:
        turn = []
        for move in record.moves:
            origin, dash, target = move.target.partition("-")
            turn.append([move.drone_id,
                         f"{origin}>{target}" if dash else origin])
        moves.append(turn)
    return {
        "valid": replay.valid, "turns": replay.check.turns,
        "moves_count": replay.check.moves, "id_base": replay.result.id_base,
        "drones": fly_map.nb_drones,
        "errors": replay.check.errors, "skipped": replay.skipped[:30],
        "issues": [{"turn": i.turn, "message": i.message,
                    "zones": list(i.zones),
                    "link": list(i.link) if i.link else None}
                   for i in replay.check.issues],
        "moves": moves,
    }


class TestJob:
    """A test run in the background, readable while it runs."""

    def __init__(self, cfg: Config, cases: list[Case]) -> None:
        """Prepare the run; :meth:`start` begins it."""
        self.cfg = cfg
        self.cases = cases
        self.results: dict[str, Outcome] = {}
        self.started = time.time()
        self.finished: float | None = None
        self.stopped = False
        self.error = ""
        self._lock = threading.Lock()

    def start(self) -> None:
        """Run the maps in a background thread."""
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self) -> None:
        """Skip the maps that have not started yet."""
        self.stopped = True

    @property
    def running(self) -> bool:
        """Return True while maps are still being tested."""
        return self.finished is None

    def _one(self, runner: Runner, case: Case) -> None:
        """Test one map unless the run was stopped."""
        if self.stopped:
            return
        outcome = runner.run_case(case)
        with self._lock:
            self.results[case.name] = outcome

    def _run(self) -> None:
        """Test every map, then remember the run like ``flyin test``."""
        cfg = self.cfg
        runner = Runner(cfg.command, timeout=cfg.timeout, cwd=cfg.project,
                        output_file=cfg.output_file)
        jobs = 1 if cfg.output_file else max(1, cfg.jobs)
        try:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                list(pool.map(lambda c: self._one(runner, c), self.cases))
            outcomes = self.outcomes()
            if outcomes and not self.stopped:
                config.save_run(outcomes)
        except Exception as error:  # keep the server alive, show it
            self.error = f"{type(error).__name__}: {error}"
        finally:
            self.finished = time.time()

    def outcomes(self) -> list[Outcome]:
        """Return the results so far, in manifest order."""
        with self._lock:
            return [self.results[c.name] for c in self.cases
                    if c.name in self.results]

    def to_json(self) -> dict[str, Any]:
        """Return the progress and the results so far."""
        outcomes = self.outcomes()
        counts = Counter(o.status for o in outcomes)
        end = self.finished or time.time()
        return {"running": self.running, "stopped": self.stopped,
                "error": self.error, "total": len(self.cases),
                "done": len(outcomes), "seconds": round(end - self.started),
                "counts": {s: counts[s] for s in (PASS, WARN, FAIL)},
                "score": score_line(outcomes),
                "checklist": [{"ok": ok, "label": label, "detail": detail}
                              for ok, label, detail
                              in report.checklist(outcomes)],
                "results": [outcome_json(o) for o in outcomes]}


class App:
    """The state behind the API: settings and the current test."""

    def __init__(self) -> None:
        """Start without a test."""
        self.token = secrets.token_urlsafe(24)
        self.job: TestJob | None = None
        self._lock = threading.Lock()

    # helpers ----------------------------------------------------------

    @staticmethod
    def cfg() -> Config:
        """Return the settings, or fail with a hint to set them."""
        current = config.load()
        if current is None:
            raise WebError("flyin is not set up yet: open Settings and "
                           "enter your project and its command",
                           HTTPStatus.CONFLICT)
        return current

    @staticmethod
    def case(name: str) -> Case:
        """Return the manifest map called ``name``."""
        for case in api.maps():
            if case.name == name:
                return case
        raise WebError(f"no map {name!r}", HTTPStatus.NOT_FOUND)

    # GET ----------------------------------------------------------------

    def state(self) -> dict[str, Any]:
        """Return the settings, the groups and a summary of the last test."""
        cfg = config.load()
        cases = api.maps()
        counts = Counter(c.group for c in cases)
        last = config.last_run()
        statuses = Counter(r.get("status") for r in last)
        runs = config.history()
        return {
            "config": asdict(cfg) if cfg else None,
            "cwd": str(Path.cwd()),
            "subject": {"version": SUBJECT_VERSION, "tolerance": TOLERANCE,
                        "imported": subject.imported()},
            "groups": [{"name": g, "count": counts[g],
                        "default": g in DEFAULT_GROUPS}
                       for g in GROUP_ORDER if counts[g]],
            "last": {"time": runs[-1]["time"] if runs else None,
                     "counts": {s: statuses[s] for s in (PASS, WARN, FAIL)},
                     "maps": len(last)},
            "running": bool(self.job and self.job.running),
        }

    def maps(self) -> list[dict[str, Any]]:
        """Return every map with the result of the last test."""
        last = {r.get("map"): r for r in config.last_run()}
        live = {o.case.name: o for o in self.job.outcomes()} \
            if self.job else {}
        rows = []
        for case in api.maps():
            row = case_json(case)
            if case.name in live:
                outcome = live[case.name]
                row.update(status=outcome.status, message=outcome.message,
                           turns=outcome.turns, best=outcome.best)
            elif case.name in last:
                record = last[case.name]
                row.update(status=record.get("status"),
                           message=record.get("message"),
                           turns=record.get("turns"),
                           best=record.get("best"))
            rows.append(row)
        return rows

    def solution(self, name: str, which: str) -> dict[str, Any]:
        """Replay the output of ``name`` saved by the last tests."""
        case = self.case(name)
        path = config.saved_output(name, which)
        if path is None:
            raise WebError(f"no saved output of the {which} test for this "
                           "map", HTTPStatus.NOT_FOUND)
        text = path.read_text("utf-8", errors="replace")
        return {"output": text, "replay": replay_json(case, text)}

    def history(self) -> list[dict[str, Any]]:
        """Return the earlier runs, newest first, as counts."""
        rows = []
        for run in reversed(config.history()):
            results = run.get("results", {})
            counts = Counter(v[0] for v in results.values()
                             if isinstance(v, list) and v)
            rows.append({"time": run.get("time"), "maps": len(results),
                         "counts": {s: counts[s] for s in
                                    (PASS, WARN, FAIL)},
                         "results": results})
        return rows

    def test_report(self) -> str:
        """Return the evaluation report of the current or last test."""
        if self.job is None or not self.job.outcomes():
            raise WebError("run a test first: the report is built from "
                           "its results", HTTPStatus.CONFLICT)
        cfg = self.cfg()
        return report.build(self.job.outcomes(), cfg.project, cfg.command)

    # POST ---------------------------------------------------------------

    def run_one(self, name: str) -> dict[str, Any]:
        """Run the program on one map and replay what it printed."""
        cfg = self.cfg()
        case = self.case(name)
        outcome = Runner(cfg.command, timeout=cfg.timeout, cwd=cfg.project,
                         output_file=cfg.output_file).run_case(case)
        data: dict[str, Any] = {"outcome": outcome_json(outcome),
                                "output": outcome.output}
        if case.expect == "solve" and outcome.output.strip():
            data["replay"] = replay_json(case, outcome.output)
        return data

    def check(self, name: str, output: str) -> dict[str, Any]:
        """Replay an output the user pasted."""
        return {"output": output,
                "replay": replay_json(self.case(name), output)}

    def start_test(self, only: list[str] | None) -> dict[str, Any]:
        """Start testing all default maps, some groups or some maps."""
        cfg = self.cfg()
        with self._lock:
            if self.job and self.job.running:
                raise WebError("a test is already running",
                               HTTPStatus.CONFLICT)
            cases = api.maps()
            if only:
                wanted = set(only)
                cases = [c for c in cases
                         if c.name in wanted or c.group in wanted]
            else:
                cases = [c for c in cases if c.group in DEFAULT_GROUPS]
            if not cases:
                raise WebError("no map selected")
            self.job = TestJob(cfg, cases)
            self.job.start()
        return self.job.to_json()

    def test_status(self) -> dict[str, Any]:
        """Return the progress of the current test (or that there is
        none)."""
        if self.job is not None:
            return self.job.to_json()
        # No test in this session yet: show the last one (also from the
        # menu or the command line), rebuilt from last_run.json.
        cases = {c.name: c for c in api.maps()}
        outcomes = [Outcome(cases[r["map"]], str(r.get("status")),
                            str(r.get("message", "")), turns=r.get("turns"),
                            bound=r.get("best"))
                    for r in config.last_run() if r.get("map") in cases
                    and r.get("status") in (PASS, WARN, FAIL)]
        counts = Counter(o.status for o in outcomes)
        runs = config.history()
        return {"running": False, "from_last": True, "total": 0, "done": 0,
                "time": runs[-1]["time"] if runs else None,
                "counts": {s: counts[s] for s in (PASS, WARN, FAIL)},
                "score": score_line(outcomes),
                "checklist": [{"ok": ok, "label": label, "detail": detail}
                              for ok, label, detail
                              in report.checklist(outcomes)]
                if outcomes else [],
                "results": [outcome_json(o) for o in outcomes]}

    def stop_test(self) -> dict[str, Any]:
        """Stop the current test."""
        if self.job is not None:
            self.job.stop()
        return self.test_status()

    @staticmethod
    def save_config(body: dict[str, Any]) -> dict[str, Any]:
        """Check and store the settings."""
        project = Path(str(body.get("project", "")).strip()).expanduser()
        command = str(body.get("command", "")).strip()
        if not project.is_dir():
            raise WebError(f"no folder {str(project)!r}")
        if not command:
            raise WebError("the command is empty")
        if "{map}" not in command:
            raise WebError("the command needs {map} where the map path "
                           "goes, e.g. python3 main.py {map}")
        old = config.load()
        try:
            timeout = float(body.get("timeout", old.timeout if old else 30))
            jobs = int(body.get("jobs", old.jobs if old else 4))
        except (TypeError, ValueError) as error:
            raise WebError("seconds per map and maps in parallel must be "
                           "numbers") from error
        cfg = Config(project=str(project.resolve()), command=command,
                     theme=old.theme if old else "mission",
                     timeout=max(1.0, timeout), jobs=max(1, min(jobs, 32)),
                     output_file=str(body.get("output_file", "")).strip())
        config.save(cfg)
        return asdict(cfg)

    @staticmethod
    def detect(project: str) -> dict[str, Any]:
        """Guess the command of a project and whether it has maps."""
        folder = Path(project).expanduser()
        if not folder.is_dir():
            raise WebError(f"no folder {project!r}")
        maps = folder / "maps"
        return {"command": config.detect_command(folder),
                "maps_folder": str(maps) if maps.is_dir() else None,
                "maps": len(subject.find_maps(maps))}

    def import_maps(self, folder: str) -> dict[str, Any]:
        """Import the subject's maps from ``folder`` (default: the
        project's ``maps/``)."""
        source = Path(folder).expanduser() if folder else \
            Path(self.cfg().project) / "maps"
        if not subject.find_maps(source):
            raise WebError(f"no .txt maps below {str(source)!r}")
        count, with_target = subject.import_maps(source)
        return {"imported": count, "with_target": with_target}


class Handler(BaseHTTPRequestHandler):
    """Serves the page, its files and the JSON API."""

    app: App
    server_version = "flyin"

    def log_message(self, format: str, *args: Any) -> None:
        """Keep the terminal quiet (errors still show in the page)."""

    # plumbing -----------------------------------------------------------

    def _send(self, status: int, body: bytes, kind: str) -> None:
        """Write one response."""
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: Any, status: int = 200) -> None:
        """Write a JSON response."""
        self._send(status, json.dumps(data).encode(), "application/json")

    def _local(self) -> bool:
        """Return True if the Host header names this computer (guards
        against DNS rebinding)."""
        host = self.headers.get("Host", "")
        name = host.rsplit(":", 1)[0] if not host.startswith("[") \
            else host.split("]")[0] + "]"
        return name in LOCAL_HOSTS

    def _authorized(self) -> bool:
        """Return True for API calls made by the page itself."""
        token = self.headers.get("X-Flyin-Token", "")
        return self._local() and secrets.compare_digest(token,
                                                        self.app.token)

    def _body(self) -> dict[str, Any]:
        """Return the JSON body of a POST."""
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise WebError("request too large")
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError as error:
            raise WebError("the request is not JSON") from error
        if not isinstance(data, dict):
            raise WebError("the request is not a JSON object")
        return data

    def _api(self, method: str, path: str, query: dict[str, str]) -> None:
        """Answer one API call."""
        app = self.app
        if not self._authorized():
            self._json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
            return
        try:
            if method == "GET":
                data: Any = self._get(app, path, query)
            else:
                data = self._post(app, path, self._body())
        except WebError as error:
            self._json({"error": str(error)}, error.status)
            return
        except Exception as error:  # one broken call must not stop it
            self._json({"error": f"{type(error).__name__}: {error}"},
                       HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if isinstance(data, str):
            self._send(200, data.encode(), "text/markdown; charset=utf-8")
        else:
            self._json(data)

    @staticmethod
    def _get(app: App, path: str, query: dict[str, str]) -> Any:
        """Dispatch a GET of the API."""
        if path == "/api/state":
            return app.state()
        if path == "/api/maps":
            return app.maps()
        if path == "/api/map":
            return map_json(app.case(query.get("name", "")))
        if path == "/api/solution":
            return app.solution(query.get("name", ""),
                                "previous" if query.get("which") ==
                                "previous" else "last")
        if path == "/api/test":
            return app.test_status()
        if path == "/api/detect":
            return app.detect(query.get("project", ""))
        if path == "/api/history":
            return app.history()
        if path == "/api/rules":
            return (Path(subject.__file__).parent / "RULES.md") \
                .read_text("utf-8")
        if path == "/api/report":
            return app.test_report()
        raise WebError("unknown API call", HTTPStatus.NOT_FOUND)

    @staticmethod
    def _post(app: App, path: str, body: dict[str, Any]) -> Any:
        """Dispatch a POST of the API."""
        if path == "/api/run":
            return app.run_one(str(body.get("name", "")))
        if path == "/api/check":
            return app.check(str(body.get("name", "")),
                             str(body.get("output", "")))
        if path == "/api/test":
            only = body.get("only")
            return app.start_test([str(x) for x in only]
                                  if isinstance(only, list) else None)
        if path == "/api/test/stop":
            return app.stop_test()
        if path == "/api/config":
            return app.save_config(body)
        if path == "/api/import":
            return app.import_maps(str(body.get("folder", "")))
        raise WebError("unknown API call", HTTPStatus.NOT_FOUND)

    def _static(self, path: str) -> None:
        """Serve the page (with the session token) or one of its files."""
        if not self._local():
            self._send(HTTPStatus.FORBIDDEN, b"forbidden", "text/plain")
            return
        base = STATIC
        if path.startswith("/fonts/"):
            base, name = FONTS, path.removeprefix("/fonts/")
        else:
            name = "index.html" if path in ("/", "/index.html") else \
                path.removeprefix("/static/")
        file = (base / name).resolve()
        if not file.is_relative_to(base) or not file.is_file() or \
                file.suffix not in TYPES:
            self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
            return
        body = file.read_bytes()
        if file.name == "index.html":
            body = body.replace(b"__FLYIN_TOKEN__", self.app.token.encode())
        self._send(200, body, TYPES[file.suffix])

    # HTTP methods -------------------------------------------------------

    def do_GET(self) -> None:
        """Answer a GET."""
        url = urlparse(self.path)
        if url.path.startswith("/api/"):
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            self._api("GET", url.path, query)
        else:
            self._static(url.path)

    def do_POST(self) -> None:
        """Answer a POST (API only)."""
        url = urlparse(self.path)
        if not url.path.startswith("/api/"):
            self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
            return
        try:
            self._api("POST", url.path, {})
        except WebError as error:
            self._json({"error": str(error)}, error.status)


def make_server(port: int = 8042) -> ThreadingHTTPServer:
    """Return the server on 127.0.0.1 (port 0: any free port)."""
    handler = type("FlyinHandler", (Handler,), {"app": App()})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(port: int = 8042, open_browser: bool = True) -> int:
    """Run the web GUI until Ctrl-C."""
    try:
        server = make_server(port)
    except OSError as error:
        print(f"cannot listen on 127.0.0.1:{port}: {error} "
              "(another flyin web? try --port 8043)")
        return 1
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"flyin web GUI: {url}   (Ctrl-C stops it)")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0
