"""Tests for the independent map reader."""

import unittest

from fly_in_tester.mapfile import MapError, has_route, parse_map, shortest_cost

BASE = """# demo
nb_drones: 2
start_hub: s 0 0 [color=green]
hub: a 1 0 [zone=priority max_drones=3 color=blue]
hub: r 1 1 [zone=restricted]
end_hub: g 2 0
connection: s-a [max_link_capacity=4]
connection: a-g
connection: s-r
connection: r-g
"""


class ParseTests(unittest.TestCase):
    """Parsing of valid maps."""

    def test_zones_and_links(self) -> None:
        """Zones, types, capacities and links are read."""
        fly_map = parse_map(BASE)
        self.assertEqual((fly_map.nb_drones, fly_map.start, fly_map.end),
                         (2, "s", "g"))
        self.assertEqual(fly_map.zones["a"].kind, "priority")
        self.assertEqual(fly_map.zones["a"].max_drones, 3)
        self.assertEqual(fly_map.zones["r"].kind, "restricted")
        self.assertEqual(fly_map.zones["s"].max_drones, 1)
        self.assertEqual(fly_map.links[frozenset(("s", "a"))].capacity, 4)
        self.assertEqual(fly_map.links[frozenset(("a", "g"))].capacity, 1)
        self.assertCountEqual(fly_map.neighbors("s"), ["a", "r"])

    def test_comments_crlf_and_bom(self) -> None:
        """Comments, CRLF and a BOM are tolerated."""
        text = "﻿" + BASE.replace("\n", "\r\n") + "  # tail\n"
        self.assertEqual(parse_map(text).nb_drones, 2)

    def test_errors(self) -> None:
        """Unreadable maps raise MapError."""
        for text in ("", "nb_drones: x\n", BASE + "foo: bar\n",
                     BASE.replace("[zone=priority", "[zone=lava"),
                     BASE.replace("nb_drones: 2\n", "")):
            with self.subTest(text=text[:30]):
                with self.assertRaises(MapError):
                    parse_map(text)


class RouteTests(unittest.TestCase):
    """Reachability and shortest cost."""

    def test_costs(self) -> None:
        """A restricted zone costs two turns, priority one."""
        self.assertEqual(shortest_cost(parse_map(BASE)), 2)
        only_restricted = BASE.replace("connection: s-a [max_link_capacity=4]",
                                       "").replace("connection: a-g", "")
        self.assertEqual(shortest_cost(parse_map(only_restricted)), 3)

    def test_blocked_zones_are_never_entered(self) -> None:
        """A route through a blocked zone does not count."""
        text = BASE.replace("[zone=restricted]", "[zone=blocked]").replace(
            "[zone=priority max_drones=3 color=blue]", "[zone=blocked]")
        self.assertFalse(has_route(parse_map(text)))

    def test_blocked_start_or_end(self) -> None:
        """A blocked start or end has no route."""
        for old, new in (("start_hub: s 0 0 [color=green]",
                          "start_hub: s 0 0 [zone=blocked]"),
                         ("end_hub: g 2 0", "end_hub: g 2 0 [zone=blocked]")):
            with self.subTest(hub=old):
                self.assertFalse(has_route(parse_map(BASE.replace(old, new))))

    def test_disconnected(self) -> None:
        """Without connections there is no route."""
        text = "\n".join(line for line in BASE.splitlines()
                         if not line.startswith("connection"))
        self.assertFalse(has_route(parse_map(text)))


if __name__ == "__main__":
    unittest.main()
