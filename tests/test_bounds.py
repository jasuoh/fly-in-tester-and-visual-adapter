"""The lower bound never exceeds a proven optimum."""

import unittest

from flyin.tester.bounds import flow_bound, lower_bound, simple_bound
from flyin.tester.mapfile import parse_map, read_map
from flyin.tester.runner import MAPS_DIR, load_manifest


class BoundTests(unittest.TestCase):
    """Lower bounds on known maps."""

    def test_never_above_a_known_optimum(self) -> None:
        """305 maps (challenge + fuzz) have an exact optimum."""
        known = [c for c in load_manifest() if c.optimum is not None]
        self.assertEqual(len(known), 305)
        for case in known:
            with self.subTest(map=case.name):
                bound = lower_bound(read_map(case.path))
                assert bound is not None and case.optimum is not None
                self.assertLessEqual(bound, case.optimum)

    def test_flow_bound_beats_the_simple_limits(self) -> None:
        """City grid: simple limits 29, flow over time 43, optimum 51."""
        fly_map = read_map(MAPS_DIR / "challenge/04_city_grid.txt")
        self.assertEqual(simple_bound(fly_map), 29)
        self.assertEqual(lower_bound(fly_map), 43)

    def test_huge_maps_fall_back(self) -> None:
        """Too big for the flow: the simple bound is used."""
        path = MAPS_DIR / "challenge/04_city_grid.txt"
        self.assertIsNone(flow_bound(read_map(path), 1, max_nodes=10))

    def test_single_exit_from_the_start(self) -> None:
        """One drone per turn leaves the start: n - 1 + distance."""
        text = ("nb_drones: 25\nstart_hub: s 0 0\nhub: a 1 0\nhub: b 2 0 "
                "[max_drones=9]\nend_hub: e 3 0\nconnection: s-a\n"
                "connection: a-b [max_link_capacity=9]\n"
                "connection: b-e [max_link_capacity=9]\n")
        self.assertEqual(lower_bound(parse_map(text)), 24 + 3)

    def test_end_side_and_unsolvable(self) -> None:
        """A narrow entrance to the end; no route at all."""
        text = ("nb_drones: 6\nstart_hub: s 0 0\nhub: a 1 0 [max_drones=3]\n"
                "end_hub: e 2 0\nconnection: s-a [max_link_capacity=3]\n"
                "connection: a-e\n")
        self.assertEqual(lower_bound(parse_map(text)), 2 + 6 - 1)
        blocked = text.replace("[max_drones=3]", "[zone=blocked]")
        self.assertIsNone(lower_bound(parse_map(blocked)))


if __name__ == "__main__":
    unittest.main()
