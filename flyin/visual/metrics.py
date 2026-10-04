"""Secondary metrics of a run: moves per turn, arrivals, path cost."""

from typing import Dict

from flyin.visual.models import SimulationResult


class SimulationMetrics:
    """Secondary metrics of a simulation run (subject chapter VII.6)."""

    def __init__(self, result: SimulationResult) -> None:
        """Compute all metrics once from ``result``."""
        self.turn_count: int = result.turn_count
        self.total_moves: int = sum(len(t.moves) for t in result.turns)
        self.arrival_turns: Dict[int, int] = self._arrivals(result)
        self.path_cost: int = self._path_cost(result)

    @property
    def moves_per_turn(self) -> float:
        """Return the average number of moves (drone steps) per turn."""
        if self.turn_count == 0:
            return 0.0
        return self.total_moves / self.turn_count

    @property
    def turns_per_drone(self) -> float:
        """Return the average turn in which a drone was delivered."""
        if not self.arrival_turns:
            return 0.0
        return sum(self.arrival_turns.values()) / len(self.arrival_turns)

    @staticmethod
    def _arrivals(result: SimulationResult) -> Dict[int, int]:
        """Map every delivered drone id to the turn it reached the end."""
        end = result.graph.end.name
        arrivals: Dict[int, int] = {}
        for record in result.turns:
            for move in record.moves:
                if move.target == end:
                    arrivals.setdefault(move.drone_id, record.number)
        return arrivals

    @staticmethod
    def _path_cost(result: SimulationResult) -> int:
        """Sum the cost of every completed movement.

        A move into a zone costs that zone's ``move_cost``. The first half
        of a restricted flight (target ``"<from>-<to>"``) costs nothing on
        its own, because the arrival move already counts 2.
        """
        graph = result.graph
        cost = 0
        for record in result.turns:
            for move in record.moves:
                if graph.has_zone(move.target):
                    cost += graph.zone(move.target).move_cost
        return cost
