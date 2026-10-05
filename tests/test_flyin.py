"""Tests for the flyin command, its settings and the library API."""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import flyin
from flyin import config
from flyin.app import main
from flyin.tester.runner import FAIL, MAPS_DIR, PASS

ROOT = Path(__file__).resolve().parent.parent
NAIVE = ROOT / "examples" / "naive_solver.py"
EASY = "provided/easy/01_linear_path.txt"


def naive_output(map_name: str) -> str:
    """Return the naive solver's output for a bundled map."""
    return subprocess.run(
        [sys.executable, str(NAIVE), str(flyin.find_map(map_name))],
        capture_output=True, text=True, check=True).stdout


class LibraryTests(unittest.TestCase):
    """``import flyin`` works without the menu."""

    def test_find_map(self) -> None:
        """Short names, paths and files; clear errors otherwise."""
        self.assertEqual(flyin.find_map("easy/01").name,
                         "01_linear_path.txt")
        self.assertEqual(flyin.find_map(EASY), MAPS_DIR / EASY)
        self.assertEqual(flyin.find_map(MAPS_DIR / EASY), MAPS_DIR / EASY)
        for bad in ("01", "no_such_map", "challenge"):
            with self.subTest(ref=bad), self.assertRaises(LookupError):
                flyin.find_map(bad)

    def test_maps(self) -> None:
        """All, a group, or a text."""
        self.assertEqual(len(flyin.maps()), 430)
        self.assertEqual(len(flyin.maps("fuzz")), 300)
        self.assertEqual(len(flyin.maps("challenge")), 5)
        self.assertEqual(len(flyin.maps("easy")), 3)

    def test_check_accepts_text_lines_and_files(self) -> None:
        """The output can be text, a list of lines or a file."""
        text = naive_output("easy/01")
        self.assertTrue(flyin.check("easy/01", text).valid)
        self.assertTrue(flyin.check("easy/01", text.splitlines()).valid)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.txt"
            path.write_text("debug: hello\n" + text, "utf-8")
            self.assertTrue(flyin.check("easy/01", path).valid)
        self.assertFalse(flyin.check("easy/01", ["D1-goal"]).valid)

    def test_run_and_test(self) -> None:
        """One map, then a group, with the naive solver."""
        command = f"{sys.executable} {NAIVE} {{map}}"
        outcome = flyin.run("easy/01", command)
        self.assertEqual(outcome.status, PASS)
        self.assertIn("D1-", outcome.output)
        outcomes = flyin.test(command, only="easy", jobs=2)
        self.assertEqual(len(outcomes), 3)
        self.assertNotIn(FAIL, [o.status for o in outcomes])


class InWorkdir(unittest.TestCase):
    """Base: every test runs in its own empty working directory."""

    def setUp(self) -> None:
        """Change into a temporary directory."""
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        old = Path.cwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, old)

    def flyin(self, *args: str, stdin: str = "") -> tuple[int, str]:
        """Run ``flyin`` in-process; return exit status and output."""
        out = io.StringIO()
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin)
        try:
            with contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(out):
                code = main(list(args))
        finally:
            sys.stdin = old_stdin
        return code, out.getvalue()

    def project(self) -> Path:
        """Create a project folder whose main.py is the naive solver."""
        folder = self.dir / "project"
        folder.mkdir()
        shutil.copy(NAIVE, folder / "main.py")
        return folder


class ConfigTests(InWorkdir):
    """Settings and remembered results."""

    def test_detect_command(self) -> None:
        """main.py, a compiled program, a package."""
        folder = self.dir / "p"
        folder.mkdir()
        self.assertIsNone(config.detect_command(folder))
        (folder / "pkg").mkdir()
        (folder / "pkg" / "__main__.py").write_text("")
        self.assertIn("-m pkg {map}", str(config.detect_command(folder)))
        binary = folder / "fly_in"
        binary.write_text("")
        binary.chmod(0o755)
        self.assertEqual(config.detect_command(folder), "./fly_in {map}")
        (folder / "main.py").write_text("")
        self.assertEqual(config.detect_command(folder),
                         "python3 main.py {map}")

    def test_save_and_load(self) -> None:
        """The settings survive in .flyin/config.json."""
        self.assertIsNone(config.load())
        config.save(config.Config("/x", "run {map}", theme="ashen"))
        loaded = config.load()
        assert loaded is not None
        self.assertEqual((loaded.command, loaded.theme),
                         ("run {map}", "ashen"))
        self.assertTrue((self.dir / ".flyin" / ".gitignore").is_file())


class SelectionTests(unittest.TestCase):
    """Choosing several maps in the menu."""

    def test_selection(self) -> None:
        """Numbers, lists, ranges, all; names are not selections."""
        from flyin.menu import selection
        self.assertEqual(selection("all", 3), [0, 1, 2])
        self.assertEqual(selection("1,3", 5), [0, 2])
        self.assertEqual(selection("2-4, 1", 5), [1, 2, 3, 0])
        self.assertEqual(selection("9", 3), None)
        self.assertEqual(selection("city_grid", 3), None)


