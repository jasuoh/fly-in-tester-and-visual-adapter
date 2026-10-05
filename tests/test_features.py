"""Tests for issues, compare, history, eval, generate and rules."""

import os
import sys
import unittest
from pathlib import Path

import flyin
from flyin import config, report
from flyin.app import changes
from flyin.tester.checker import check_solution
from flyin.tester.generate import generate
from flyin.tester.mapfile import has_route, parse_map
from flyin.tester.runner import FAIL, PASS, WARN, Outcome
from flyin.visual.replay import build_replay
from tests.test_flyin import NAIVE, InWorkdir, naive_output

MAP = """\
nb_drones: 3
start_hub: s 0 0
hub: a 1 0 [max_drones=2]
end_hub: e 2 0
connection: s-a [max_link_capacity=3]
connection: a-e [max_link_capacity=3]
"""

try:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame  # noqa: F401
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False


class IssueTests(unittest.TestCase):
    """The checker says where a rule is broken."""

    def test_zone_and_link_are_named(self) -> None:
        """An overfull zone and a missing connection."""
        fly_map = parse_map(MAP)
        result = check_solution(fly_map, ["D1-a D2-a D3-a", "D1-e D2-e D3-e"])
        overfull = [i for i in result.issues if "holds" in i.message]
        self.assertEqual((overfull[0].turn, overfull[0].zones), (1, ("a",)))
        result = check_solution(fly_map, ["D1-e D2-e D3-e"])
        self.assertEqual(result.issues[0].link, ("s", "e"))

    def test_replay_keeps_the_issues(self) -> None:
        """The GUI gets them, limited to zones of the map."""
        replay = build_replay(parse_map(MAP), "D1-a D2-a D3-a\nD1-e D2-e "
                              "D3-e\n")
        self.assertTrue(any(i.zones == ("a",) for i in replay.result.issues))

    @unittest.skipUnless(HAS_PYGAME, "pygame-ce is not installed")
    def test_frames_with_issues_render(self) -> None:
        """Marks, panel section and timeline dots draw in every theme."""
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        from flyin.visual.gui import GuiVisualizer
        replay = build_replay(parse_map(MAP), "D1-a D2-a D3-a\nD1-e D2-e "
                              "D3-e\n")
        for theme in GuiVisualizer.theme_names():
            gui = GuiVisualizer(replay.result.graph, theme, "t")
            for turn in (0, 1):
                for progress in (0.2, 0.8):
                    gui.render_frame(replay.result, turn, progress,
                                     (900, 600))


class GenerateTests(unittest.TestCase):
    """Random maps."""

    def test_same_seed_same_solvable_map(self) -> None:
        """Deterministic, solvable, with its bound in the header."""
        for seed in range(20):
            text = generate(seed, 7, 3, 15)
            self.assertEqual(text, generate(seed, 7, 3, 15))
            self.assertTrue(has_route(parse_map(text)))
            self.assertIn("# lower bound:", text)
            self.assertNotIn("?", text.splitlines()[1])

    def test_random_shape(self) -> None:
        """Scattered zones, also solvable and deterministic."""
        for seed in range(10):
            text = generate(seed, 4, 3, 10, "random")
            self.assertEqual(text, generate(seed, 4, 3, 10, "random"))
            self.assertTrue(has_route(parse_map(text)))
            self.assertIn("12 scattered zones", text)

    def test_naive_solver_is_valid_on_generated_maps(self) -> None:
        """A sanity check of generator and checker together."""
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for seed in range(5):
                path = Path(tmp) / f"{seed}.txt"
                path.write_text(generate(seed, 6, 3, 8), "utf-8")
                out = subprocess.run([sys.executable, str(NAIVE), str(path)],
                                     capture_output=True, text=True,
                                     check=True).stdout
                self.assertTrue(flyin.check(path, out).valid)


class HistoryTests(InWorkdir):
    """Runs are remembered and compared."""

    def test_changes_and_saved_outputs(self) -> None:
        """Better and worse lines; last and previous outputs."""
        case = flyin.case_for("easy/02")
        first = Outcome(case, WARN, "slow", turns=9, output="D1-x\n")
        second = Outcome(case, PASS, "fast", turns=5, output="D1-y\n")
        config.save_run([first])
        config.save_run([second])
        runs = config.history()
        self.assertEqual(len(runs), 2)
        better, worse = changes(runs[0], [second])
        self.assertEqual((len(better), worse), (1, []))
        better, worse = changes(runs[1], [first])
        self.assertEqual((better, len(worse)), ([], 1))
        last = config.saved_output(case.name, "last")
        previous = config.saved_output(case.name, "previous")
        assert last is not None and previous is not None
        self.assertEqual(last.read_text(), "D1-y\n")
        self.assertEqual(previous.read_text(), "D1-x\n")

    def test_history_command(self) -> None:
        """Lists the runs."""
        config.save_run([Outcome(flyin.case_for("easy/01"), PASS, "", 4)])
        code, text = self.flyin("history")
        self.assertEqual(code, 0)
        self.assertIn("1 pass", text)


class ReportTests(unittest.TestCase):
    """The evaluation checklist."""

    def test_checklist_and_markdown(self) -> None:
        """A crash and a missed target show up."""
        crash = Outcome(flyin.case_for("easy/01"), FAIL,
                        "printed a traceback: boom")
        slow = Outcome(flyin.case_for("easy/02"), WARN,
                       "valid, but 9 turns", turns=9)
        rows = {r[1]: r[0] for r in report.checklist([crash, slow])}
        self.assertFalse(rows["No crash, no traceback"])
        self.assertFalse(rows["Turn targets of the subject are met"])
        self.assertTrue(rows["No timeout"])
        text = report.build([crash, slow], "/p", "cmd {map}")
        self.assertIn("# Fly-In evaluation report", text)
        self.assertIn("❌", text)


class CommandTests(InWorkdir):
    """generate, rules, compare."""

    def test_generate_and_rules(self) -> None:
        """A map file is written; the rules are printed."""
        code, text = self.flyin("generate", "--seed", "3", "--size", "5x2")
        self.assertEqual(code, 0, text)
        self.assertTrue((self.dir / "maps-generated/seed_3.txt").is_file())
        code, text = self.flyin("rules")
        self.assertIn("Leaving frees the place", text)

    @unittest.skipUnless(HAS_PYGAME, "pygame-ce is not installed")
    def test_compare_screenshot(self) -> None:
        """Two files side by side, one of them invalid."""
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        good = self.dir / "good.txt"
        good.write_text(naive_output("easy/03"), "utf-8")
        bad = self.dir / "bad.txt"
        bad.write_text("D1-bottleneck D2-bottleneck D3-bottleneck\n")
        png = self.dir / "pair.png"
        code, text = self.flyin("compare", "easy/03", str(good), str(bad),
                                "--screenshot", str(png), "--turn", "1")
        self.assertEqual(code, 1, text)
        self.assertTrue(png.is_file())
        code, text = self.flyin("compare", "easy/03", "last", "now")
        self.assertEqual(code, 2)
        self.assertIn("test it once first", text)


if __name__ == "__main__":
    unittest.main()
