"""Tests for the runner, using tiny fake programs instead of a real project."""

import dataclasses
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fly_in_tester.runner import (
    FAIL, PASS, WARN, Case, Runner, extract_turns, load_manifest,
)

ROOT = Path(__file__).resolve().parent.parent


def case(name: str) -> Case:
    """Return the manifest case for ``name`` (a path below maps/)."""
    for candidate in load_manifest():
        if candidate.name == name:
            return candidate
    raise KeyError(name)


class FakeProgramTests(unittest.TestCase):
    """Judging of programs that behave in different ways."""

    def setUp(self) -> None:
        """Create a temporary directory for fake programs."""
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.solve = case("edge/valid/single_drone_linear.txt")
        self.reject = case("edge/invalid/nb_drones_zero.txt")

    def runner(self, code: str, **options: object) -> Runner:
        """Return a Runner for a fake program with the given source."""
        script = Path(self._tmp.name) / "fake.py"
        script.write_text(code, encoding="utf-8")
        return Runner(f"{sys.executable} {script} {{map}} {{out}}"
                      if options.pop("out", False) else
                      f"{sys.executable} {script} {{map}}",
                      timeout=float(str(options.pop("timeout", 20))),
                      **options)  # type: ignore[arg-type]

    def judge(self, code: str, which: Case, **options: object) -> str:
        """Run ``code`` on ``which`` and return the status."""
        return self.runner(code, **options).run_case(which).status

    def test_correct_solution(self) -> None:
        """A valid solution passes."""
        self.assertEqual(
            self.judge("print('D0-a'); print('D0-g')", self.solve), PASS)

    def test_noise_is_ignored_unless_strict(self) -> None:
        """Banner lines are ignored; --strict-output rejects them."""
        code = "print('pygame 2.0 hello'); print('D0-a'); print('D0-g')"
        self.assertEqual(self.judge(code, self.solve), PASS)
        self.assertEqual(
            self.judge(code, self.solve, strict_output=True), FAIL)

    def test_invalid_solution(self) -> None:
        """A rule violation fails and names the problem."""
        outcome = self.runner("print('D0-g')").run_case(self.solve)
        self.assertEqual(outcome.status, FAIL)
        self.assertIn("invalid solution", outcome.message)

    def test_traceback_message_names_the_cause(self) -> None:
        """The failure message shows the last line of the traceback."""
        outcome = self.runner(
            "raise ModuleNotFoundError('No module named pydantic')"
        ).run_case(self.solve)
        self.assertEqual(outcome.status, FAIL)
        self.assertIn("No module named pydantic", outcome.message)

    def test_incomplete_and_missing_solution(self) -> None:
        """Half a solution, or none, fails."""
        self.assertEqual(self.judge("print('D0-a')", self.solve), FAIL)
        self.assertEqual(self.judge("print('done')", self.solve), FAIL)

    def test_exit_status_and_traceback(self) -> None:
        """A non-zero exit or a traceback fails even with a solution."""
        base = "print('D0-a'); print('D0-g')\n"
        self.assertEqual(
            self.judge(base + "raise SystemExit(3)", self.solve), FAIL)
        self.assertEqual(
            self.judge(base + "raise RuntimeError('x')", self.solve), FAIL)

    def test_too_many_turns_is_a_warning_or_failure(self) -> None:
        """A valid but longer-than-target solution warns (fails if strict)."""
        stricter = dataclasses.replace(self.solve, target=1)
        code = "print('D0-a'); print('D0-g')"
        self.assertEqual(self.judge(code, stricter), WARN)
        self.assertEqual(
            self.judge(code, stricter, strict_targets=True), FAIL)
        optional = dataclasses.replace(stricter, optional_target=True)
        self.assertEqual(
            self.judge(code, optional, strict_targets=True), WARN)

    def test_timeout(self) -> None:
        """A program that hangs fails with a timeout message."""
        outcome = self.runner("import time; time.sleep(30)",
                              timeout=1).run_case(self.solve)
        self.assertEqual(outcome.status, FAIL)
        self.assertIn("timeout", outcome.message)

    def test_missing_program(self) -> None:
        """A command that cannot be started fails cleanly."""
        outcome = Runner("/no/such/program {map}").run_case(self.solve)
        self.assertEqual(outcome.status, FAIL)

    def test_solution_from_a_file(self) -> None:
        """With {out} the solution is read from the file."""
        code = ("import sys; open(sys.argv[2], 'w')"
                ".write('D0-a\\nD0-g\\n'); print('written')")
        self.assertEqual(self.judge(code, self.solve, out=True), PASS)
        self.assertEqual(
            self.judge("import sys", self.solve, out=True), FAIL)

    def test_valid_map_where_the_priority_zone_is_ignored(self) -> None:
        """Ignoring the priority zone only warns."""
        priority = case("edge/valid/priority_preferred.txt")
        self.assertEqual(
            self.judge("print('D0-n'); print('D0-g')", priority), WARN)
        self.assertEqual(
            self.judge("print('D0-p'); print('D0-g')", priority), PASS)

    def test_rejecting_an_invalid_map(self) -> None:
        """Exit status 1 with a message naming the line passes."""
        code = "import sys; print('map.txt:1: bad', file=sys.stderr); " \
               "sys.exit(1)"
        self.assertEqual(self.judge(code, self.reject), PASS)

    def test_rejection_without_the_line_number(self) -> None:
        """The line is required unless --no-check-lines is given."""
        code = "import sys; print('bad map', file=sys.stderr); sys.exit(1)"
        self.assertEqual(self.judge(code, self.reject), FAIL)
        self.assertEqual(
            self.judge(code, self.reject, check_lines=False), PASS)

    def test_bad_ways_to_handle_an_invalid_map(self) -> None:
        """Accepting, crashing, silence and solving all fail."""
        for code in (
            "print('D0-a')",
            "raise RuntimeError('boom')",
            "import sys; sys.exit(1)",
            "import sys; print('x', file=sys.stderr); print('D0-a'); "
            "sys.exit(1)",
            "import os, signal; os.kill(os.getpid(), signal.SIGSEGV)",
        ):
            with self.subTest(code=code):
                self.assertEqual(self.judge(code, self.reject), FAIL)

    def test_recommended_cases_only_warn(self) -> None:
        """A failing 'recommended' map is downgraded to a warning."""
        soft = dataclasses.replace(self.solve, level="recommended")
        self.assertEqual(self.judge("print('D0-g')", soft), WARN)

    def test_extract_turns(self) -> None:
        """Only movement lines are kept."""
        turns, noise = extract_turns("hi\nD0-a D1-b\n\nD2-c-d\nDx\n")
        self.assertEqual(turns, ["D0-a D1-b", "D2-c-d"])
        self.assertEqual(noise, ["hi", "Dx"])


