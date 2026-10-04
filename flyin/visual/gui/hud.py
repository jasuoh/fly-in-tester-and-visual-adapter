"""The side panel: live status sections and the space budget."""

from typing import List, Tuple

import pygame

from flyin.visual.gui.timeline import StateCounts, Timeline
from flyin.visual.gui.colors import Colors
from flyin.visual.gui.layout import ScreenLayout
from flyin.visual.gui.painter import Painter
from flyin.visual.gui.panel import (
    KeyHints,
    LegendSection,
    MetricsSection,
    PanelSection,
    ThroughputSection,
)
from flyin.visual.gui.player import View


class BrandSection(PanelSection):
    """Product line, theme name and map name."""

    def __init__(self, painter: Painter, layout: ScreenLayout,
                 timeline: Timeline, map_name: str) -> None:
        """Remember the map name shown as title."""
        super().__init__(painter, layout, timeline)
        self.map_name: str = map_name or "Drone routing"

    def height(self, width: int) -> int:
        """Return brand line + title + rule + gap."""
        return self.px(16) + self.px(6) + self.px(26) + self.px(14) \
            + self.px(18)

    def draw(self, target: pygame.Surface, x: int, y: int, width: int,
             view: View) -> None:
        """Draw the brand line; the theme name only if it has room."""
        px, theme, painter = self.px, self.theme, self.painter
        brand = painter.heading("Fly-in", px(11), theme.accent, px(2.2))
        target.blit(brand, (x, y))
        mode = painter.text(theme.title, px(11.5), theme.muted)
        if brand.get_width() + px(20) + mode.get_width() <= width:
            target.blit(mode, (x + width - mode.get_width(),
                               y + (brand.get_height()
                                    - mode.get_height()) // 2))
        title = self._fit(self.map_name, px(20), width)
        target.blit(title, (x, y + px(16) + px(6)))
        rule_y = y + px(16) + px(6) + px(26) + px(14) - px(1)
        pygame.draw.line(target, theme.rule, (x, rule_y), (x + width, rule_y))

    def _fit(self, text: str, size: int, width: int) -> pygame.Surface:
        """Render ``text`` and shorten it with an ellipsis to fit."""
        surface = self.painter.text(text, size, self.theme.text, "ui",
                                    "semibold")
        while surface.get_width() > width and len(text) > 4:
            text = text[:-2]
            surface = self.painter.text(text + "…", size, self.theme.text,
                                        "ui", "semibold")
        return surface


class IssueSection(PanelSection):
    """Invalid solutions only: the rule broken at the shown turn.

    Away from a broken turn it says where the next problem is; ``E``
    jumps there (see :mod:`flyin.visual.gui.window`).
    """

    LINES: int = 3

    def line_height(self) -> int:
        """Return the height of one text line."""
        return self.painter.text("Xg", self.px(12.5), self.theme.text) \
            .get_height()

    def height(self, width: int) -> int:
        """Return caption + text lines + gap."""
        return self.caption_height() + self.LINES * self.line_height() \
            + self.px(self.GAP) - self.px(6)

    def draw(self, target: pygame.Surface, x: int, y: int, width: int,
             view: View) -> None:
        """Draw the problem of the shown state, or the way to it."""
        timeline, theme = self.timeline, self.theme
        shown = timeline.shown_index(view.turn_index, view.progress)
        here = timeline.issues_at(shown)
        turns = timeline.issue_turns()
        label = self.painter.heading("Rule broken", self.px(11),
                                     theme.danger, self.px(1.3))
        target.blit(label, (x, y))
        y += self.caption_height()
        if here:
            text = f"Turn {shown}: " + here[0].message
            if len(here) > 1:
                text += f"  (+{len(here) - 1} more)"
            color = theme.danger
        else:
            later = [t for t in turns if t > shown] or turns
            text = (f"{len(turns)} turns break a rule. Next: turn "
                    f"{later[0]}. Press E to jump there." if turns else
                    "; ".join(i.message for i in timeline.result.issues))
            color = theme.muted
        for line in self._wrap(text, width)[:self.LINES]:
            target.blit(self.painter.text(line, self.px(12.5), color),
                        (x, y))
            y += self.line_height()

    def _wrap(self, text: str, width: int) -> List[str]:
        """Split ``text`` into lines that fit ``width``."""
        lines: List[str] = []
        current = ""
        for word in text.split():
            trial = f"{current} {word}".strip()
            if current and self.painter.text(
                    trial, self.px(12.5), self.theme.text).get_width() > width:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        if len(lines) > self.LINES:
            lines[self.LINES - 1] += " …"
        return lines


class TurnSection(PanelSection):
    """Big turn counter plus en route / in transit / waiting counts."""

    def height(self, width: int) -> int:
        """Return caption + big number + gap."""
        big = self.painter.fonts.get("mono", self.px(46), "medium")
        return self.px(16) + big.get_height() + self.px(12)

    def draw(self, target: pygame.Surface, x: int, y: int, width: int,
             view: View) -> None:
        """Draw ``turn / total`` and the status column."""
        px, theme, painter = self.px, self.theme, self.painter
        total = self.timeline.turn_count
        current = self.timeline.clamp(view.turn_index) + 1 if total else 0
        caption = painter.heading("Turn", px(11), theme.muted, px(1.3))
        target.blit(caption, (x, y))
        big = painter.text(str(current), px(46), theme.text, "mono",
                           "medium")
        small = painter.text(f"/ {total}", px(20), theme.muted, "mono")
        top = y + px(16)
        target.blit(big, (x - px(2), top))
        target.blit(small, (x + big.get_width() + px(6),
                            top + big.get_height() - small.get_height()
                            - px(8)))
        counts = self.timeline.counts(
            self.timeline.shown_index(view.turn_index, view.progress))
        self._status(target, x + width, y, counts)

    def _status(self, target: pygame.Surface, right: int, y: int,
                counts: StateCounts) -> None:
        """Draw the three counters right-aligned."""
        px, theme, painter = self.px, self.theme, self.painter
        rows: Tuple[Tuple[str, int, Tuple[int, int, int]], ...] = (
            ("EN ROUTE", counts.en_route, theme.accent),
            ("IN TRANSIT", counts.transit, theme.warning),
            ("WAITING", counts.waiting, theme.muted))
        for label, value, color in rows:
            number = painter.text(str(value), px(15), theme.text, "mono",
                                  "medium")
            text = painter.text(label, px(10), theme.muted, "ui", "medium",
                                px(1.0))
            middle = y + number.get_height() / 2
            text_x = right - number.get_width() - px(8) - text.get_width()
            target.blit(number, (right - number.get_width(), y))
            target.blit(text, (text_x, round(middle - text.get_height() / 2)))
            painter.disc(target, color, (text_x - px(9), middle), px(3))
            y += number.get_height() + px(4)


class DeliveredSection(PanelSection):
    """Delivered count and progress bar."""

    def height(self, width: int) -> int:
        """Return caption + numbers + bar + gap."""
        return self.caption_height() + self.px(18) + self.px(8) \
            + self.px(6) + self.px(self.GAP)

    def draw(self, target: pygame.Surface, x: int, y: int, width: int,
             view: View) -> None:
        """Draw ``done / total``, the percentage and the bar."""
        px, theme, painter = self.px, self.theme, self.painter
        total = self.timeline.drone_count
        done = self.timeline.counts(self.timeline.shown_index(
            view.turn_index, view.progress)).delivered
        y = self.caption(target, "Delivered", x, y, width)
        value = painter.text(f"{done} / {total}", px(13.5), theme.text,
                             "mono", "medium")
        share = painter.text(f"{100 * done / total if total else 0:.0f}%",
                             px(13.5), theme.muted, "mono")
        target.blit(value, (x, y))
        target.blit(share, (x + width - share.get_width(), y))
        bar = pygame.Rect(x, y + px(18) + px(8), width, px(6))
        painter.panel_rect(target, Colors.mix(theme.panel, theme.muted,
                                              0.22), bar, bar.height // 2)
        if done and total:
            fill = bar.copy()
            fill.width = max(bar.height, round(width * done / total))
            painter.panel_rect(target, theme.success, fill, bar.height // 2)


class MovesSection(PanelSection):
    """This turn's moves in the exact output format (wrapped)."""

    def __init__(self, painter: Painter, layout: ScreenLayout,
                 timeline: Timeline) -> None:
        """Start with the minimum number of lines."""
        super().__init__(painter, layout, timeline)
        self.lines: int = 2

    def line_height(self) -> int:
        """Return the height of one text line."""
        return self.px(19)

    def height(self, width: int) -> int:
        """Return caption + ``lines`` lines + gap."""
        return self.caption_height() + self.lines * self.line_height() \
            + self.px(self.GAP) - self.px(6)

    def draw(self, target: pygame.Surface, x: int, y: int, width: int,
             view: View) -> None:
        """Draw the tokens; transits orange, deliveries green."""
        px, theme, painter = self.px, self.theme, self.painter
        y = self.caption(target, "Moves this turn", x, y, width)
        turns = self.timeline.result.turns
        moves = [str(m) for m in
                 turns[self.timeline.clamp(view.turn_index)].moves] \
            if turns else []
        if not moves:
            target.blit(painter.text("all drones hold position", px(13),
                                     theme.muted), (x, y))
            return
        lines = self._wrap(moves, width)
        if len(lines) > self.lines:
            hidden = sum(len(line) for line in lines[self.lines - 1:])
            lines = lines[:self.lines - 1] + [[f"+ {hidden} more"]]
        for line in lines:
            cursor = x
            for token in line:
                surface = painter.text(self._clip(token, width), px(13),
                                       self._color(token), "mono")
                target.blit(surface, (cursor, y))
                cursor += surface.get_width() + px(8)
            y += self.line_height()

    def _color(self, token: str) -> Tuple[int, int, int]:
        """Return the colour of one move token."""
        if token.startswith("+"):
            return self.theme.muted
        if token.count("-") >= 2:
            return self.theme.warning
        if token.endswith(f"-{self.timeline.end}"):
            return self.theme.success
        return self.theme.text

    def _clip(self, token: str, width: int) -> str:
        """Shorten a token that is wider than the whole panel."""
        font = self.painter.fonts.get("mono", self.px(13))
        while font.size(token)[0] > width and len(token) > 4:
            token = token[:-2] + "…"
        return token

    def _wrap(self, tokens: List[str], width: int) -> List[List[str]]:
        """Group tokens into lines that fit ``width`` pixels."""
        font = self.painter.fonts.get("mono", self.px(13))
        space = self.px(8)
        lines: List[List[str]] = [[]]
        used = 0
        for token in tokens:
            size = min(width, font.size(token)[0])
            if lines[-1] and used + space + size > width:
                lines.append([])
                used = 0
            used += size + (space if lines[-1] else 0)
            lines[-1].append(token)
        return lines


class HudRenderer:
    """Lay out and draw the panel without any overlap.

    Required sections always show; optional ones (metrics, legend,
    chart) are added in priority order while they fit, and spare room
    goes to more lines of moves.
    """

    MAX_MOVE_LINES: int = 5

    def __init__(self, painter: Painter, layout: ScreenLayout,
                 timeline: Timeline, map_name: str) -> None:
        """Create all sections."""
        args = (painter, layout, timeline)
        self.painter: Painter = painter
        self.layout: ScreenLayout = layout
        self.moves: MovesSection = MovesSection(*args)
        self.required: List[PanelSection] = [
            BrandSection(painter, layout, timeline, map_name),
            TurnSection(*args), DeliveredSection(*args)]
        if timeline.result.issues:
            self.required.insert(1, IssueSection(*args))
        self.metrics: PanelSection = MetricsSection(*args)
        self.legend: PanelSection = LegendSection(*args)
        self.chart: PanelSection = ThroughputSection(*args)
        self.keys: KeyHints = KeyHints(*args)

    def draw(self, target: pygame.Surface, view: View) -> None:
        """Fill the panel background and draw the chosen sections."""
        theme, rect, px = self.painter.theme, self.layout.panel, \
            self.layout.px
        pygame.draw.rect(target, theme.panel, rect)
        if theme.panel_border is not None:
            pygame.draw.line(target, theme.panel_border, rect.topleft,
                             rect.bottomleft)
        x, width = rect.left + px(24), rect.width - px(48)
        keys_top = rect.bottom - px(18) - self.keys.height(width)
        room = keys_top - rect.top - px(24)
        show_keys = room >= self._minimum(width)
        if not show_keys:
            room = rect.height - px(24)
        sections = self._plan(width, room)
        target.set_clip(rect)
        y = rect.top + px(24)
        for section in sections:
            section.draw(target, x, y, width, view)
            y += section.height(width)
        if show_keys:
            self.keys.draw(target, x, keys_top, width, view)
        target.set_clip(None)

    def _minimum(self, width: int) -> int:
        """Return the height of the required sections and two move lines."""
        self.moves.lines = 2
        return sum(s.height(width) for s in self.required) \
            + self.moves.height(width)

    def _plan(self, width: int, room: int) -> List[PanelSection]:
        """Choose the sections that fit into ``room`` pixels."""
        self.moves.lines = 2
        used = sum(s.height(width) for s in self.required) \
            + self.moves.height(width)
        extras: List[PanelSection] = []
        for section in (self.metrics, self.legend, self.chart):
            if used + section.height(width) <= room:
                extras.append(section)
                used += section.height(width)
        spare = max(0, room - used) // self.moves.line_height()
        self.moves.lines = min(self.MAX_MOVE_LINES, 2 + spare)
        order = [self.metrics, self.chart, self.legend]
        return self.required + [self.moves] + [s for s in order
                                               if s in extras]
