"""Window regions and the map-to-screen projection."""

import math
from typing import Dict, List, Tuple

import pygame

from flyin.visual.models import Graph

Point = Tuple[float, float]


class ScreenLayout:
    """Split the window into map area, timeline bar and side panel.

    Why: every renderer asks the layout for its rectangle and for
    scaled pixel sizes (``px``), so the GUI looks the same at 800x500
    and at 1920x1080.
    """

    def __init__(self, size: Tuple[int, int]) -> None:
        """Compute all rectangles for a window of ``size`` pixels."""
        width, height = max(320, size[0]), max(240, size[1])
        self.size: Tuple[int, int] = (width, height)
        self.scale: float = max(0.68, min(1.5, min(width / 1600,
                                                   height / 900)))
        panel_width = round(max(236 * self.scale,
                                min(440 * self.scale, width * 0.25)))
        panel_width = max(200, panel_width)
        self.panel: pygame.Rect = pygame.Rect(width - panel_width, 0,
                                              panel_width, height)
        bar = round(64 * self.scale)
        self.timeline: pygame.Rect = pygame.Rect(
            round(28 * self.scale), height - bar,
            self.panel.left - round(56 * self.scale), bar)
        self.map: pygame.Rect = pygame.Rect(0, 0, self.panel.left,
                                            height - bar)

    def px(self, value: float) -> int:
        """Return ``value`` design pixels scaled to the window."""
        return max(1, round(value * self.scale))


class Projection:
    """Map zone coordinates to screen positions inside a rectangle.

    Why independent axis scales: maps like the challenger are 22 units
    wide and 4 high. A limited stretch uses the window height without
    distorting the topology beyond recognition.
    """

    MAX_STRETCH: float = 3.2

    def __init__(self, graph: Graph, area: pygame.Rect, scale: float
                 ) -> None:
        """Fit all zones of ``graph`` into ``area``."""
        self.positions: Dict[str, Point] = {}
        self.spacing: float = 1.0
        self._fit(graph, area)
        self.radius: float = max(7 * scale,
                                 min(24 * scale, self.spacing * 0.24))

    def _fit(self, graph: Graph, area: pygame.Rect) -> None:
        """Compute positions and the smallest distance between zones."""
        zones = graph.zones
        xs = [zone.x for zone in zones]
        ys = [zone.y for zone in zones]
        x_range, y_range = max(xs) - min(xs), max(ys) - min(ys)
        sx = area.width / x_range if x_range else math.inf
        sy = area.height / y_range if y_range else math.inf
        if math.isinf(sx) and math.isinf(sy):
            sx = sy = 1.0
        sx = min(sx, sy * self.MAX_STRETCH)
        sy = min(sy, sx * self.MAX_STRETCH)
        left = area.centerx - x_range * sx / 2
        top = area.centery - y_range * sy / 2
        for zone in zones:
            self.positions[zone.name] = (left + (zone.x - min(xs)) * sx,
                                         top + (zone.y - min(ys)) * sy)
        self.spacing = self._min_distance(list(self.positions.values()),
                                          min(sx, sy, area.width))

    @staticmethod
    def _min_distance(points: List[Point], default: float) -> float:
        """Return the smallest distance between two distinct points."""
        best = default
        for i, (ax, ay) in enumerate(points):
            for bx, by in points[i + 1:]:
                distance = math.hypot(ax - bx, ay - by)
                if 0 < distance < best:
                    best = distance
        return best

    def midpoint(self, a: str, b: str) -> Point:
        """Return the middle of the connection between two zones."""
        (ax, ay), (bx, by) = self.positions[a], self.positions[b]
        return ((ax + bx) / 2, (ay + by) / 2)

    def normal(self, a: str, b: str) -> Point:
        """Return the unit vector perpendicular to the connection a-b."""
        (ax, ay), (bx, by) = self.positions[a], self.positions[b]
        length = math.hypot(bx - ax, by - ay) or 1.0
        return (-(by - ay) / length, (bx - ax) / length)
