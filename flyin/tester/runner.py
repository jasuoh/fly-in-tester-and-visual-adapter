"""Run a program on the maps of the manifest and judge its behaviour."""

import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .checker import check_solution
from .bounds import lower_bound
from .mapfile import MapError, read_map

MAPS_DIR = Path(__file__).resolve().parent.parent / "maps"
TURN_LINE = re.compile(r"^D\d+-\S+(?: D\d+-\S+)*$")
TRACEBACK = re.compile(r"Traceback \(most recent call last\)")

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
GROUP_ORDER = ("subject", "subject-invalid", "extra", "extra-invalid",
               "edge-valid", "edge-invalid", "challenge", "fuzz")
# Groups a plain "test everything" runs; fuzz (300 maps) only on request.
DEFAULT_GROUPS = GROUP_ORDER[:-1]
# The subject's own maps are not shipped; ``flyin import-maps`` copies
# them from your project into this folder (relative to where flyin runs).
LOCAL_MAPS = Path(".flyin") / "maps"


@dataclass(frozen=True)
class Case:
    """One map of the manifest with the behaviour that is expected."""

    path: Path
    name: str
    group: str
    expect: str
    target: int | None = None
    optional_target: bool = False
    lines: tuple[int, ...] = ()
    level: str = "required"
    note: str = ""
    prefer_visit: tuple[str, ...] = ()
    optimum: int | None = None


@dataclass
class Outcome:
    """The verdict for one case."""

    case: Case
    status: str
    message: str
    turns: int | None = None
    seconds: float = 0.0
    details: tuple[str, ...] = ()
    output: str = ""
    bound: int | None = None

    @property
    def best(self) -> int | None:
        """Return the best possible turns: the optimum if known, else the
        lower bound (None for maps that must be rejected)."""
        return self.case.optimum or self.bound


def load_manifest(maps_dir: Path = MAPS_DIR) -> list[Case]:
    """Load every case described in ``maps_dir/manifest.json``.

    For the bundled maps this also adds the subject maps imported into
    ``.flyin/maps/`` of the current folder, if there are any.
    """
    cases = _read_manifest(maps_dir)
    local = Path.cwd() / LOCAL_MAPS
    if maps_dir == MAPS_DIR and (local / "manifest.json").is_file():
        cases += _read_manifest(local)
    order = {group: i for i, group in enumerate(GROUP_ORDER)}
    return sorted(cases, key=lambda case: order.get(case.group, len(order)))


def _read_manifest(maps_dir: Path) -> list[Case]:
    """Read one manifest; paths are relative to its folder."""
    try:
        data = json.loads((maps_dir / "manifest.json").read_text("utf-8"))
    except (OSError, ValueError):
        return []
    cases = []
    for entry in data.get("maps", []):
        line = entry.get("line", [])
        lines = tuple(line if isinstance(line, list) else [line])
        cases.append(Case(
            path=maps_dir / entry["path"],
            name=entry["path"],
            group=entry["group"],
            expect=entry["expect"],
            target=entry.get("target"),
            optional_target=entry.get("optional_target", False),
            lines=lines,
            level=entry.get("level", "required"),
            note=entry.get("note", ""),
            prefer_visit=tuple(entry.get("prefer_visit", [])),
            optimum=entry.get("optimum"),
        ))
    return cases


