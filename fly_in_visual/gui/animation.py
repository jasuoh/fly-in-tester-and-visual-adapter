"""Drone states -> smooth positions and fades for any instant.

The playback position is ``turn_index + progress``. ``progress`` 0 is the
state before the turn, 1 the state after it. Everything here is a pure
function of that position, so pausing, stepping and scrubbing always
land on exactly the same picture as continuous playback.
"""

import math
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Tuple

from fly_in_visual.gui.layout import Projection
from fly_in_visual.gui.timeline import Timeline
from fly_in_visual.models import Graph

Point = Tuple[float, float]
Edge = FrozenSet[str]


class Easing:
    """The one easing curve used for every movement and fade."""

    @staticmethod
    def ease(t: float) -> float:
        """Cubic ease-in-out of ``t`` in 0..1 (slow start and end)."""
        t = max(0.0, min(1.0, t))
        if t < 0.5:
            return 4 * t * t * t
        return 1 - (-2 * t + 2) ** 3 / 2

    @staticmethod
    def window(start: float, stop: float, t: float) -> float:
        """Return 0 before ``start``, 1 after ``stop``, eased in between."""
        if stop <= start:
            return 1.0 if t >= stop else 0.0
        return Easing.ease((t - start) / (stop - start))

    @staticmethod
    def lerp(a: Point, b: Point, t: float) -> Point:
        """Return the point at ``t`` (0..1) on the segment a-b."""
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


@dataclass
class DroneSprite:
    """Where and how to draw one drone in a frame.

    ``heading`` is the horizontal direction of travel (-1, 0 or 1),
    ``arriving`` marks a drone reaching the goal in this turn and
    ``transit`` a drone on its way to a restricted zone.
    """

    drone_id: int
    point: Point
    scale: float
    opacity: float
    moving: bool
    heading: int = 0
    arriving: bool = False
    transit: bool = False


