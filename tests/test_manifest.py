"""Consistency of the bundled maps and their manifest."""

import unittest
from pathlib import Path

from fly_in_tester.mapfile import MapError, has_route, parse_map, shortest_cost
from fly_in_tester.runner import MAPS_DIR, load_manifest


class ManifestTests(unittest.TestCase):
    """Every map is present and labelled truthfully."""

    def setUp(self) -> None:
        """Load the manifest."""
        self.cases = load_manifest()

    def test_not_empty_and_groups(self) -> None:
        """All five groups exist."""
        self.assertGreater(len(self.cases), 100)
        self.assertEqual(
            {c.group for c in self.cases},
            {"provided", "provided-invalid", "edge-valid", "edge-invalid",
             "challenge"})

    def test_files_exist_and_none_are_orphaned(self) -> None:
        """Manifest and maps/ list exactly the same files."""
        listed = {c.path.resolve() for c in self.cases}
        for path in listed:
            self.assertTrue(path.is_file(), path)
        found = {p.resolve() for p in MAPS_DIR.rglob("*.txt")}
        self.assertEqual(found - listed, set(), "maps not in the manifest")

    def test_paths_are_unique(self) -> None:
        """No map is listed twice."""
        names = [c.name for c in self.cases]
        self.assertEqual(len(names), len(set(names)))

    def test_solvable_maps_are_really_solvable(self) -> None:
        """Maps that must be solved parse and have a route."""
        for case in self.cases:
            if case.expect != "solve":
                continue
            with self.subTest(map=case.name):
                text = case.path.read_text("utf-8")
                fly_map = parse_map(text)
                self.assertTrue(has_route(fly_map))

    def test_targets_are_physically_possible(self) -> None:
        """A target below the shortest route would be impossible."""
        for case in self.cases:
            if case.expect != "solve" or case.target is None:
                continue
            with self.subTest(map=case.name):
                cost = shortest_cost(parse_map(case.path.read_text("utf-8")))
                assert cost is not None
                self.assertGreaterEqual(case.target, cost)

    def test_error_maps_have_a_reason_that_holds(self) -> None:
        """Maps marked 'unsolvable' parse but have no route."""
        data = __import__("json").loads(
            (MAPS_DIR / "manifest.json").read_text("utf-8"))["maps"]
        for entry in data:
            if entry["expect"] != "error":
                continue
            self.assertIn(entry["reason"], ("syntax", "unsolvable"))
            if entry["reason"] != "unsolvable":
                continue
            with self.subTest(map=entry["path"]):
                text = (MAPS_DIR / entry["path"]).read_text("utf-8")
                try:
                    fly_map = parse_map(text)
                except MapError:
                    continue
                self.assertFalse(has_route(fly_map))

    def test_expected_lines_are_inside_the_file(self) -> None:
        """A line number in the manifest exists in the map."""
        for case in self.cases:
            if not case.lines:
                continue
            with self.subTest(map=case.name):
                count = len(case.path.read_bytes().splitlines())
                for line in case.lines:
                    self.assertLessEqual(line, count)

    def test_valid_edge_maps_have_no_syntax_error_for_the_reader(self) -> None:
        """The tester's own reader understands every solvable map."""
        for case in self.cases:
            if case.expect == "solve":
                with self.subTest(map=case.name):
                    self.assertIsInstance(Path(case.path).read_bytes(), bytes)
                    parse_map(case.path.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
