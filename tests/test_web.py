"""Tests for ``flyin web``: the local server and its JSON API."""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from flyin import config
from flyin.config import Config
from flyin.tester.mapfile import parse_map
from flyin.tester.runner import Case
from flyin.web.server import make_server, replay_json

GOOD = """\
import sys
print('D1-a')
print('D1-g')
"""


class WebTests(unittest.TestCase):
    """The server answers the page and nobody else."""

    def setUp(self) -> None:
        """Serve from a temporary folder with a configured fake project."""
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        old = Path.cwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, old)
        (self.dir / "main.py").write_text(GOOD, "utf-8")
        config.save(Config(str(self.dir), f"{sys.executable} main.py {{map}}",
                           timeout=20, jobs=2))
        self.server = make_server(0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever,
                         daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        page = urllib.request.urlopen(self.url("/")).read().decode()
        self.token = page.split('name="flyin-token" content="')[1] \
            .split('"')[0]

    def url(self, path: str) -> str:
        """Return the address of ``path`` on the test server."""
        return f"http://127.0.0.1:{self.port}{path}"

    def call(self, path: str, body: Any = None,
             headers: dict[str, str] | None = None) -> tuple[int, Any]:
        """Call the API; return (status, JSON)."""
        sent = {"X-Flyin-Token": self.token} if headers is None else headers
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.url(path), data, sent)
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_page_and_token(self) -> None:
        """The page carries a token; the API refuses calls without it or
        from another Host (DNS rebinding)."""
        self.assertGreater(len(self.token), 20)
        self.assertEqual(self.call("/api/state", headers={})[0], 403)
        self.assertEqual(self.call("/api/state", headers={
            "X-Flyin-Token": "wrong"})[0], 403)
        self.assertEqual(self.call("/api/state", headers={
            "X-Flyin-Token": self.token, "Host": "evil.example"})[0], 403)
        status, state = self.call("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(state["subject"]["version"], "3.0")

    def test_static_files_stay_inside(self) -> None:
        """Only the page's own files are served."""
        request = urllib.request.Request(self.url("/static/app.js"))
        self.assertEqual(urllib.request.urlopen(request).status, 200)
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.url("/static/../server.py"))

    def test_map_run_and_check(self) -> None:
        """A map is drawn, run and replayed; a pasted output is checked."""
        name = "edge/valid/single_drone_linear.txt"
        status, data = self.call(f"/api/map?name={name}")
        self.assertEqual(status, 200)
        self.assertEqual(data["nb_drones"], 1)
        status, data = self.call("/api/run", {"name": name})
        self.assertEqual(data["outcome"]["status"], "PASS", data)
        self.assertEqual(data["replay"]["moves"], [[[1, "a"]], [[1, "g"]]])
        status, data = self.call("/api/check", {"name": name,
                                                "output": "D1-g\n"})
        self.assertFalse(data["replay"]["valid"])
        self.assertEqual(self.call("/api/map?name=nope")[0], 404)

    def test_restricted_flight_is_a_place(self) -> None:
        """A flight becomes ``a>b`` whichever way the connection is named
        (subject 3.0: ``D<id>-<connection>``)."""
        fly_map = parse_map("nb_drones: 1\nstart_hub: s 0 0\n"
                            "hub: r 1 0 [zone=restricted]\nend_hub: g 2 0\n"
                            "connection: r-s\nconnection: r-g\n")
        case = Case(self.dir / "m.txt", "m.txt", "", "solve")
        case.path.write_text("", "utf-8")
        for token in ("D1-s-r", "D1-r-s"):
            with unittest.mock.patch("flyin.web.server.read_map",
                                     return_value=fly_map):
                data = replay_json(case, f"{token}\nD1-r\nD1-g\n")
            self.assertTrue(data["valid"], data["errors"])
            self.assertEqual(data["moves"][0], [[1, "s>r"]])

    def test_test_job(self) -> None:
        """A test runs in the background and is saved like 'flyin test'."""
        status, data = self.call("/api/test", {"only": [
            "edge/valid/single_drone_linear.txt"]})
        self.assertEqual((status, data["total"]), (200, 1))
        for _ in range(100):
            status, data = self.call("/api/test")
            if not data["running"]:
                break
            time.sleep(0.1)
        self.assertEqual(data["counts"]["PASS"], 1, data)
        self.assertEqual(len(config.last_run()), 1)
        status, rows = self.call("/api/maps")
        row = next(r for r in rows
                   if r["name"] == "edge/valid/single_drone_linear.txt")
        self.assertEqual(row["status"], "PASS")

    def test_config_is_checked(self) -> None:
        """A command without {map} or a missing folder is refused."""
        status, data = self.call("/api/config", {
            "project": str(self.dir), "command": "python3 main.py"})
        self.assertEqual(status, 400)
        self.assertIn("{map}", data["error"])
        status, _ = self.call("/api/config", {
            "project": str(self.dir / "nope"), "command": "x {map}"})
        self.assertEqual(status, 400)
        status, data = self.call("/api/config", {
            "project": str(self.dir), "command": "python3 main.py {map}",
            "timeout": 5, "jobs": 1})
        self.assertEqual((status, data["timeout"]), (200, 5.0))


if __name__ == "__main__":
    unittest.main()
