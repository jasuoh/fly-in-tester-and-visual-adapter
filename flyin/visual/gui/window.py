"""The interactive window: real time and input -> playback position."""

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
        return True

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