def last_line(text: str) -> str:
    """Return the last non-empty line of ``text`` (a traceback's cause)."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def extract_turns(text: str) -> tuple[list[str], list[str]]:
    """Split program output into turn lines and other (noise) lines."""
    turns, noise = [], []
    for line in text.splitlines():
        stripped = line.strip()
        if TURN_LINE.match(stripped):
            turns.append(stripped)
        elif stripped:
            noise.append(stripped)
    return turns, noise


class Runner:
    """Runs the command under test and turns its behaviour into outcomes."""

    def __init__(
        self,
        command: str,
        timeout: float = 60.0,
        cwd: str | None = None,
        source: str = "stdout",
        shell: bool = False,
        check_lines: bool = True,
        strict_output: bool = False,
        strict_targets: bool = False,
        output_file: str = "",
    ) -> None:
        """Configure the runner.

        ``command`` may contain ``{map}`` (path of the map) and ``{out}``
        (path of an output file the program should write). When ``{out}``
        is used, or ``source`` is ``"file"``, the solution is read from that
        file instead of from the terminal. ``output_file`` is for programs
        that always write the same file (relative to ``cwd``): it is
        removed before and read after every run, so run maps one by one.
        """
        self.command = command
        self.timeout = timeout
        self.cwd = cwd
        self.use_file = source == "file" or "{out}" in command \
            or bool(output_file)
        self.output_file = output_file
        self.shell = shell
        self.check_lines = check_lines
        self.strict_output = strict_output
        self.strict_targets = strict_targets

    def _execute(
        self, case: Case, out_path: str
    ) -> subprocess.CompletedProcess[str]:
        """Run the command for ``case``."""
        windows = os.name == "nt"
        quote = (lambda text: f'"{text}"') if windows else shlex.quote
        command = self.command.replace("{name}", case.path.stem)
        command = command.replace("{map}", quote(str(case.path)))
        command = command.replace("{out}", quote(out_path))
        env = dict(os.environ, SDL_VIDEODRIVER="dummy", PYTHONUNBUFFERED="1")
        # Windows splits a command line itself (backslashes in paths would
        # break shlex), so the string is passed through as it is.
        shell = self.shell or windows
        return subprocess.run(
            command if shell else shlex.split(command),
            shell=shell, cwd=self.cwd, env=env, text=True,
            errors="replace", capture_output=True, timeout=self.timeout,
            stdin=subprocess.DEVNULL,
        )

    def run_case(self, case: Case) -> Outcome:
        """Run the program on ``case`` and judge the result."""
        start = time.monotonic()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "solution.txt")
            if self.output_file:
                out_path = os.path.join(self.cwd or ".", self.output_file)
                if os.path.exists(out_path):
                    os.remove(out_path)
            try:
                process = self._execute(case, out_path)
            except subprocess.TimeoutExpired:
                return self._done(case, start, FAIL,
                                  f"timeout after {self.timeout:g}s")
            except (OSError, ValueError) as error:
                return self._done(case, start, FAIL,
                                  f"could not run the command: {error}")
            written = ""
            if self.use_file and os.path.exists(out_path):
                written = Path(out_path).read_text("utf-8", errors="replace")
        if case.expect == "error":
            outcome = self._judge_error(case, process, written)
        else:
            outcome = self._judge_solution(case, process, written)
            outcome.output = written if self.use_file else process.stdout
        outcome.seconds = time.monotonic() - start
        if outcome.status != PASS and case.note:
            outcome.details = (f"about this map: {case.note}",
                               *outcome.details)
        if outcome.status == FAIL and case.level == "recommended":
            outcome.status = WARN
            outcome.message = f"(recommended) {outcome.message}"
        return outcome

    def _done(
        self, case: Case, start: float, status: str, message: str
    ) -> Outcome:
        """Build an outcome that ends the case early."""
        if status == FAIL and case.level == "recommended":
            status, message = WARN, f"(recommended) {message}"
        return Outcome(case, status, message, seconds=time.monotonic() - start)

    def _judge_error(
        self,
        case: Case,
        process: subprocess.CompletedProcess[str],
        written: str,
    ) -> Outcome:
        """Judge a run on a map that the program must reject."""
        combined = process.stdout + "\n" + process.stderr
        turns, noise = extract_turns(process.stdout)
        details = tuple(noise[-3:])
        if TRACEBACK.search(combined) or process.returncode < 0:
            cause = last_line(process.stderr) or last_line(process.stdout)
            return Outcome(case, FAIL, "crashed instead of reporting an "
                           f"error: {cause[:100] or 'signal'}",
                           details=details)
        if process.returncode == 0:
            return Outcome(case, FAIL, "accepted an invalid map "
                           "(exit status 0)", details=details)
        if turns or written.strip():
            return Outcome(case, FAIL, "printed a solution for an invalid "
                           "map", details=details)
        message = (process.stderr.strip() or "\n".join(noise)).strip()
        message = message.replace(str(case.path), case.path.name)
        if not message:
            return Outcome(case, FAIL, "no error message")
        if case.lines and self.check_lines:
            numbers = {int(n) for n in re.findall(r"(?<![\w.])\d+(?![\w.])",
                                                  message)}
            if not numbers & set(case.lines):
                wanted = " or ".join(str(n) for n in case.lines)
                return Outcome(case, FAIL, f"error message does not name "
                               f"line {wanted}", details=(message[:200],))
        return Outcome(case, PASS, "rejected with a message",
                       details=(message.splitlines()[0][:160],))

    def _judge_solution(
        self,
        case: Case,
        process: subprocess.CompletedProcess[str],
        written: str,
    ) -> Outcome:
        """Judge a run on a solvable map."""
        turns, noise = extract_turns(written if self.use_file
                                     else process.stdout)
        if TRACEBACK.search(process.stdout + process.stderr):
            cause = last_line(process.stderr) or last_line(process.stdout)
            return Outcome(case, FAIL, f"printed a traceback: {cause[:110]}")
        if process.returncode != 0:
            message = (process.stderr.strip().splitlines() or ["?"])[-1]
            message = message.replace(str(case.path), case.path.name)
            return Outcome(case, FAIL, f"exit status {process.returncode}: "
                           f"{message[:120]}")
        if not turns:
            where = f" in {self.output_file}" if self.output_file else \
                " in the output file" if self.use_file else ""
            return Outcome(case, FAIL, f"no solution was printed{where}")
        if self.strict_output and noise:
            return Outcome(case, FAIL, "output has lines that are not "
                           "movements", details=tuple(noise[:3]))
        try:
            fly_map = read_map(case.path)
        except (MapError, OSError, KeyError) as error:
            return Outcome(case, FAIL, f"tester cannot read the map: {error}")
        result = check_solution(fly_map, turns)
        bound = lower_bound(fly_map)
        if not result.valid:
            return Outcome(case, FAIL, "invalid solution: "
                           f"{result.errors[0]}", turns=len(turns),
                           details=tuple(result.errors[1:6]))
        visited = {token.split("-")[-1] for line in turns
                   for token in line.split()}
        missing = [z for z in case.prefer_visit if z not in visited]
        if missing:
            return Outcome(case, WARN, "valid, but the priority zone "
                           f"{', '.join(missing)} was not preferred",
                           turns=len(turns), bound=bound)
        outcome = self._judge_turns(case, len(turns))
        outcome.bound = bound
        return outcome

    def _judge_turns(self, case: Case, turns: int) -> Outcome:
        """Compare a valid solution's length with the reference target."""
        if case.target is None:
            return Outcome(case, PASS, f"valid, {turns} turns", turns=turns)
        if turns <= case.target:
            return Outcome(case, PASS, f"{turns} turns "
                           f"(target <= {case.target})", turns=turns)
        status = FAIL if self.strict_targets and not case.optional_target \
            else WARN
        return Outcome(case, status, f"valid, but {turns} turns "
                       f"(target <= {case.target})", turns=turns)

    def run_all(self, cases: list[Case], jobs: int = 1) -> list[Outcome]:
        """Run every case, optionally in parallel, keeping the order."""
        if jobs <= 1 or self.output_file:
            return [self.run_case(case) for case in cases]
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            return list(pool.map(self.run_case, cases))
