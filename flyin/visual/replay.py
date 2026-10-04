"""Turn any program's output into something the GUI can play.

The GUI was written for a solver whose output is always valid. Programs
under test are not, so this module is the adaptive layer in between:

* drone ids may start at 0 or at 1 (the base is detected);
* banners and other text around the turn lines are ignored;
* tokens the GUI cannot draw (unknown zone, unknown drone, a drone that
  acts twice in one turn, a malformed token) are left out and reported;
* everything else is shown as written, *including* rule violations (an
  overfull zone, a missing connection), so you can watch the mistake
  happen. The checker's verdict is attached to the replay.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from flyin.tester.checker import CheckResult, check_solution
from flyin.tester.mapfile import FlyMap
from flyin.tester.runner import extract_turns
from flyin.visual.loader import graph_from_map
from flyin.visual.models import Move, SimulationResult, TurnRecord

TOKEN = re.compile(r"^D(\d+)-(\S+)$")


@dataclass
class Replay:
    """A playable result plus what was wrong with the output.

    Attributes:
        result: What the GUI plays.
        check: The checker's verdict on the original lines.
        skipped: Tokens that were left out because they cannot be drawn.
    """

    result: SimulationResult
    check: CheckResult
    skipped: List[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        """Return True if the checker accepts the output."""
        return self.check.valid


def detect_id_base(lines: List[str]) -> int:
    """Return 0 if any drone is called ``D0``, else 1."""
    for line in lines:
        for token in line.split():
            match = TOKEN.match(token)
            if match is not None and int(match.group(1)) == 0:
                return 0
    return 1


def _place(fly_map: FlyMap, parts: List[str]) -> Optional[str]:
    """Return the GUI place of a token's target, or None if not drawable.

    ``['zone']`` is a zone; ``['a', 'b']`` is a flight over ``a-b``.
    """
    if len(parts) == 1 and parts[0] in fly_map.zones:
        return parts[0]
    if (len(parts) == 2 and parts[0] != parts[1]
            and all(name in fly_map.zones for name in parts)):
        return f"{parts[0]}-{parts[1]}"
    return None


def build_replay(fly_map: FlyMap, text: str, raw: bool = False) -> Replay:
    """Build a replay of ``text`` (a program's output) on ``fly_map``.

    Args:
        fly_map: The map the output belongs to.
        text: The output; non-turn lines are ignored unless ``raw``.
        raw: Treat every line as a turn (like ``check --raw``).
    """
    lines = text.splitlines() if raw else extract_turns(text)[0]
    check = check_solution(fly_map, lines)
    base = detect_id_base(lines)
    ids = range(base, base + fly_map.nb_drones)
    delivered: Dict[int, bool] = {drone: False for drone in ids}
    skipped: List[str] = []
    turns: List[TurnRecord] = []
    for number, line in enumerate(lines, 1):
        moves: Dict[int, Move] = {}
        for token in line.split():
            match = TOKEN.match(token)
            place = None if match is None else \
                _place(fly_map, match.group(2).split("-"))
            drone = -1 if match is None else int(match.group(1))
            reason = ("malformed or unknown zone" if place is None
                      else "unknown drone" if drone not in delivered
                      else "acts twice" if drone in moves
                      else "already delivered" if delivered[drone]
                      else "")
            if reason:
                skipped.append(f"turn {number}: {token} ({reason})")
                continue
            moves[drone] = Move(drone, str(place))
            delivered[drone] = place == fly_map.end
        turns.append(TurnRecord(number, [moves[d] for d in sorted(moves)]))
    graph = graph_from_map(fly_map)
    return Replay(SimulationResult(graph, turns, base), check, skipped)
