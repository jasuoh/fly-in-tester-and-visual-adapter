"""Building blocks of the side panel; each knows its own height."""

from typing import List, Tuple

import pygame

from fly_in_visual.gui.timeline import Timeline
from fly_in_visual.gui.ashen import AshenScenery
from fly_in_visual.gui.colors import Colors
from fly_in_visual.gui.layout import ScreenLayout
from fly_in_visual.gui.painter import Painter
from fly_in_visual.gui.player import View
from fly_in_visual.gui.sprites import SpriteBook


class PanelSection:
    """Base class: a block that can report its height and draw itself.

    Why: the panel first asks every section how tall it is, then keeps
    only the sections that fit. Nothing can overlap, whatever the size.
    """

    GAP: float = 22

    def __init__(self, painter: Painter, layout: ScreenLayout,
                 timeline: Timeline) -> None:
        """Store the shared helpers."""
        self.painter: Painter = painter
        self.theme = painter.theme
        self.layout: ScreenLayout = layout
        self.px = layout.px
        self.timeline: Timeline = timeline

    def height(self, width: int) -> int:
        """Return the height including the gap below the section."""
        raise NotImplementedError

    def draw(self, target: pygame.Surface, x: int, y: int, width: int,
             view: View) -> None:
        """Draw the section with its top-left corner at (x, y)."""
        raise NotImplementedError

    def caption_height(self) -> int:
        """Return the height of a section heading."""
        return self._caption_surface("X").get_height() + self.px(10)

    def caption(self, target: pygame.Surface, text: str, x: int, y: int,
                width: int) -> int:
        """Draw a letter-spaced heading with a rule; return the next y."""
        label = self._caption_surface(text)
        target.blit(label, (x, y))
        rule_y = y + label.get_height() // 2
        pygame.draw.line(target, self.theme.rule,
                         (x + label.get_width() + self.px(10), rule_y),
                         (x + width, rule_y))
        return y + self.caption_height()

    def _caption_surface(self, text: str) -> pygame.Surface:
        """Render a heading."""
        return self.painter.heading(text, self.px(11), self.theme.muted,
                                    self.px(1.3))


