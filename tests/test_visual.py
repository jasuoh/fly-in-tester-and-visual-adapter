"""Tests for the adaptive layer and the visualizer (headless)."""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from flyin.tester.mapfile import MapError, parse_map, read_map
from flyin.tester.runner import MAPS_DIR
from flyin.visual.loader import graph_from_map
from flyin.visual.models import ZoneType
from flyin.visual.replay import build_replay, detect_id_base

ROOT = Path(__file__).resolve().parent.parent
NAIVE = ROOT / "examples" / "naive_solver.py"

MAP = """\
nb_drones: 2
start_hub: s 0 0 [color=green]
hub: r 1 0 [zone=restricted color=red]
hub: p 1 1 [zone=priority max_drones=2]
end_hub: e 2 0
connection: s-r
connection: r-e
connection: s-p
connection: p-e
"""
VALID = "D1-s-r\nD1-r D2-p\nD1-e D2-e\n"

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
try:
    import pygame  # noqa: F401
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False


def quiet(function: object, *args: object) -> int:
    """Call ``function`` with stdout and stderr swallowed."""
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return function(*args)  # type: ignore[operator, no-any-return]


class LoaderTests(unittest.TestCase):
    """The tester's map becomes the GUI's graph."""

    def test_zones_connections_and_colors(self) -> None:
        """Types, capacities, colours, start and end are kept."""
        graph = graph_from_map(parse_map(MAP))
        self.assertEqual(graph.nb_drones, 2)
        self.assertEqual(graph.start.name, "s")
        self.assertEqual(graph.end.name, "e")
        self.assertEqual(graph.zone("r").zone_type, ZoneType.RESTRICTED)
        self.assertEqual(graph.zone("p").max_drones, 2)
        self.assertEqual(graph.zone("s").color, "green")
        self.assertIsNotNone(graph.connection("e", "p"))
        self.assertEqual(len(graph.connections), 4)

    def test_connection_to_unknown_zone(self) -> None:
        """A broken map is a MapError, not a crash."""
        with self.assertRaises(MapError):
            graph_from_map(parse_map(MAP + "connection: e-ghost\n"))

    def test_every_solvable_bundled_map_loads(self) -> None:
        """All maps the tester expects to be solved can be shown."""
        for path in sorted(MAPS_DIR.rglob("*.txt")):
            if "invalid" in path.parts:
                continue
            with self.subTest(map=path.name):
                graph_from_map(read_map(path))


class ReplayTests(unittest.TestCase):
    """Any output becomes a playable result."""

    def setUp(self) -> None:
        """Parse the small map."""
        self.map = parse_map(MAP)

    def test_valid_output(self) -> None:
        """A valid log is replayed move by move."""
        replay = build_replay(self.map, VALID)
        self.assertTrue(replay.valid)
        self.assertEqual(replay.skipped, [])
        turns = replay.result.turns
        self.assertEqual(len(turns), 3)
        self.assertEqual([str(m) for m in turns[0].moves], ["D1-s-r"])
        self.assertEqual([str(m) for m in turns[1].moves], ["D1-r", "D2-p"])
        self.assertEqual(replay.result.id_base, 1)

    def test_noise_is_ignored(self) -> None:
        """Banners and debug lines around the turns do not count."""
        replay = build_replay(self.map, "solver v2\n" + VALID + "done!\n")
        self.assertTrue(replay.valid)
        self.assertEqual(len(replay.result.turns), 3)

    def test_ids_from_zero(self) -> None:
        """D0..D(n-1) is detected and kept."""
        text = "D0-s-r\nD0-r D1-p\nD0-e D1-e\n"
        self.assertEqual(detect_id_base(text.splitlines()), 0)
        replay = build_replay(self.map, text)
        self.assertTrue(replay.valid)
        self.assertEqual(replay.result.id_base, 0)

    def test_undrawable_tokens_are_skipped(self) -> None:
        """Unknown zones and drones, double moves are left out."""
        text = "D1-s-r D1-p D3-p D2-moon\nD1-r D2-p\nD1-e D2-e\n"
        replay = build_replay(self.map, text, raw=True)
        self.assertFalse(replay.valid)
        self.assertEqual(len(replay.skipped), 3)
        self.assertEqual([str(m) for m in replay.result.turns[0].moves],
                         ["D1-s-r"])

    def test_rule_violations_are_still_shown(self) -> None:
        """A move over a missing connection is drawn, the checker fails."""
        replay = build_replay(self.map, "D1-e D2-e\n")
        self.assertFalse(replay.valid)
        self.assertEqual(replay.skipped, [])
        self.assertEqual(len(replay.result.turns[0].moves), 2)

    def test_moves_after_delivery_are_skipped(self) -> None:
        """A delivered drone does not come back on screen."""
        text = VALID + "D1-p\n"
        replay = build_replay(self.map, text)
        self.assertEqual(len(replay.skipped), 1)
        self.assertIn("already delivered", replay.skipped[0])


