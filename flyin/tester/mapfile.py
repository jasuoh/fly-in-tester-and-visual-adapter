"""A small, independent reader for *valid* Fly-In map files.

This is deliberately separate from any student's parser: the checker must
not trust the program it is checking. It only has to understand correct
maps, so it is tolerant (whitespace, inline comments) and raises
``MapError`` for anything it cannot make sense of.
"""

import heapq
import re
from dataclasses import dataclass, field
from pathlib import Path

ZONE_TYPES = ("normal", "blocked", "restricted", "priority")
COST = {"normal": 1, "priority": 1, "restricted": 2}


class MapError(ValueError):
    """Raised when a map file cannot be understood."""


@dataclass(frozen=True)
class Zone:
    """A zone of the network."""

    name: str
    x: int
    y: int
    kind: str = "normal"
    max_drones: int = 1
    color: str | None = None


@dataclass(frozen=True)
class Link:
    """An undirected connection between two zones."""

    a: str
    b: str
    capacity: int = 1


@dataclass
class FlyMap:
    """A parsed map."""

    nb_drones: int
    start: str
    end: str
    zones: dict[str, Zone] = field(default_factory=dict)
    links: dict[frozenset[str], Link] = field(default_factory=dict)

    def neighbors(self, name: str) -> list[str]:
        """Return the zones directly connected to ``name``."""
        result = []
        for link in self.links.values():
            if link.a == name:
                result.append(link.b)
            elif link.b == name:
                result.append(link.a)
        return result


def _metadata(rest: str) -> tuple[str, dict[str, str]]:
    """Split ``rest`` into the text before ``[...]`` and its key/values."""
    match = re.search(r"\[(.*?)\]", rest)
    if match is None:
        return rest, {}
    values: dict[str, str] = {}
    for token in match.group(1).split():
        key, sep, value = token.partition("=")
        if not sep:
            raise MapError(f"bad metadata token {token!r}")
        values[key] = value
    return rest[: match.start()], values


def parse_map(text: str) -> FlyMap:
    """Parse the text of a valid map file."""
    nb_drones = 0
    start = end = ""
    zones: dict[str, Zone] = {}
    links: dict[frozenset[str], Link] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split(" #")[0].strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        key, sep, rest = line.partition(":")
        key = key.strip()
        if not sep:
            raise MapError(f"line {number}: missing ':'")
        try:
            if key == "nb_drones":
                nb_drones = int(rest.strip())
            elif key in ("start_hub", "end_hub", "hub"):
                head, meta = _metadata(rest)
                name, x, y = head.split()
                kind = meta.get("zone", "normal")
                if kind not in ZONE_TYPES:
                    raise MapError(f"unknown zone type {kind!r}")
                zones[name] = Zone(
                    name, int(x), int(y), kind,
                    int(meta.get("max_drones", 1)), meta.get("color"),
                )
                if key == "start_hub":
                    start = name
                elif key == "end_hub":
                    end = name
            elif key == "connection":
                head, meta = _metadata(rest)
                a, b = head.strip().split("-")
                links[frozenset((a, b))] = Link(
                    a, b, int(meta.get("max_link_capacity", 1))
                )
            else:
                raise MapError(f"unknown key {key!r}")
        except ValueError as error:
            raise MapError(f"line {number}: {error}") from error
    if not (nb_drones and start and end):
        raise MapError("nb_drones, start_hub and end_hub are required")
    return FlyMap(nb_drones, start, end, zones, links)


def read_map(path: str | Path) -> FlyMap:
    """Read and parse the map file at ``path``."""
    return parse_map(Path(path).read_text(encoding="utf-8"))


def shortest_cost(fly_map: FlyMap) -> int | None:
    """Return the minimum number of turns one drone needs, or None.

    None means the end zone cannot be reached without entering a blocked
    zone, i.e. the map has no solution.
    """
    if fly_map.zones[fly_map.start].kind == "blocked":
        return None
    best = {fly_map.start: 0}
    queue = [(0, fly_map.start)]
    while queue:
        cost, name = heapq.heappop(queue)
        if name == fly_map.end:
            return cost
        if cost > best.get(name, cost):
            continue
        for other in fly_map.neighbors(name):
            kind = fly_map.zones[other].kind
            if kind == "blocked":
                continue
            new_cost = cost + COST[kind]
            if new_cost < best.get(other, new_cost + 1):
                best[other] = new_cost
                heapq.heappush(queue, (new_cost, other))
    return None


def has_route(fly_map: FlyMap) -> bool:
    """Return whether the end zone is reachable from the start zone."""
    return shortest_cost(fly_map) is not None
