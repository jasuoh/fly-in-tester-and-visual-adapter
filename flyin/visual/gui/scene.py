"""The static picture of the network (drawn once per size and theme)."""

import math
from typing import Dict, Optional, Tuple

import pygame

from flyin.visual.gui.ashen import AshenScenery
from flyin.visual.gui.colors import Colors
from flyin.visual.gui.layout import Projection, ScreenLayout
from flyin.visual.gui.painter import Painter, Point
from flyin.visual.gui.sprites import SpriteBook
from flyin.visual.gui.themes import RGB
from flyin.visual.models import Graph, Zone, ZoneType


class MapScene:
    """Background, idle connections, zone bodies and labels.

    Why cached: these parts never change during playback. Drawing them
    once into ``surface`` and copying it per frame keeps 60 fps even on
    maps with many zones; only drones and highlights are redrawn.
    """

    LABEL_ANGLE: float = 32.0

    def __init__(self, graph: Graph, layout: ScreenLayout,
                 painter: Painter) -> None:
        """Fit the map, choose the label style and draw the static layer."""
        self.graph: Graph = graph
        self.layout: ScreenLayout = layout
        self.painter: Painter = painter
        theme = painter.theme
        self.label_role: str = "mono" if theme.mono_labels else "ui"
        self.label_size: int = max(10, layout.px(13))
        self.colors: Dict[str, RGB] = {
            zone.name: Colors.for_zone(zone.color, theme)
            for zone in graph.zones}
        self.label_angle: float = 0.0
        self.sparse_labels: bool = False
        self.sprites: SpriteBook = SpriteBook()
        self.ashen: Optional[AshenScenery] = None
        if theme.art == "ashen":
            self.ashen = AshenScenery(painter, self.sprites)
        self.projection: Projection = self._fit()
        self.surface: pygame.Surface = pygame.Surface(layout.size)
        self._draw_background()
        for connection in graph.connections:
            self._draw_connection(connection.zone_a, connection.zone_b,
                                  connection.max_link_capacity)
        for zone in graph.zones:
            self._draw_zone(zone)
        for zone in graph.zones:
            self._draw_label(zone)

    # fitting ------------------------------------------------------------

    def _fit(self) -> Projection:
        """Fit the map; switch to slanted labels when names collide."""
        px = self.layout.px
        area = self.layout.map.inflate(-2 * px(70), -2 * px(84))
        area.top += px(12)
        projection = Projection(self.graph, area, self.layout.scale)
        if not self._labels_collide(projection):
            return projection
        self.label_angle = self.LABEL_ANGLE
        self.label_size = max(10, self.layout.px(12))
        longest = max(self._label_width(z.name) for z in self.graph.zones)
        angle = math.radians(self.label_angle)
        area.height -= round(longest * math.sin(angle) * 0.85)
        area.width -= round(longest * math.cos(angle) * 0.55)
        slanted = Projection(self.graph, area, self.layout.scale)
        if self._slanted_fit(slanted):
            return slanted
        self.sparse_labels, self.label_angle = True, 0.0
        return projection

    def _slanted_fit(self, projection: Projection) -> bool:
        """Return True if slanted labels keep a calm distance.

        Neighbouring slanted labels run in parallel; their distance is
        ``spacing * sin(angle)``. Below 1.5 line heights the map gets
        cluttered, so only start and goal are labelled and every other
        name is shown in the hover card.
        """
        line = self.painter.fonts.get(self.label_role,
                                      self.label_size).get_height()
        distance = projection.spacing * math.sin(
            math.radians(self.LABEL_ANGLE))
        return distance >= 1.5 * line

    def _label_width(self, name: str) -> int:
        """Return the pixel width of a zone label."""
        font = self.painter.fonts.get(self.label_role, self.label_size)
        return font.size(name)[0]

    def _labels_collide(self, projection: Projection) -> bool:
        """Return True if horizontal labels would overlap a neighbour."""
        positions = projection.positions
        height = self.label_size * 2.4 + projection.radius
        names = list(positions)
        for i, a in enumerate(names):
            ax, ay = positions[a]
            for b in names[i + 1:]:
                bx, by = positions[b]
                if abs(ay - by) > height:
                    continue
                room = abs(ax - bx) - self.layout.px(10)
                if room < (self._label_width(a) + self._label_width(b)) / 2:
                    return True
        return False

    # geometry shared with the dynamic layer -----------------------------

    def edge_points(self, a: str, b: str) -> Tuple[Point, Point]:
        """Return a connection's end points, trimmed to the zone rims."""
        (ax, ay) = self.projection.positions[a]
        (bx, by) = self.projection.positions[b]
        length = math.hypot(bx - ax, by - ay) or 1.0
        trim = min(self.projection.radius + self.layout.px(3), length / 3)
        ux, uy = (bx - ax) / length, (by - ay) / length
        return ((ax + ux * trim, ay + uy * trim),
                (bx - ux * trim, by - uy * trim))

    def edge_width(self, capacity: int) -> float:
        """Return the line width of a connection of ``capacity``."""
        return min(7.0, 1.8 + 1.1 * (capacity - 1)) * self.layout.scale

    def zone_radius(self, zone: Zone) -> float:
        """Return the drawn radius (start and goal are a bit larger)."""
        factor = 1.18 if zone.has_unlimited_capacity else 1.0
        return self.projection.radius * factor

    # static drawing -----------------------------------------------------

    def _draw_background(self) -> None:
        """Fill the gradient and the optional grid."""
        theme, surface = self.painter.theme, self.surface
        width, height = self.layout.size
        for y in range(height):
            color = Colors.mix(theme.background_top, theme.background,
                               y / max(1, height - 1))
            pygame.draw.line(surface, color, (0, y), (width, y))
        if self.ashen is not None:
            self.ashen.background(surface, self.layout.map,
                                  self.layout.scale)
            return
        if theme.grid is None or theme.grid_major is None:
            return
        step, area = self.layout.px(theme.grid_step), self.layout.map
        xs = list(range(area.left, area.right, step))
        ys = list(range(area.top, area.bottom, step))
        if theme.grid_dots:
            for i, x in enumerate(xs):
                for j, y in enumerate(ys):
                    if i % 5 == 0 and j % 5 == 0:
                        pygame.draw.circle(surface, theme.grid_major,
                                           (x, y), 1)
                    else:
                        surface.set_at((x, y), theme.grid)
            return
        for i, x in enumerate(xs):
            pygame.draw.line(surface, theme.grid_major if i % 5 == 0
                             else theme.grid, (x, area.top), (x, area.bottom))
        for j, y in enumerate(ys):
            pygame.draw.line(surface, theme.grid_major if j % 5 == 0
                             else theme.grid, (area.left, y), (area.right, y))

    def _draw_connection(self, a: str, b: str, capacity: int) -> None:
        """Draw one idle connection (faded when it touches a blocked zone)."""
        theme = self.painter.theme
        color = theme.edge
        if not (self.graph.zone(a).is_passable
                and self.graph.zone(b).is_passable):
            color = Colors.mix(theme.edge, theme.background, 0.55)
        start, stop = self.edge_points(a, b)
        if self.ashen is not None:
            self.ashen.path(self.surface, start, stop,
                            self.edge_width(capacity), color != theme.edge)
            return
        self.painter.line(self.surface, color, start, stop,
                          self.edge_width(capacity))

    def _draw_zone(self, zone: Zone) -> None:
        """Draw the zone body, its type marks and its rim."""
        painter, theme = self.painter, self.painter.theme
        center = self.projection.positions[zone.name]
        radius = self.zone_radius(zone)
        color = self.colors[zone.name]
        if self.ashen is not None:
            self.ashen.zone(self.surface, zone, center, radius, color)
            return
        if zone.is_passable:
            painter.glow(self.surface, color, center, radius * 1.25, 0.3)
        else:
            color = Colors.mix(color, theme.background, 0.6)
        fill = Colors.mix(theme.background, color, theme.zone_fill_mix)
        painter.disc(self.surface, theme.background, center,
                     radius + self.layout.px(2))
        painter.disc(self.surface, fill, center, radius)
        if zone.zone_type is ZoneType.RESTRICTED:
            stripe = Colors.mix(fill, color if theme.zone_fill_mix < 0.5
                                else theme.background, 0.45)
            painter.hatch(self.surface, stripe, center, radius)
        self._draw_rim(zone, center, radius, color)
        if not zone.is_passable:
            painter.cross(self.surface,
                          Colors.mix(theme.muted, theme.background, 0.2),
                          center, radius * 0.42, self.layout.px(2))

    def _draw_rim(self, zone: Zone, center: Point, radius: float,
                  color: RGB) -> None:
        """Draw the outline: rainbow segments or a ring in map colour."""
        theme = self.painter.theme
        width = max(self.layout.px(1.5), radius * theme.zone_ring)
        if zone.color and zone.color.lower() == "rainbow":
            band = max(width, self.layout.px(3))
            count = len(Colors.RAINBOW)
            for i, part in enumerate(Colors.RAINBOW):
                start = -math.pi / 2 + i * 2 * math.pi / count
                self.painter.arc_band(self.surface, part, center,
                                      radius - band, radius, start,
                                      start + 2 * math.pi / count + 0.02)
        elif theme.zone_ring > 0:
            self.painter.ring(self.surface, color, center, radius, width)

    def _draw_label(self, zone: Zone) -> None:
        """Draw the zone name below the zone (slanted on dense maps)."""
        if self.sparse_labels and not zone.has_unlimited_capacity:
            return
        theme = self.painter.theme
        x, y = self.projection.positions[zone.name]
        radius = self.projection.radius
        color = theme.text if zone.is_passable else theme.muted
        label = self.painter.halo_text(zone.name, self.label_size, color,
                                       theme.background, self.label_role,
                                       -self.label_angle)
        gap = radius + self.layout.px(8)
        if self.label_angle == 0:
            self.surface.blit(label, (round(x - label.get_width() / 2),
                                      round(y + gap)))
            return
        angle = math.radians(self.label_angle)
        height = self.label_size * 1.3
        anchor = (x + radius * 0.35, y + gap * 0.9)
        self.surface.blit(label, (
            round(anchor[0] - height / 2 * math.sin(angle)),
            round(anchor[1] - height / 2 * math.cos(angle))))
