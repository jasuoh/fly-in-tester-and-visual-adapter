"""Drone states before and after every turn, built on demand."""

from bisect import bisect_right, insort
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Set, Tuple, TypeVar

from flyin.visual.models import Issue, SimulationResult
from flyin.visual.metrics import SimulationMetrics

Edge = FrozenSet[str]
State = Dict[int, str]
Value = TypeVar("Value")


@dataclass(frozen=True)
class StateCounts:
    """How many drones are where in one state."""

    waiting: int
    en_route: int
    transit: int
    delivered: int


class Timeline:
    """Replay the moves of a result into drone states, lazily.

    ``state(k)`` maps every drone id to its place after ``k`` turns
    (``state(0)``: everybody in the start zone). A place is a zone name
    or ``"<from>-<to>"`` while flying towards a restricted zone.

    Why lazy: a run with 10 000 drones can have 10 000 turns, so storing
    every state would need 10^8 entries. Instead the state after turn
    ``k`` is the state before it plus the moves of turn ``k`` (a move's
    target *is* the new place). We keep a snapshot every
    ``CHECKPOINT_EVERY`` turns and a few recent states, so any state is
    at most 64 turns of moves away. Cost: O(moves) per replayed turn;
    memory O(drones * turns / 64).
    """

    CHECKPOINT_EVERY: int = 64
    CACHE_SIZE: int = 8

    def __init__(self, result: SimulationResult) -> None:
        """Prepare the replay (only state 0 is built now)."""
        self.result: SimulationResult = result
        graph = result.graph
        self.start: str = graph.start.name
        self.end: str = graph.end.name
        self.drone_count: int = graph.nb_drones
        self.move_counts: List[int] = [len(t.moves) for t in result.turns]
        self.metrics: SimulationMetrics = SimulationMetrics(result)
        first = result.id_base
        initial: State = {d: self.start
                          for d in range(first, first + graph.nb_drones)}
        self._checkpoints: Dict[int, State] = {0: initial}
        self._checkpoint_keys: List[int] = [0]
        self._states: "OrderedDict[int, State]" = OrderedDict()
        self._groups: "OrderedDict[int, Dict[str, List[int]]]" = \
            OrderedDict()
        self._counts: Dict[int, StateCounts] = {}
        self._edges: Dict[int, Set[Edge]] = {}

    @property
    def turn_count(self) -> int:
        """Return the number of turns."""
        return len(self.result.turns)

    def clamp(self, turn_index: int) -> int:
        """Return a valid turn index (0 when there are no turns)."""
        return max(0, min(turn_index, self.turn_count - 1))

    # states -------------------------------------------------------------

    def state(self, k: int) -> State:
        """Return the drone places after ``k`` turns (clamped, cached)."""
        k = max(0, min(k, self.turn_count))
        if k in self._checkpoints:
            return self._checkpoints[k]
        if k in self._states:
            self._states.move_to_end(k)
            return self._states[k]
        base, state = self._closest_before(k)
        state = dict(state)
        for turn in range(base, k):
            for move in self.result.turns[turn].moves:
                state[move.drone_id] = move.target
            self._maybe_checkpoint(turn + 1, state)
        self._remember(self._states, k, state)
        return state

    def _closest_before(self, k: int) -> Tuple[int, State]:
        """Return the nearest known state at or before ``k``."""
        index = self._checkpoint_keys[
            bisect_right(self._checkpoint_keys, k) - 1]
        cached = [j for j in self._states if index < j <= k]
        if cached:
            return max(cached), self._states[max(cached)]
        return index, self._checkpoints[index]

    def _maybe_checkpoint(self, k: int, state: State) -> None:
        """Keep a snapshot every ``CHECKPOINT_EVERY`` turns."""
        if k % self.CHECKPOINT_EVERY == 0 and k not in self._checkpoints:
            self._checkpoints[k] = dict(state)
            insort(self._checkpoint_keys, k)

    def _remember(self, cache: "OrderedDict[int, Value]", key: int,
                  value: Value) -> None:
        """Store ``value`` in a small least-recently-used cache."""
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > self.CACHE_SIZE:
            cache.popitem(last=False)

    def shown_index(self, turn_index: int, progress: float) -> int:
        """Return the state the counters show: it flips at half time."""
        index = self.clamp(turn_index)
        if self.turn_count and progress >= 0.5:
            return index + 1
        return index

    def shown(self, turn_index: int, progress: float) -> State:
        """Return the state shown by the counters (see shown_index)."""
        return self.state(self.shown_index(turn_index, progress))

    # derived data -------------------------------------------------------

    def groups(self, k: int) -> Dict[str, List[int]]:
        """Return the drones of state ``k`` grouped by place (cached).

        States keep the id order of state 0, so groups come out sorted.
        """
        k = max(0, min(k, self.turn_count))
        if k in self._groups:
            self._groups.move_to_end(k)
            return self._groups[k]
        groups: Dict[str, List[int]] = {}
        for drone, place in self.state(k).items():
            groups.setdefault(place, []).append(drone)
        self._remember(self._groups, k, groups)
        return groups

    def counts(self, k: int) -> StateCounts:
        """Return waiting / en route / in transit / delivered counts."""
        k = max(0, min(k, self.turn_count))
        if k not in self._counts:
            groups = self.groups(k)
            waiting = len(groups.get(self.start, []))
            delivered = len(groups.get(self.end, []))
            transit = sum(len(ids) for place, ids in groups.items()
                          if self.is_transit(place))
            self._counts[k] = StateCounts(
                waiting, self.drone_count - waiting - delivered, transit,
                delivered)
        return self._counts[k]

    def occupancy(self, k: int, place: str) -> int:
        """Return how many drones are at ``place`` in state ``k``."""
        return len(self.groups(k).get(place, []))

    def delivered(self, state: State) -> int:
        """Return how many drones of ``state`` are in the end zone."""
        return sum(1 for place in state.values() if place == self.end)

    def movers(self, turn_index: int) -> List[int]:
        """Return the ids of the drones that move in a turn."""
        if 0 <= turn_index < self.turn_count:
            return [m.drone_id for m in self.result.turns[turn_index].moves]
        return []

    def edges(self, turn_index: int) -> Set[Edge]:
        """Return the connections used during a turn (empty if invalid)."""
        if not 0 <= turn_index < self.turn_count:
            return set()
        if turn_index not in self._edges:
            before = self.state(turn_index)
            used: Set[Edge] = set()
            for move in self.result.turns[turn_index].moves:
                edge = self.edge_of(before.get(move.drone_id, self.start),
                                    move.target)
                if edge is not None:
                    used.add(frozenset(edge))
            self._edges[turn_index] = used
        return self._edges[turn_index]

    def move_profile(self, slots: int) -> List[int]:
        """Return the moves per turn squeezed into at most ``slots`` bars.

        Each bar shows the maximum of the turns it covers.
        """
        counts, total = self.move_counts, len(self.move_counts)
        slots = max(1, min(slots, total))
        return [max(counts[i * total // slots:
                           max(i * total // slots + 1,
                               (i + 1) * total // slots)])
                for i in range(slots)] if total else []

    # problems -----------------------------------------------------------

    def issues_at(self, k: int) -> List[Issue]:
        """Return the broken rules of the state after ``k`` turns."""
        return [i for i in self.result.issues if i.turn == k and k > 0]

    def issue_turns(self) -> List[int]:
        """Return the turns with a broken rule, sorted."""
        return sorted({i.turn for i in self.result.issues if i.turn > 0})

    # places -------------------------------------------------------------

    @staticmethod
    def is_transit(place: str) -> bool:
        """Return True for a ``"<from>-<to>"`` place."""
        return "-" in place

    @staticmethod
    def split(place: str) -> Tuple[str, str]:
        """Split a transit place into its two zone names."""
        source, _, destination = place.partition("-")
        return source, destination

    @classmethod
    def edge_of(cls, start: str, stop: str) -> Optional[Tuple[str, str]]:
        """Return the connection a drone uses between two places."""
        if start == stop:
            return None
        if cls.is_transit(start):
            return cls.split(start)
        if cls.is_transit(stop):
            return cls.split(stop)
        return (start, stop)