class CommandLineTests(unittest.TestCase):
    """The command line entry points."""

    def cli(
        self, *args: str, stdin: str = ""
    ) -> subprocess.CompletedProcess[str]:
        """Run ``python -m fly_in_tester`` and return the result."""
        return subprocess.run(
            [sys.executable, "-m", "fly_in_tester", *args], cwd=ROOT,
            text=True, capture_output=True, input=stdin,
            env=dict(os.environ, PYTHONPATH=str(ROOT)))

    def test_check_valid_and_invalid_from_stdin(self) -> None:
        """`check` reads the output from stdin and sets the exit status."""
        target = str(ROOT / "maps/edge/valid/single_drone_linear.txt")
        good = self.cli("check", target, "-", stdin="banner\nD0-a\nD0-g\n")
        self.assertEqual(good.returncode, 0, good.stdout)
        self.assertIn("VALID", good.stdout)
        bad = self.cli("check", target, "-", stdin="D0-g\n")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("INVALID", bad.stdout)

    def test_run_reports_and_sets_the_exit_status(self) -> None:
        """`run` fails when the program under test fails."""
        result = self.cli("run", "--cmd", f"{sys.executable} -c pass",
                          "--filter", "edge/valid/single_drone", "--no-color")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL", result.stdout)
        self.assertIn("1 maps", result.stdout)

    def test_run_json_output(self) -> None:
        """`--json` prints machine readable results."""
        result = self.cli("run", "--cmd", f"{sys.executable} -c pass",
                          "--filter", "nb_drones_zero", "--json")
        data = json.loads(result.stdout)
        self.assertEqual(data[0]["map"], "edge/invalid/nb_drones_zero.txt")

    def test_list(self) -> None:
        """`list` names the maps."""
        result = self.cli("list", "--group", "provided-invalid")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout.splitlines()), 10)


if __name__ == "__main__":
    unittest.main()
