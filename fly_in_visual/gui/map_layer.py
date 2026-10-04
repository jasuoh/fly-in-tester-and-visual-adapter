"""The moving parts of the map, redrawn every frame."""

import math
from typing import List, Optional

import pygame

from fly_in_visual.gui.animation import Choreography, DroneSprite
from fly_in_visual.gui.ashen_motion import AshenMotion, Embers
from fly_in_visual.gui.colors import Colors
from fly_in_visual.gui.painter import Point
from fly_in_visual.gui.scene import MapScene
from fly_in_visual.gui.timeline import StateCounts, Timeline
from fly_in_visual.gui.themes import RGB
from fly_in_visual.models import Zone, ZoneType


class MapLayer:
    """Draw highlights, capacity rings, hub tags and drones.

    Why separate from :class:`MapScene`: the scene is cached, this
    layer depends on the playback position. Every value it draws is
    cross-faded with the same easing, so nothing switches abruptly.
    """

    def __init__(self, scene: MapScene, timeline: Timeline) -> None:
        """Bind the layer to a scene and a timeline."""
        self.scene: MapScene = scene
        self.timeline: Timeline = timeline
        self.painter = scene.painter
        self.theme = scene.painter.theme
        self.px = scene.layout.px
        self.drone_radius: float = max(
            self.px(4.5), min(self.px(9.5), scene.projection.radius * 0.45))
        self.choreography: Choreography = Choreography(
            timeline, scene.projection, scene.graph, self.drone_radius)
        self.ashen: Optional[AshenMotion] = None
        if self.theme.art == "ashen":
            self.ashen = AshenMotion(self.painter, scene.sprites,
                                     self.drone_radius,
                                     scene.projection.radius)

    def draw(self, target: pygame.Surface, turn_index: int,
             progress: float, clock: Optional[float] = None) -> None:
        """Draw everything that depends on the playback position.

        ``clock`` (seconds) drives ambient effects such as embers; by
        default it follows the playback position, so a frame is
        reproducible.
        """
        p = max(0.0, min(1.0, progress)) if self.timeline.turn_count else 0.0
        t = self.timeline.clamp(turn_index)
        now = t + p if clock is None else clock
        if self.theme.embers:
            Embers().draw(target, now, self.scene.layout.map,
                          self.theme.background, self.px(2))
        self._draw_edges(target, t, p)
        self._draw_occupancy(target, t, p)
        self._draw_ambient(target, now)
        self._draw_hub_tags(target, self.timeline.counts(
            self.timeline.shown_index(t, p)))
        sprites = self.choreography.sprites(t, p)
        for sprite in sprites:
            self._draw_drone(target, sprite, p)
        self._draw_flashes(target, sprites, p)

    def _draw_ambient(self, target: pygame.Surface, clock: float) -> None:
        """Ashen only: the bonfire in the start and cursed zones."""
        if self.ashen is None:
            return
        positions = self.scene.projection.positions
        for index, zone in enumerate(self.scene.graph.zones):
            radius = self.scene.zone_radius(zone)
            if zone.is_start:
                self.ashen.bonfire(target, positions[zone.name], radius,
                                   clock)
            elif zone.zone_type is ZoneType.RESTRICTED:
                self.ashen.curse(target, positions[zone.name], radius,
                                 clock, index)

    def _draw_flashes(self, target: pygame.Surface,
                      sprites: List[DroneSprite], p: float) -> None:
        """Ashen only: golden flash for knights reaching the goal."""
        if self.ashen is None:
            return
        goal = self.scene.graph.end
        for sprite in sprites:
            self.ashen.arrival_flash(
                target, sprite, self.scene.projection.positions[goal.name],
                self.scene.zone_radius(goal), p)

    # connections --------------------------------------------------------

    def _draw_edges(self, target: pygame.Surface, t: int, p: float) -> None:
        """Highlight used connections with a fading strength."""
        theme, graph = self.theme, self.scene.graph
        for edge, strength in self.choreography.edge_strength(t, p).items():
            if strength <= 0.01:
                continue
            a, b = sorted(edge)
            connection = graph.connection(a, b)
            capacity = connection.max_link_capacity if connection else 1
            start, stop = self.scene.edge_points(a, b)
            width = self.scene.edge_width(capacity) + self.px(1.5) * strength
            halo = Colors.mix(theme.background, theme.edge_active,
                              0.3 * strength)
            self.painter.line(target, halo, start, stop, width + self.px(4))
            self.painter.line(target, Colors.mix(theme.edge,
                                                 theme.edge_active, strength),
                              start, stop, width)

    # zones --------------------------------------------------------------

    def _draw_occupancy(self, target: pygame.Surface, t: int,
                        p: float) -> None:
        """Draw capacity rings, cross-fading old and new occupancy."""
        old = self.timeline.groups(t)
        new = self.timeline.groups(t + 1 if self.timeline.turn_count else 0)
        blend = self.choreography.occupancy_blend(p)
        for zone in self.scene.graph.zones:
            if zone.has_unlimited_capacity or not zone.is_passable:
                continue
            self._capacity_ring(target, zone, len(old.get(zone.name, [])),
                                len(new.get(zone.name, [])), blend)
            self._type_badge(target, zone)

    def _slot_color(self, zone: Zone, count: int, slot: int) -> RGB:
        """Return the colour of one ring segment for a drone count."""
        theme = self.theme
        if slot >= count:
            return Colors.mix(theme.background, theme.muted, 0.35)
        return theme.warning if count >= zone.max_drones else theme.accent

    def _capacity_ring(self, target: pygame.Surface, zone: Zone, old: int,
                       new: int, blend: float) -> None:
        """Draw ``max_drones`` segments; full zones get an outer ring."""
        center = self.scene.projection.positions[zone.name]
        inner = self.scene.projection.radius + self.px(3)
        outer = inner + self.px(3)
        fullness = (1 - blend) * (old >= zone.max_drones) \
            + blend * (new >= zone.max_drones)
        if fullness > 0.01:
            color = Colors.mix(self.theme.background, self.theme.warning,
                               fullness)
            self.painter.ring(target, color, center, outer + self.px(3),
                              self.px(1.2))
        slots = min(zone.max_drones, 24)
        gap = 0.0 if slots == 1 else min(0.18, 1.2 / slots)
        for slot in range(slots):
            start = -math.pi / 2 + slot * 2 * math.pi / slots + gap / 2
            color = Colors.mix(self._slot_color(zone, old, slot),
                               self._slot_color(zone, new, slot), blend)
            self.painter.arc_band(target, color, center, inner, outer,
                                  start, start + 2 * math.pi / slots - gap)

    def _type_badge(self, target: pygame.Surface, zone: Zone) -> None:
        """Draw the clock (restricted) or star (priority) badge."""
        if self.ashen is not None or zone.zone_type not in (
                ZoneType.RESTRICTED, ZoneType.PRIORITY):
            return
        cx, cy = self.scene.projection.positions[zone.name]
        radius = self.scene.projection.radius
        size = max(self.px(6.5), radius * 0.42)
        center = (cx + radius * 0.82, cy - radius * 0.82)
        theme, painter = self.theme, self.painter
        painter.disc(target, theme.background, center, size + self.px(2))
        if zone.zone_type is ZoneType.PRIORITY:
            painter.disc(target, Colors.mix(theme.background, Colors.STAR,
                                            0.25), center, size)
            painter.star(target, Colors.STAR, center, size * 0.85)
        else:
            painter.disc(target, Colors.mix(theme.background, theme.warning,
                                            0.18), center, size)
            painter.clock(target, theme.warning, center, size * 0.72)

    def _draw_hub_tags(self, target: pygame.Surface,
                       counts: StateCounts) -> None:
        """Draw the START / GOAL pills with waiting and delivered counts."""
        graph = self.scene.graph
        self._pill(target, graph.start, "START", str(counts.waiting),
                   self.theme.accent)
        self._pill(target, graph.end, "GOAL",
                   f"{counts.delivered}/{graph.nb_drones}", self.theme.success)

    def _pill(self, target: pygame.Surface, zone: Zone, title: str,
              value: str, color: RGB) -> None:
        """Draw a small rounded tag above a zone."""
        px, theme, painter = self.px, self.theme, self.painter
        label = painter.text(title, px(10.5), color, "ui", "semibold",
                             px(1.2))
        number = painter.text(value, px(12), theme.text, "mono", "medium")
        width = label.get_width() + number.get_width() + px(22)
        height = max(label.get_height(), number.get_height()) + px(6)
        x, y = self.scene.projection.positions[zone.name]
        top = y - self.scene.zone_radius(zone) - px(10) - height
        rect = pygame.Rect(round(x - width / 2), round(top), width, height)
        painter.panel_rect(target, Colors.mix(theme.background, color, 0.14),
                           rect, height // 2,
                           Colors.mix(theme.background, color, 0.6))
        painter.blit_center(target, label, (
            rect.left + px(9) + label.get_width() / 2, rect.centery))
        painter.blit_center(target, number, (
            rect.right - px(9) - number.get_width() / 2, rect.centery))

    # drones -------------------------------------------------------------

    def _draw_drone(self, target: pygame.Surface, sprite: DroneSprite,
                    progress: float) -> None:
        """Draw one drone marker; faded drones blend into the background."""
        if self.ashen is not None:
            self.ashen.transit_fog(target, sprite)
            self.ashen.knight(target, sprite, progress)
            return
        radius = self.drone_radius * sprite.scale
        if radius < 1 or sprite.opacity <= 0.02:
            return
        theme, painter = self.theme, self.painter
        color = Colors.mix(theme.background,
                           Colors.drone(sprite.drone_id, theme),
                           sprite.opacity)
        painter.disc(target, theme.background, sprite.point,
                     radius + self.px(2) * sprite.opacity)
        painter.disc(target, color, sprite.point, radius)
        if radius >= self.px(7.5) and sprite.opacity > 0.6:
            size = round(radius * (1.05 if sprite.drone_id < 10 else 0.9))
            text = painter.text(str(sprite.drone_id), size,
                                Colors.mix(color, theme.drone_text,
                                           sprite.opacity), "mono",
                                "semibold")
            painter.blit_center(target, text, sprite.point)

    # hover --------------------------------------------------------------

    def zone_at(self, point: Optional[Point]) -> Optional[Zone]:
        """Return the zone under the mouse pointer, if any."""
        if point is None:
            return None
        limit = self.scene.projection.radius + self.px(6)
        candidates: List[Zone] = []
        for zone in self.scene.graph.zones:
            x, y = self.scene.projection.positions[zone.name]
            if math.hypot(point[0] - x, point[1] - y) <= limit:
                candidates.append(zone)
        return candidates[0] if candidates else None