class Choreography:
    """Compute drone positions, fades and highlight strengths.

    Rules (all driven by :class:`Easing`):

    * a normal move eases from the old slot to the new slot in one turn;
    * a restricted flight is one continuous movement over two turns that
      passes the middle of the connection exactly at the turn boundary;
    * drones sharing a zone sit on a small ring; when the group changes
      every drone glides from its old slot to its new one;
    * leaving the start fades/scales in, reaching the goal fades out.
    """

    def __init__(self, timeline: Timeline, projection: Projection,
                 graph: Graph, drone_radius: float) -> None:
        """Bind the choreography to the data and the screen geometry."""
        self.timeline: Timeline = timeline
        self.projection: Projection = projection
        self.graph: Graph = graph
        self.drone_radius: float = drone_radius

    # drones -------------------------------------------------------------

    def sprites(self, turn_index: int, progress: float) -> List[DroneSprite]:
        """Return every visible drone; moving drones come last (on top)."""
        timeline = self.timeline
        if timeline.turn_count == 0:
            return []
        t = timeline.clamp(turn_index)
        p = max(0.0, min(1.0, progress))
        before, after = timeline.state(t), timeline.state(t + 1)
        resting: List[DroneSprite] = []
        moving: List[DroneSprite] = []
        for drone in self._active(t):
            old, new = before[drone], after[drone]
            if old == timeline.end or (old == new == timeline.start):
                continue
            point = self._position(t, drone, p)
            ahead = self._position(t, drone, min(1.0, p + 0.05))
            heading = 0 if abs(ahead[0] - point[0]) < 0.01 else (
                1 if ahead[0] > point[0] else -1)
            sprite = DroneSprite(
                drone, point, 1.0, 1.0, old != new, heading,
                new == timeline.end and old != new,
                timeline.is_transit(old) or timeline.is_transit(new))
            self._fade(sprite, old, new, p)
            (moving if sprite.moving else resting).append(sprite)
        return resting + moving

    def _active(self, t: int) -> List[int]:
        """Return the drones worth drawing in turn ``t``, sorted by id.

        Only drones that move or rest outside start and goal; with
        thousands of drones waiting in the start this keeps every frame
        cheap.
        """
        timeline = self.timeline
        active = set(timeline.movers(t))
        for place, drones in timeline.groups(t).items():
            if place not in (timeline.start, timeline.end):
                active.update(drones)
        return sorted(active)

    def _fade(self, sprite: DroneSprite, old: str, new: str,
              p: float) -> None:
        """Scale/fade drones leaving the start or reaching the goal."""
        if old == self.timeline.start:
            grow = Easing.window(0.0, 0.35, p)
            sprite.scale, sprite.opacity = 0.5 + 0.5 * grow, grow
        if new == self.timeline.end:
            shrink = Easing.window(0.65, 1.0, p)
            sprite.scale = sprite.scale * (1 - 0.5 * shrink)
            sprite.opacity = sprite.opacity * (1 - shrink)

    def _position(self, t: int, drone: int, p: float) -> Point:
        """Return the drone position at ``t + p``."""
        timeline = self.timeline
        old, new = timeline.state(t)[drone], timeline.state(t + 1)[drone]
        if timeline.is_transit(new) and not timeline.is_transit(old):
            return self._flight(t, drone, Easing.ease(p / 2))
        if timeline.is_transit(old) and not timeline.is_transit(new):
            return self._flight(t - 1, drone, Easing.ease((1 + p) / 2))
        return Easing.lerp(self.slot(t, drone), self.slot(t + 1, drone),
                           Easing.ease(p))

    def _flight(self, first: int, drone: int, s: float) -> Point:
        """Position on a two-turn restricted flight starting in ``first``.

        ``s`` runs 0..1 over both turns; at 0.5 (the turn boundary) the
        drone is exactly on its transit slot in the middle of the edge.
        """
        origin = self.slot(first, drone)
        middle = self.slot(first + 1, drone)
        target = self.slot(first + 2, drone)
        if s <= 0.5:
            return Easing.lerp(origin, middle, s * 2)
        return Easing.lerp(middle, target, (s - 0.5) * 2)

    def slot(self, k: int, drone: int) -> Point:
        """Return where ``drone`` rests in state ``k``.

        Several drones in one zone sit on a ring big enough that markers
        never overlap; drones in transit sit side by side across the
        middle of their connection.
        """
        place = self.timeline.state(k)[drone]
        if self.timeline.is_transit(place):
            a, b = self.timeline.split(place)
            group = self.timeline.groups(k)[place]
            x, y = self.projection.midpoint(a, b)
            nx, ny = self.projection.normal(a, b)
            offset = (group.index(drone) - (len(group) - 1) / 2) \
                * self.drone_radius * 2.3
            return (x + nx * offset, y + ny * offset)
        x, y = self.projection.positions[place]
        if self.graph.zone(place).has_unlimited_capacity:
            return (x, y)
        group = self.timeline.groups(k)[place]
        if len(group) == 1:
            return (x, y)
        count = len(group)
        ring = max(self.projection.radius * 0.5,
                   self.drone_radius * 1.15 / math.sin(math.pi / count))
        angle = -math.pi / 2 + group.index(drone) * 2 * math.pi / count
        return (x + math.cos(angle) * ring, y + math.sin(angle) * ring)

    # highlights ---------------------------------------------------------

    def edge_strength(self, turn_index: int, progress: float
                      ) -> Dict[Edge, float]:
        """Return 0..1 highlight strength of every used connection.

        A connection fades in at the start of a turn and out at its end,
        unless the neighbouring turn uses it as well (then it stays lit,
        e.g. during a two-turn restricted flight).
        """
        timeline = self.timeline
        if timeline.turn_count == 0:
            return {}
        t = timeline.clamp(turn_index)
        p = max(0.0, min(1.0, progress))
        previous, following = timeline.edges(t - 1), timeline.edges(t + 1)
        strengths: Dict[Edge, float] = {}
        for edge in timeline.edges(t):
            value = 1.0
            if edge not in previous:
                value = min(value, Easing.window(0.0, 0.2, p))
            if edge not in following:
                value = min(value, Easing.window(0.0, 0.2, 1 - p))
            strengths[edge] = value
        return strengths

    @staticmethod
    def occupancy_blend(progress: float) -> float:
        """Return the cross-fade weight between old and new occupancy."""
        return Easing.window(0.3, 0.7, progress)
