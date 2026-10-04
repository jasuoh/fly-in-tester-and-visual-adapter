"""The scrubbable timeline below the map."""

import math

import pygame

from flyin.visual.gui.timeline import Timeline
from flyin.visual.gui.layout import ScreenLayout
from flyin.visual.gui.painter import Painter
from flyin.visual.gui.player import View


class TimelineBar:
    """Play state, speed, a tick per turn and the playhead.

    Why its own class: the same geometry is used for drawing and for
    turning a mouse x coordinate back into a playback position.
    """

    def __init__(self, painter: Painter, layout: ScreenLayout,
                 timeline: Timeline) -> None:
        """Bind the bar to its painter, layout and data."""
        self.painter: Painter = painter
        self.layout: ScreenLayout = layout
        self.timeline: Timeline = timeline

    def track(self) -> pygame.Rect:
        """Return the clickable track rectangle."""
        rect, px = self.layout.timeline, self.layout.px
        left = rect.left + px(92)
        return pygame.Rect(left, rect.centery - px(10),
                           max(1, rect.right - left - px(60)), px(20))

    def position_at(self, x: float) -> float:
        """Return the playback position (in turns) for a mouse x."""
        track = self.track()
        share = (x - track.left) / max(1, track.width)
        return max(0.0, min(1.0, share)) * self.timeline.turn_count

    def draw(self, target: pygame.Surface, view: View) -> None:
        """Draw status, track, ticks and playhead."""
        px, theme, painter = self.layout.px, self.painter.theme, self.painter
        track = self.track()
        total = self.timeline.turn_count
        position = 0.0
        if total:
            position = self.timeline.clamp(view.turn_index) + max(
                0.0, min(1.0, view.progress))
        self._status(target, view)
        y = track.centery
        head = track.left + (track.width * position / total if total else 0)
        pygame.draw.line(target, theme.rule, (track.left, y),
                         (track.right, y), px(4))
        pygame.draw.line(target, theme.accent, (track.left, y),
                         (round(head), y), px(4))
        self._ticks(target, track, total, position)
        painter.disc(target, theme.background, (head, y), px(9))
        painter.disc(target, theme.accent, (head, y), px(7))
        end = painter.text(str(total), px(11.5), theme.muted, "mono")
        target.blit(end, (track.right + px(12), y - end.get_height() // 2))

    def _ticks(self, target: pygame.Surface, track: pygame.Rect,
               total: int, position: float) -> None:
        """Draw one tick per turn (thinned out on long runs)."""
        if total == 0:
            return
        theme, px = self.painter.theme, self.layout.px
        every = max(1, math.ceil(total / (track.width / px(9))))
        for turn in range(0, total + 1, every):
            x = round(track.left + track.width * turn / total)
            color = theme.accent if turn <= position else theme.muted
            height = px(5) if turn % (5 * every) else px(8)
            top = track.centery + px(6)
            pygame.draw.line(target, color, (x, top), (x, top + height))

    def _status(self, target: pygame.Surface, view: View) -> None:
        """Draw the play/pause symbol and the speed."""
        px, theme, painter = self.layout.px, self.painter.theme, self.painter
        rect = self.layout.timeline
        center = (rect.left + px(14), rect.centery)
        if view.playing is None or view.playing:
            painter.play_icon(target, theme.text, center, px(7))
        else:
            for dx in (-3.5, 3.5):
                bar = pygame.Rect(0, 0, px(4), px(14))
                bar.center = (round(center[0] + px(dx)), round(center[1]))
                pygame.draw.rect(target, theme.text, bar, border_radius=1)
        speed = painter.text(f"{view.speed:g}×", px(12), theme.muted, "mono")
        target.blit(speed, (rect.left + px(32),
                            rect.centery - speed.get_height() // 2))