@unittest.skipUnless(HAS_PYGAME, "pygame-ce is not installed")
class GuiTests(unittest.TestCase):
    """The reference GUI plays replays of any output, headless."""

    def setUp(self) -> None:
        """Use the dummy video driver."""
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_every_theme_turn_and_progress(self) -> None:
        """Frames render for all themes, also with ids from zero."""
        from flyin.visual.gui import GuiVisualizer
        fly_map = parse_map(MAP)
        for text in (VALID, "D0-s-r\nD0-r D1-p\nD0-e D1-e\n",
                     "D1-e D2-moon\nD2-e\n"):
            replay = build_replay(fly_map, text, raw=True)
            for theme in GuiVisualizer.theme_names():
                gui = GuiVisualizer(replay.result.graph, theme, "t")
                for turn in range(len(replay.result.turns)):
                    for progress in (0.0, 0.3, 0.5, 1.0):
                        frame = gui.render_frame(replay.result, turn,
                                                 progress, (900, 600))
                        self.assertEqual(frame.get_size(), (900, 600))

    def test_show_writes_screenshot(self) -> None:
        """``show`` checks, reports and saves a PNG."""
        from flyin.visual.view import show
        map_path = self.dir / "map.txt"
        map_path.write_text(MAP, encoding="utf-8")
        png = self.dir / "frame.png"
        self.assertEqual(quiet(show, str(map_path), VALID, "ashen",
                               str(png), 2), 0)
        self.assertGreater(png.stat().st_size, 1000)
        self.assertEqual(quiet(show, str(map_path), "D1-e D2-e", "mission",
                               str(png)), 1)
        self.assertEqual(quiet(show, str(map_path), "nothing here"), 1)

    def test_view_command_with_cmd(self) -> None:
        """``view --cmd`` runs a program and shows its output."""
        png = self.dir / "naive.png"
        process = subprocess.run(
            [sys.executable, "-m", "flyin", "view",
             str(MAPS_DIR / "edge" / "valid" / "fork_merge_bottleneck.txt"),
             "--cmd", f"{sys.executable} {NAIVE} {{map}}",
             "--screenshot", str(png)],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
            env=dict(os.environ, SDL_VIDEODRIVER="dummy"), check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("VALID solution", process.stdout)
        self.assertTrue(png.is_file())


class NaiveSolverTests(unittest.TestCase):
    """The example solver is valid on every map it must solve."""

    def test_valid_on_extra_and_challenge_maps(self) -> None:
        """Slow but correct."""
        for group in ("extra", "challenge"):
            for path in sorted((MAPS_DIR / group).rglob("*.txt")):
                if "invalid" in path.parts:
                    continue
                with self.subTest(map=path.name):
                    output = subprocess.run(
                        [sys.executable, str(NAIVE), str(path)],
                        capture_output=True, text=True, timeout=60,
                        check=True).stdout
                    replay = build_replay(read_map(path), output)
                    self.assertTrue(replay.valid, replay.check.errors[:3])