class CommandTests(InWorkdir):
    """The short commands of ``flyin``."""

    def test_setup_test_and_problems(self) -> None:
        """Set up, test a group, remember the problem maps."""
        project = self.project()
        code, text = self.flyin("setup", str(project), "--cmd",
                                f"{sys.executable} main.py")
        self.assertEqual(code, 0, text)
        self.assertIn("Works", text)
        cfg = config.load()
        assert cfg is not None
        self.assertTrue(cfg.command.endswith("{map}"))
        code, text = self.flyin("test", "challenge")
        self.assertEqual(code, 0, text)
        self.assertIn("[challenge] 0/5 passed, 5 warnings", text)
        self.assertIn("flyin show --problems", text)
        records = config.last_run()
        self.assertEqual(len(records), 5)
        self.assertTrue(Path(records[0]["output"]).is_file())

    def test_programs_that_write_files(self) -> None:
        """A fixed output file, or a file passed as {out}."""
        folder = self.dir / "writer"
        folder.mkdir()
        (folder / "main.py").write_text(
            "import subprocess, sys\n"
            f"out = subprocess.run([sys.executable, {str(NAIVE)!r}, "
            "sys.argv[1]], capture_output=True, text=True).stdout\n"
            "target = sys.argv[2] if len(sys.argv) > 2 else 'output.txt'\n"
            "open(target, 'w').write(out)\nprint('done')\n", "utf-8")
        command = f"{sys.executable} main.py"
        code, text = self.flyin("setup", str(folder), "--cmd", command,
                                "--output-file", "output.txt")
        self.assertEqual(code, 0, text)
        self.assertIn("Works", text)
        code, text = self.flyin("setup", str(folder), "--cmd",
                                command + " {map} {out}", "--output-file", "")
        self.assertIn("Works", text)
        code, text = self.flyin("test", "easy/01")
        self.assertEqual(code, 0, text)

    def test_show_output_file_as_screenshot(self) -> None:
        """``show MAP OUTPUT --screenshot`` needs no project."""
        try:
            import pygame  # noqa: F401
        except ImportError:
            self.skipTest("pygame-ce is not installed")
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        out = self.dir / "out.txt"
        out.write_text(naive_output("easy/02"), "utf-8")
        png = self.dir / "frame.png"
        code, text = self.flyin("show", "easy/02", str(out),
                                "--screenshot", str(png))
        self.assertEqual(code, 0, text)
        self.assertTrue(png.is_file())

    def test_maps_check_and_errors(self) -> None:
        """Listing, checking from stdin, ambiguous names."""
        code, text = self.flyin("maps", "challenge")
        self.assertEqual((code, len(text.splitlines())), (0, 5))
        code, text = self.flyin("check", "easy/01", "-",
                                stdin=naive_output("easy/01"))
        self.assertEqual(code, 0, text)
        self.assertIn("VALID", text)
        code, text = self.flyin("show", "01", "-")
        self.assertEqual(code, 1)
        self.assertIn("matches 21 maps", text)


if __name__ == "__main__":
    unittest.main()


class MenuTests(InWorkdir):
    """The interactive menu, driven with typed answers."""

    def test_first_start_group_test_and_more(self) -> None:
        """Setup on first start, a group test, history, quit."""
        project = self.project()
        answers = "\n".join([
            str(project), f"{sys.executable} main.py {{map}}", "1",
            "6", "1", "5", "n",      # More -> Test one group -> challenge
            "6", "3",                # More -> History
            "0", ""])
        code, text = self.flyin(stdin=answers)
        self.assertEqual(code, 0, text)
        self.assertIn("First start", text)
        self.assertIn("Works", text)
        self.assertIn("[challenge]", text)
        self.assertIn("5 maps", text)
        self.assertIn("warn", text)

    @unittest.skipUnless(sys.platform.startswith("linux"),
                         "needs the no-display message of Linux")
    def test_selection_of_several_maps(self) -> None:
        """'Watch maps' with a range runs each map (no display here)."""
        project = self.project()
        config.save(config.Config(str(project),
                                  f"{sys.executable} main.py {{map}}"))
        os.environ.pop("SDL_VIDEODRIVER", None)
        old = {k: os.environ.pop(k, None) for k in ("DISPLAY",
                                                    "WAYLAND_DISPLAY")}
        try:
            code, text = self.flyin(stdin="2\n1\n1-2\n0\n")
        finally:
            for key, value in old.items():
                if value is not None:
                    os.environ[key] = value
        self.assertEqual(code, 0, text)
        self.assertIn("[1/2]", text)
        self.assertIn("[2/2]", text)
