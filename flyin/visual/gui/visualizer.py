"""Public entry point of the GUI: frames, screenshots, interactive run."""

from typing import List, Optional, Tuple

import pygame

from flyin.visual.errors import FlyInError
from flyin.visual.gui.timeline import Timeline
from flyin.visual.gui.fonts import FontBook
from flyin.visual.gui.hud import HudRenderer
from flyin.visual.gui.layout import ScreenLayout
from flyin.visual.gui.map_layer import MapLayer
from flyin.visual.gui.painter import Painter
from flyin.visual.gui.player import View
from flyin.visual.gui.scene import MapScene
from flyin.visual.gui.themes import Theme, ThemeBook
from flyin.visual.gui.timeline_bar import TimelineBar
from flyin.visual.models import Graph, SimulationResult, Zone


class GuiVisualizer:
    """Render frames of a simulation and play them in a window.

    Why this split: :meth:`render_frame` is a pure function of
    (result, turn, progress, size). The window
    (:mod:`flyin.visual.gui.window`) only turns time and input into those
    numbers, so everything visible can be tested headless.
    """

    def __init__(self, graph: Graph, theme: str = "mission",
                 map_name: str = "") -> None:
        """Create the visualizer.

        Args:
            graph: The parsed network.
            theme: One of :meth:`theme_names`.
            map_name: Optional title shown in the side panel.

        Raises:
            FlyInError: If the theme is unknown.
        """
        self.graph: Graph = graph
        self.map_name: str = map_name
        self.theme: Theme = ThemeBook.get(theme)
        self._fonts: FontBook = FontBook()
        self._painter: Painter = Painter(self.theme, self._fonts)
        self._scene: Optional[MapScene] = None
        self._timeline: Optional[Timeline] = None

    @staticmethod
    def theme_names() -> List[str]:
        """Return the names of all available themes."""
        return ThemeBook.names()

    def set_theme(self, name: str) -> None:
        """Switch to another theme (the cached map is rebuilt)."""
        self.theme = ThemeBook.get(name)
        self._painter = Painter(self.theme, self._fonts)
        self._scene = None

    def next_theme(self) -> None:
        """Switch to the following theme (T key)."""
        self.set_theme(ThemeBook.following(self.theme).name)

    # rendering ----------------------------------------------------------

    def render_frame(self, result: SimulationResult, turn_index: int,
                     progress: float, size: Tuple[int, int]
                     ) -> pygame.Surface:
        """Render one frame without opening a window.

        Args:
            result: The simulation to show.
            turn_index: 0-based index of the animated turn.
            progress: 0 = state before that turn, 1 = state after it.
            size: Width and height of the frame in pixels.

        Returns:
            A new surface with the complete frame.
        """
        return self.compose(result, View(turn_index, progress), size)

    def save_screenshot(self, result: SimulationResult, turn_index: int,
                        path: str, size: Tuple[int, int] = (1600, 900),
                        progress: float = 1.0) -> None:
        """Render a frame and save it as an image (PNG by extension).

        Raises:
            FlyInError: If the file cannot be written.
        """
        frame = self.render_frame(result, turn_index, progress, size)
        try:
            pygame.image.save(frame, path)
        except (pygame.error, OSError) as error:
            raise FlyInError(f"cannot save screenshot '{path}': {error}"
                             ) from error

    def compose(self, result: SimulationResult, view: View,
                size: Tuple[int, int]) -> pygame.Surface:
        """Draw map, drones, timeline, panel and hover card."""
        layout = ScreenLayout(size)
        timeline = self.timeline_for(result)
        scene = self._scene_for(layout)
        frame = scene.surface.copy()
        layer = MapLayer(scene, timeline)
        layer.draw(frame, view.turn_index, view.progress, view.clock)
        self.timeline_bar(layout, timeline).draw(frame, view)
        HudRenderer(self._painter, layout, timeline,
                    self.map_name).draw(frame, view)
        hovered = layer.zone_at(view.mouse)
        if hovered is not None:
            self._tooltip(frame, layout, scene, timeline, hovered, view)
        return frame

    def timeline_for(self, result: SimulationResult) -> Timeline:
        """Return the cached timeline of ``result``."""
        if self._timeline is None or self._timeline.result is not result:
            self._timeline = Timeline(result)
        return self._timeline

    def timeline_bar(self, layout: ScreenLayout,
                     timeline: Timeline) -> TimelineBar:
        """Return the timeline bar for a layout (used for scrubbing)."""
        return TimelineBar(self._painter, layout, timeline)

    def _scene_for(self, layout: ScreenLayout) -> MapScene:
        """Return the cached static scene for this size and theme."""
        scene = self._scene
        if scene is None or scene.layout.size != layout.size:
            scene = MapScene(self.graph, layout, self._painter)
            self._scene = scene
        return scene

    def _tooltip(self, target: pygame.Surface, layout: ScreenLayout,
                 scene: MapScene, timeline: Timeline, zone: Zone,
                 view: View) -> None:
        """Draw an info card for the zone under the mouse."""
        px, theme, painter = layout.px, self.theme, self._painter
        count = timeline.occupancy(
            timeline.shown_index(view.turn_index, view.progress), zone.name)
        capacity = "∞" if zone.has_unlimited_capacity else \
            str(zone.max_drones)
        agents = f"{theme.agent_label.lower()}s"
        rows = [f"{zone.zone_type.value} · {count}/{capacity} {agents}",
                f"color {zone.color or '-'} · ({zone.x}, {zone.y})"]
        title = painter.text(zone.name, px(14), theme.text, "ui", "semibold")
        lines = [painter.text(row, px(12.5), theme.muted) for row in rows]
        width = max([title.get_width()] + [s.get_width() for s in lines])
        height = title.get_height() + sum(s.get_height() for s in lines)
        x, y = scene.projection.positions[zone.name]
        rect = pygame.Rect(0, 0, width + px(24), height + px(20))
        rect.midbottom = (round(x), round(y - scene.zone_radius(zone)
                                          - px(14)))
        rect.clamp_ip(layout.map)
        painter.panel_rect(target, theme.panel, rect, px(8),
                           theme.panel_border or theme.rule)
        target.blit(title, (rect.left + px(12), rect.top + px(10)))
        top = rect.top + px(10) + title.get_height()
        for surface in lines:
            target.blit(surface, (rect.left + px(12), top))
            top += surface.get_height()

    # interactive --------------------------------------------------------

    def run(self, result: SimulationResult) -> None:
        """Open a resizable window and play the simulation.

        Raises:
            FlyInError: If no display is available.
        """
        from flyin.visual.gui.window import PlayerWindow
        PlayerWindow(self, result).run()
