"""The interactive window: real time and input -> playback position."""

from dataclasses import replace
from typing import TYPE_CHECKING, Tuple

import pygame

from flyin.visual.errors import FlyInError
from flyin.visual.gui.icon import AppIcon
from flyin.visual.gui.layout import ScreenLayout
from flyin.visual.gui.player import Player, View
from flyin.visual.models import SimulationResult

if TYPE_CHECKING:
    from flyin.visual.gui.visualizer import GuiVisualizer


class PlayerWindow:
    """Event loop of the pygame window.

    Why kept apart from drawing: this class only measures time and
    reacts to keys and the mouse; each frame it asks the visualizer for
    the picture at the current playback position.
    """

    SIZE: Tuple[int, int] = (1440, 860)
    FPS: int = 60

    def __init__(self, visualizer: "GuiVisualizer",
                 result: SimulationResult) -> None:
        """Prepare the player for ``result``."""
        self.visualizer: "GuiVisualizer" = visualizer
        self.result: SimulationResult = result
        self.player: Player = Player(len(result.turns))
        if result.issues:
            self.jump_to_issue()
        self.dragging: bool = False
        self._title: str = ""

    def run(self) -> None:
        """Open the window and loop until the user quits.

        Raises:
            FlyInError: If no display is available.
        """
        try:
            pygame.display.init()
            pygame.display.set_icon(AppIcon().render(64))
            screen = pygame.display.set_mode(self.SIZE, pygame.RESIZABLE)
        except pygame.error as error:
            raise FlyInError(f"cannot open a window: {error}") from error
        clock = pygame.time.Clock()
        try:
            while self._handle_events(screen):
                self.player.advance(clock.tick(self.FPS) / 1000)
                self._update_title()
                screen.blit(self._frame(screen.get_size()), (0, 0))
                pygame.display.flip()
        finally:
            pygame.display.quit()

    def title(self) -> str:
        """Return the window title, e.g. ``Fly-in — hard03 · turn 4/26``."""
        name = self.visualizer.map_name
        title = f"Fly-in — {name}" if name else "Fly-in"
        if self.player.turn_count:
            index, _ = self.player.view()
            title += f" · turn {index + 1}/{self.player.turn_count}"
        return title

    def _update_title(self) -> None:
        """Set the window title, but only when it changed."""
        title = self.title()
        if title != self._title:
            pygame.display.set_caption(title)
            self._title = title

    def _frame(self, size: Tuple[int, int]) -> pygame.Surface:
        """Render the frame for the current playback position."""
        index, progress = self.player.view()
        mouse = pygame.mouse.get_pos()
        view = View(index, progress, self.player.playing, self.player.speed,
                    (float(mouse[0]), float(mouse[1])),
                    pygame.time.get_ticks() / 1000)
        return self.visualizer.compose(self.result, view, size)

    def _handle_events(self, screen: pygame.Surface) -> bool:
        """Process all pending events; return False to quit."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and not self._key(event.key):
                return False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.dragging = self._scrub(screen, event.pos)
            elif event.type == pygame.MOUSEBUTTONUP:
                self.dragging = False
            elif event.type == pygame.MOUSEMOTION and self.dragging:
                self._scrub(screen, event.pos)
        return True

    def _key(self, key: int) -> bool:
        """Apply one key press; return False to quit."""
        player = self.player
        if key in (pygame.K_ESCAPE, pygame.K_q):
            return False
        if key == pygame.K_SPACE:
            player.toggle()
        elif key == pygame.K_RIGHT:
            player.step(1)
        elif key == pygame.K_LEFT:
            player.step(-1)
        elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            player.change_speed(1)
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            player.change_speed(-1)
        elif key == pygame.K_r:
            player.restart()
        elif key == pygame.K_t:
            self.visualizer.next_theme()
        elif key == pygame.K_e:
            self.jump_to_issue()
        return True

    def issue_turns(self) -> list[int]:
        """Return the turns that break a rule."""
        return self.visualizer.timeline_for(self.result).issue_turns()

    def jump_to_issue(self) -> None:
        """Pause on the next turn that breaks a rule (wraps around).

        The playhead lands just after the middle of that turn, where the
        map shows the state the rule is about.
        """
        turns = self.issue_turns()
        if not turns:
            return
        index, progress = self.player.view()
        shown = index + (1 if progress >= 0.5 else 0)
        target = next((t for t in turns if t > shown), turns[0])
        self.player.playing = False
        self.player.seek(target - 0.4)

    def _scrub(self, screen: pygame.Surface, pos: Tuple[int, int]) -> bool:
        """Seek when the mouse is on the timeline; return True if so."""
        layout = ScreenLayout(screen.get_size())
        bar = self.visualizer.timeline_bar(
            layout, self.visualizer.timeline_for(self.result))
        if not bar.track().inflate(0, layout.px(16)).collidepoint(pos):
            return False
        self.player.playing = False
        self.player.seek(bar.position_at(pos[0]))
        return True


def compose_pair(left: "GuiVisualizer", left_result: SimulationResult,
                 right: "GuiVisualizer", right_result: SimulationResult,
                 view: View, size: Tuple[int, int]) -> pygame.Surface:
    """Draw two solutions side by side at the same playback position.

    The shorter one simply stays at its last turn. The mouse only
    affects the half it is over.
    """
    width, height = size
    half = width // 2
    frame = pygame.Surface(size)
    mouse = view.mouse
    for index, (vis, result) in enumerate(((left, left_result),
                                           (right, right_result))):
        offset = index * half
        local = None
        if mouse is not None and offset <= mouse[0] < offset + half:
            local = (mouse[0] - offset, mouse[1])
        part = vis.compose(result, replace(view, mouse=local),
                           (width - half if index else half, height))
        frame.blit(part, (offset, 0))
    pygame.draw.line(frame, left.theme.rule, (half, 0), (half, height), 3)
    return frame


class CompareWindow(PlayerWindow):
    """Two solutions of the same map side by side, played together."""

    SIZE: Tuple[int, int] = (1700, 860)

    def __init__(self, left: "GuiVisualizer", left_result: SimulationResult,
                 right: "GuiVisualizer", right_result: SimulationResult
                 ) -> None:
        """Play both; the player runs as long as the longer one."""
        self.right: "GuiVisualizer" = right
        self.right_result: SimulationResult = right_result
        super().__init__(left, left_result)
        self.player = Player(max(len(left_result.turns),
                                 len(right_result.turns)))
        if left_result.issues or right_result.issues:
            self.jump_to_issue()

    def title(self) -> str:
        """Return ``Fly-in compare — A vs B · turn``."""
        title = (f"Fly-in compare — {self.visualizer.map_name} vs "
                 f"{self.right.map_name}")
        if self.player.turn_count:
            index, _ = self.player.view()
            title += f" · turn {index + 1}/{self.player.turn_count}"
        return title

    def _frame(self, size: Tuple[int, int]) -> pygame.Surface:
        """Render both halves."""
        index, progress = self.player.view()
        mouse = pygame.mouse.get_pos()
        view = View(index, progress, self.player.playing, self.player.speed,
                    (float(mouse[0]), float(mouse[1])),
                    pygame.time.get_ticks() / 1000)
        return compose_pair(self.visualizer, self.result, self.right,
                            self.right_result, view, size)

    def _key(self, key: int) -> bool:
        """Like the single player; T switches both themes."""
        if key == pygame.K_t:
            self.right.next_theme()
        return super()._key(key)

    def issue_turns(self) -> list[int]:
        """Return the broken turns of both solutions."""
        return sorted(set(super().issue_turns()) | set(
            self.right.timeline_for(self.right_result).issue_turns()))

    def _scrub(self, screen: pygame.Surface, pos: Tuple[int, int]) -> bool:
        """Seek on the timeline of either half."""
        width, height = screen.get_size()
        half = width // 2
        layout = ScreenLayout((half, height))
        x = pos[0] - half if pos[0] >= half else pos[0]
        bar = self.visualizer.timeline_bar(
            layout, self.visualizer.timeline_for(self.result))
        if not bar.track().inflate(0, layout.px(16)).collidepoint(
                (x, pos[1])):
            return False
        self.player.playing = False
        share = (x - bar.track().left) / max(1, bar.track().width)
        self.player.seek(max(0.0, min(1.0, share)) * self.player.turn_count)
        return True
