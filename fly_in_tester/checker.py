"""Verify that a turn log is a valid solution for a map.

Rules checked (all from the subject):

* every line is one turn; a token is ``D<id>-<zone>`` or, for a drone that
  starts a two-turn flight to a restricted zone, ``D<id>-<from>-<to>``;
* a drone acts at most once per turn and must land in the *next* turn;
* moves follow connections, never enter blocked zones, and restricted zones
  are only entered by the two-turn flight;
* a zone holds at most ``max_drones`` drones at the end of a turn (start and
  end are unlimited, drones leaving free space in the same turn);
* a connection carries at most ``max_link_capacity`` drones per turn; only
  departures count, a drone landing from a flight frees its connection in
  the same turn (like a drone leaving a zone);
* drones that reached the end zone do not move again;
* at the end every drone is in the end zone and there are no empty turns.

Drone ids may start at 0 or at 1.
"""

import re
from dataclasses import dataclass, field

from .mapfile import FlyMap

TOKEN = re.compile(r"^D(\d+)-(\S+)$")
MAX_ERRORS = 30


@dataclass
class CheckResult:
    """Outcome of checking a solution."""

    turns: int
    moves: int = 0
    id_base: int | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        """Return True if no rule was violated."""
        return not self.errors


@dataclass
class _Drone:
    """State of one drone while replaying the log."""

    zone: str | None
    flight: tuple[str, int] | None = None


def _split(token: str) -> tuple[int, list[str]] | None:
    """Split ``D3-a-b`` into ``(3, ['a', 'b'])`` or return None."""
    match = TOKEN.match(token)
    if match is None:
        return None
    return int(match.group(1)), match.group(2).split("-")


def check_solution(fly_map: FlyMap, log: list[str]) -> CheckResult:
    """Replay ``log`` on ``fly_map`` and report every rule violation."""
    result = CheckResult(turns=len(log))
    errors = result.errors

    def fail(turn: int, message: str) -> None:
        if len(errors) < MAX_ERRORS:
            errors.append(f"turn {turn}: {message}" if turn else message)

    parsed: list[list[tuple[str, int, list[str]]]] = []
    ids: set[int] = set()
    for turn, line in enumerate(log, 1):
        tokens = []
        if not line.strip():
            fail(turn, "empty line (a turn without any movement)")
        for token in line.split():
            split = _split(token)
            if split is None:
                fail(turn, f"malformed token {token!r}")
                continue
            ids.add(split[0])
            tokens.append((token, split[0], split[1]))
        parsed.append(tokens)
    if not ids:
        fail(0, "the output contains no movements")
        return result
    base = min(ids)
    result.id_base = base
    expected = set(range(base, base + fly_map.nb_drones))
    if base not in (0, 1) or ids != expected:
        fail(0, f"drone ids {sorted(ids)} do not match {fly_map.nb_drones} "
                "drones numbered from 0 or from 1")

    drones = {i: _Drone(fly_map.start) for i in range(fly_map.nb_drones)}
    for turn, tokens in enumerate(parsed, 1):
        acted: set[int] = set()
        link_use: dict[frozenset[str], int] = {}
        for token, drone_id, parts in tokens:
            result.moves += 1
            drone = drones.get(drone_id - base)
            if drone is None:
                continue
            if drone_id in acted:
                fail(turn, f"D{drone_id} acts twice")
                continue
            acted.add(drone_id)
            if drone.flight is not None:
                target, arrival = drone.flight
                if len(parts) != 1 or parts[0] != target or arrival != turn:
                    fail(turn, f"{token}: D{drone_id} must land in {target} "
                               f"in turn {arrival}")
                drone.zone, drone.flight = target, None
                continue
            if drone.zone == fly_map.end:
                fail(turn, f"{token}: D{drone_id} moves after being delivered")
                continue
            origin: str | None
            if len(parts) == 2:
                origin, target = parts
                kind_required = True
            elif len(parts) == 1:
                origin, target = drone.zone, parts[0]
                kind_required = False
            else:
                fail(turn, f"{token}: malformed movement")
                continue
            if origin != drone.zone:
                fail(turn, f"{token}: D{drone_id} is in {drone.zone}, "
                           f"not in {origin}")
                continue
            link_key = frozenset((str(origin), target))
            if target not in fly_map.zones or link_key not in fly_map.links:
                fail(turn, f"{token}: no connection {origin}-{target}")
                continue
            kind = fly_map.zones[target].kind
            if kind == "blocked":
                fail(turn, f"{token}: {target} is blocked")
            elif kind == "restricted" and not kind_required:
                fail(turn, f"{token}: {target} is restricted, so the move "
                           f"needs the form D{drone_id}-{origin}-{target}")
            elif kind != "restricted" and kind_required:
                fail(turn, f"{token}: {target} is not restricted, so the "
                           f"connection form is wrong")
            link_use[link_key] = link_use.get(link_key, 0) + 1
            if kind == "restricted":
                drone.zone, drone.flight = None, (target, turn + 1)
            else:
                drone.zone = target
        for drone_id, drone in drones.items():
            if drone.flight is not None and drone.flight[1] <= turn:
                fail(turn, f"D{drone_id + base} did not land in "
                           f"{drone.flight[0]} as required")
                drone.zone, drone.flight = drone.flight[0], None
        for link_key, used in link_use.items():
            capacity = fly_map.links[link_key].capacity
            if used > capacity:
                names = "-".join(sorted(link_key))
                fail(turn, f"connection {names} carries {used} drones "
                           f"(max_link_capacity {capacity})")
        occupancy: dict[str, int] = {}
        for drone in drones.values():
            if drone.zone is not None:
                occupancy[drone.zone] = occupancy.get(drone.zone, 0) + 1
        for name, count in occupancy.items():
            if name in (fly_map.start, fly_map.end):
                continue
            if count > fly_map.zones[name].max_drones:
                fail(turn, f"zone {name} holds {count} drones "
                           f"(max_drones {fly_map.zones[name].max_drones})")
    for drone_id, drone in drones.items():
        if drone.zone != fly_map.end:
            where = drone.zone or "in flight"
            fail(0, f"D{drone_id + base} did not reach {fly_map.end} "
                    f"(ends in {where})")
    return result