class MetricsSection(PanelSection):
    """Score and secondary metrics (subject VII.6) as a 2x2 grid."""

    def tile_height(self) -> int:
        """Return the height of one metric tile."""
        return self.px(56)

    def height(self, width: int) -> int:
        """Return caption + two rows of tiles + gap."""
        return (self.caption_height() + 2 * self.tile_height()
                + self.px(10) + self.px(self.GAP))

    def draw(self, target: pygame.Surface, x: int, y: int, width: int,
             view: View) -> None:
        """Draw the four tiles."""
        px, theme, painter = self.px, self.theme, self.painter
        metrics = self.timeline.metrics
        y = self.caption(target, "Metrics", x, y, width)
        tiles = (("Total turns", f"{metrics.turn_count}"),
                 ("Moves / turn", f"{metrics.moves_per_turn:.2f}"),
                 ("Avg turns / drone", f"{metrics.turns_per_drone:.2f}"),
                 ("Path cost", f"{metrics.path_cost}"))
        column = (width - px(10)) // 2
        for index, (label, value) in enumerate(tiles):
            left = x + (index % 2) * (column + px(10))
            top = y + (index // 2) * (self.tile_height() + px(10))
            rect = pygame.Rect(left, top, column, self.tile_height())
            painter.panel_rect(target, Colors.mix(theme.panel, theme.muted,
                                                  0.07), rect, px(8),
                               theme.rule)
            number = painter.text(value, px(19), theme.text, "mono",
                                  "medium")
            caption = painter.text(label, px(11.5), theme.muted)
            target.blit(number, (left + px(12), top + px(8)))
            target.blit(caption, (left + px(12), rect.bottom
                                  - caption.get_height() - px(8)))


class ThroughputSection(PanelSection):
    """Bar per turn: how many drones moved (current turn = accent)."""

    def height(self, width: int) -> int:
        """Return caption + chart + gap."""
        return self.caption_height() + self.px(44) + self.px(self.GAP)

    def draw(self, target: pygame.Surface, x: int, y: int, width: int,
             view: View) -> None:
        """Draw the bar chart."""
        total = self.timeline.turn_count
        if not total:
            return
        theme = self.theme
        profile = self.timeline.move_profile(max(1, width // 3))
        peak = max(1, max(profile))
        y = self.caption(target, f"Moves per turn · peak {peak}", x, y,
                         width)
        chart = self.px(44)
        current = self.timeline.clamp(view.turn_index) * len(profile) \
            // total
        slot = min(width / len(profile), self.px(14))
        gap = 1 if slot >= 3 else 0
        for index, moves in enumerate(profile):
            bar = max(1, round(chart * moves / peak))
            left = round(x + index * slot)
            right = round(x + (index + 1) * slot) - gap
            color = theme.rule
            if index == current:
                color = theme.accent
            elif index < current:
                color = Colors.mix(theme.panel, theme.accent, 0.45)
            pygame.draw.rect(target, color, pygame.Rect(
                left, y + chart - bar, max(1, right - left), bar))


class LegendSection(PanelSection):
    """Zone symbols explained, in two columns."""

    sprites: SpriteBook = SpriteBook()

    ENTRIES: Tuple[Tuple[str, str], ...] = (
        ("normal", "Normal zone"), ("restricted", "Restricted · 2 turns"),
        ("priority", "Priority"), ("blocked", "Blocked"),
        ("full", "Zone at capacity"), ("drone", "Drone"))

    def height(self, width: int) -> int:
        """Return caption + three rows + gap."""
        return self.caption_height() + 3 * self.px(26) + self.px(8)

    def draw(self, target: pygame.Surface, x: int, y: int, width: int,
             view: View) -> None:
        """Draw icon + text for every entry."""
        y = self.caption(target, "Legend", x, y, width)
        column = width // 2
        for index, (key, text) in enumerate(self.ENTRIES):
            if key == "drone":
                text = self.theme.agent_label
            left = x + (index % 2) * column
            top = y + (index // 2) * self.px(26)
            self._icon(target, key, (left + self.px(8), top + self.px(9)),
                       self.px(7))
            label = self.painter.text(text, self.px(12.5), self.theme.text)
            target.blit(label, (left + self.px(24),
                                top + self.px(9) - label.get_height() // 2))

    def _icon(self, target: pygame.Surface, key: str,
              center: Tuple[float, float], radius: int) -> None:
        """Draw one small legend symbol."""
        theme, painter = self.theme, self.painter
        if theme.art == "ashen" and AshenScenery(
                painter, self.sprites).legend_icon(target, key, center,
                                                   radius):
            return
        base = Colors.mix(theme.muted, theme.text, 0.3)
        fill = Colors.mix(theme.panel, base, theme.zone_fill_mix)
        if key == "drone":
            painter.disc(target, Colors.drone(1, theme), center, radius - 1)
            return
        painter.disc(target, fill, center, radius)
        ring = max(1.5, radius * max(theme.zone_ring, 0.2))
        if key == "restricted":
            painter.hatch(target, Colors.mix(fill, base if theme.zone_fill_mix
                                             < 0.5 else theme.panel, 0.5),
                          center, radius)
            painter.ring(target, theme.warning, center, radius, ring)
        elif key == "priority":
            painter.star(target, Colors.STAR, center, radius)
        elif key == "blocked":
            painter.disc(target, Colors.mix(fill, theme.panel, 0.6), center,
                         radius)
            painter.cross(target, theme.muted, center, radius * 0.5,
                          self.px(1.5))
        elif key == "full":
            painter.arc_band(target, theme.warning, center, radius - 2,
                             radius + 1, 0, 6.2832)
        else:
            painter.ring(target, base, center, radius, ring)


class KeyHints(PanelSection):
    """Keyboard shortcuts as key caps, wrapped to the panel width."""

    HINTS: Tuple[Tuple[str, str], ...] = (
        ("Space", "play"), ("← →", "step"), ("+ −", "speed"),
        ("R", "restart"), ("T", "theme"), ("Q", "quit"))

    def _rows(self, width: int) -> List[List[Tuple[str, str]]]:
        """Group the hints into rows that fit ``width``."""
        rows: List[List[Tuple[str, str]]] = [[]]
        used = 0
        for hint in self.HINTS:
            needed = self._hint_width(hint)
            if rows[-1] and used + needed > width:
                rows.append([])
                used = 0
            rows[-1].append(hint)
            used += needed
        return rows

    def _hint_width(self, hint: Tuple[str, str]) -> int:
        """Return the width of one key cap + text + spacing."""
        cap, text = self._surfaces(hint)
        return cap.get_width() + self.px(18) + text.get_width() + self.px(14)

    def _surfaces(self, hint: Tuple[str, str]
                  ) -> Tuple[pygame.Surface, pygame.Surface]:
        """Render the key and its action."""
        cap = self.painter.text(hint[0], self.px(11), self.theme.text,
                                "mono", "medium")
        text = self.painter.text(hint[1], self.px(11.5), self.theme.muted)
        return cap, text

    def height(self, width: int) -> int:
        """Return the height of all rows plus the rule above."""
        return len(self._rows(width)) * self.px(28) + self.px(14)

    def draw(self, target: pygame.Surface, x: int, y: int, width: int,
             view: View) -> None:
        """Draw a rule and the key caps."""
        px, theme, painter = self.px, self.theme, self.painter
        pygame.draw.line(target, theme.rule, (x, y), (x + width, y))
        top = y + px(14)
        for row in self._rows(width):
            cursor = x
            for hint in row:
                cap, text = self._surfaces(hint)
                rect = pygame.Rect(cursor, top, cap.get_width() + px(12),
                                   px(20))
                painter.panel_rect(target, Colors.mix(theme.panel,
                                                      theme.muted, 0.12),
                                   rect, px(4), theme.rule)
                painter.blit_center(target, cap, rect.center)
                target.blit(text, (rect.right + px(6),
                                   rect.centery - text.get_height() // 2))
                cursor += self._hint_width(hint)
            top += px(28)
