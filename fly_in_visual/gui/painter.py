"""Anti-aliased drawing primitives and cached text."""

import math
from typing import Dict, List, Optional, Sequence, Tuple

import pygame
import pygame.gfxdraw

from fly_in_visual.gui.colors import Colors
from fly_in_visual.gui.fonts import FontBook
from fly_in_visual.gui.themes import RGB, Theme

Point = Tuple[float, float]


class Painter:
    """Small drawing toolbox shared by all renderers.

    Why: pygame's primitives are low level. Wrapping them keeps the
    renderers readable (``painter.star(...)``) and puts every cache
    (text, glows, hatch patterns) in one place.
    """

    def __init__(self, theme: Theme, fonts: FontBook) -> None:
        """Bind the painter to a theme and a font cache."""
        self.theme: Theme = theme
        self.fonts: FontBook = fonts
        self._text: Dict[Tuple[object, ...], pygame.Surface] = {}
        self._glows: Dict[Tuple[int, RGB, float], pygame.Surface] = {}
        self._hatches: Dict[Tuple[int, RGB], pygame.Surface] = {}

    # text ---------------------------------------------------------------

    def text(self, text: str, size: int, color: RGB, role: str = "ui",
             weight: str = "regular", tracking: float = 0.0
             ) -> pygame.Surface:
        """Return rendered text (cached); ``tracking`` adds letter spacing."""
        key: Tuple[object, ...] = (text, size, color, role, weight, tracking)
        cached = self._text.get(key)
        if cached is not None:
            return cached
        font = self.fonts.get(role, size, weight)
        if tracking <= 0:
            surface = font.render(text, True, color)
        else:
            surface = self._tracked(font, text, color, tracking)
        if len(self._text) > 4000:
            self._text.clear()
        self._text[key] = surface
        return surface

    @staticmethod
    def _tracked(font: pygame.font.Font, text: str, color: RGB,
                 tracking: float) -> pygame.Surface:
        """Render ``text`` letter by letter with extra spacing."""
        glyphs = [font.render(char, True, color) for char in text]
        width = sum(g.get_width() for g in glyphs)
        width += round(tracking * max(0, len(glyphs) - 1))
        surface = pygame.Surface((max(1, width), font.get_height()),
                                 pygame.SRCALPHA)
        x = 0.0
        for glyph in glyphs:
            surface.blit(glyph, (round(x), 0))
            x += glyph.get_width() + tracking
        return surface

    def heading(self, text: str, size: int, color: RGB,
                tracking: float = 0.0) -> pygame.Surface:
        """Render a heading in the theme's display style.

        Flat themes use letter-spaced Geist capitals. The ashen theme
        uses Cinzel, whose lowercase letters already are small caps.
        """
        if self.theme.display_role == "display":
            warm = Colors.mix(color, self.theme.accent, 0.45)
            return self.text(text, round(size * 1.18), warm, "display",
                             "semibold")
        return self.text(text.upper(), size, color, "ui", "semibold",
                         tracking)

    def halo_text(self, text: str, size: int, color: RGB, halo: RGB,
                  role: str, angle: float = 0.0) -> pygame.Surface:
        """Return text with a soft outline so it stays readable on lines."""
        key: Tuple[object, ...] = ("halo", text, size, color, halo, role,
                                   angle)
        cached = self._text.get(key)
        if cached is not None:
            return cached
        core = self.text(text, size, color, role)
        ring = self.text(text, size, halo, role)
        pad = 2
        surface = pygame.Surface(
            (core.get_width() + 2 * pad, core.get_height() + 2 * pad),
            pygame.SRCALPHA)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1),
                       (1, 1), (-1, 1), (1, -1)):
            surface.blit(ring, (pad + dx, pad + dy))
        surface.blit(core, (pad, pad))
        if angle:
            surface = pygame.transform.rotozoom(surface, angle, 1.0)
        self._text[key] = surface
        return surface

    @staticmethod
    def blit_center(target: pygame.Surface, surface: pygame.Surface,
                    center: Point) -> None:
        """Blit ``surface`` centred on ``center``."""
        target.blit(surface, (round(center[0] - surface.get_width() / 2),
                              round(center[1] - surface.get_height() / 2)))

    # basic shapes -------------------------------------------------------

    @staticmethod
    def disc(target: pygame.Surface, color: RGB, center: Point,
             radius: float) -> None:
        """Draw a filled anti-aliased circle."""
        if radius >= 0.5:
            pygame.draw.aacircle(target, color, center, radius)

    @staticmethod
    def ring(target: pygame.Surface, color: RGB, center: Point,
             radius: float, width: float) -> None:
        """Draw an anti-aliased circle outline of ``width`` pixels."""
        if radius >= 1 and width > 0:
            pygame.draw.aacircle(target, color, center, radius,
                                 max(1, round(width)))

    @staticmethod
    def line(target: pygame.Surface, color: RGB, a: Point, b: Point,
             width: float) -> None:
        """Draw an anti-aliased line of ``width`` pixels."""
        pygame.draw.aaline(target, color, a, b, max(1, round(width)))

    @staticmethod
    def polygon(target: pygame.Surface, color: RGB,
                points: Sequence[Point]) -> None:
        """Draw a filled polygon with anti-aliased edges."""
        pts = [(round(x), round(y)) for x, y in points]
        if len(pts) >= 3:
            pygame.gfxdraw.filled_polygon(target, pts, color)
            pygame.gfxdraw.aapolygon(target, pts, color)

    @staticmethod
    def panel_rect(target: pygame.Surface, color: RGB, rect: pygame.Rect,
                   radius: int, border: Optional[RGB] = None) -> None:
        """Draw a rounded rectangle with an optional 1 px border."""
        pygame.draw.rect(target, color, rect, border_radius=radius)
        if border is not None:
            pygame.draw.rect(target, border, rect, 1, border_radius=radius)

    # symbols ------------------------------------------------------------

    @classmethod
    def arc_band(cls, target: pygame.Surface, color: RGB, center: Point,
                 inner: float, outer: float, start: float,
                 stop: float) -> None:
        """Draw a ring segment between two radii and two angles (rad)."""
        steps = max(3, int(abs(stop - start) * outer / 3))
        outer_pts: List[Point] = []
        inner_pts: List[Point] = []
        for i in range(steps + 1):
            angle = start + (stop - start) * i / steps
            cos, sin = math.cos(angle), math.sin(angle)
            outer_pts.append((center[0] + cos * outer,
                              center[1] + sin * outer))
            inner_pts.append((center[0] + cos * inner,
                              center[1] + sin * inner))
        cls.polygon(target, color, outer_pts + inner_pts[::-1])

    @classmethod
    def star(cls, target: pygame.Surface, color: RGB, center: Point,
             radius: float) -> None:
        """Draw a five pointed star (priority zones)."""
        points: List[Point] = []
        for i in range(10):
            r = radius if i % 2 == 0 else radius * 0.45
            angle = -math.pi / 2 + i * math.pi / 5
            points.append((center[0] + math.cos(angle) * r,
                           center[1] + math.sin(angle) * r))
        cls.polygon(target, color, points)

    @classmethod
    def clock(cls, target: pygame.Surface, color: RGB, center: Point,
              radius: float) -> None:
        """Draw a small clock face (restricted zones cost 2 turns)."""
        width = max(1.0, radius * 0.22)
        cls.ring(target, color, center, radius, width)
        cx, cy = center
        cls.line(target, color, center, (cx, cy - radius * 0.62), width)
        cls.line(target, color, center, (cx + radius * 0.5, cy), width)

    @classmethod
    def cross(cls, target: pygame.Surface, color: RGB, center: Point,
              size: float, width: float) -> None:
        """Draw an X (blocked zones)."""
        cx, cy = center
        cls.line(target, color, (cx - size, cy - size),
                 (cx + size, cy + size), width)
        cls.line(target, color, (cx - size, cy + size),
                 (cx + size, cy - size), width)

    @classmethod
    def play_icon(cls, target: pygame.Surface, color: RGB, center: Point,
                  size: float) -> None:
        """Draw a play triangle."""
        cx, cy = center
        cls.polygon(target, color, [(cx - size * 0.6, cy - size),
                                    (cx + size * 0.9, cy),
                                    (cx - size * 0.6, cy + size)])

    # effects ------------------------------------------------------------

    def glow(self, target: pygame.Surface, color: RGB, center: Point,
             radius: float, strength: float) -> None:
        """Add a soft additive glow (only on themes with ``glow``).

        Used for the static map layer only, so it never flickers.
        """
        if not self.theme.glow or radius < 2:
            return
        key = (round(radius), color, round(strength, 2))
        surface = self._glows.get(key)
        if surface is None:
            size = round(radius * 4)
            surface = pygame.Surface((size, size))
            surface.fill((0, 0, 0))
            core = Colors.mix((0, 0, 0), color, strength)
            pygame.draw.circle(surface, core, (size // 2, size // 2),
                               round(radius))
            surface = pygame.transform.gaussian_blur(
                surface, max(1, round(radius * 0.6)))
            self._glows[key] = surface
        target.blit(surface, (round(center[0] - surface.get_width() / 2),
                              round(center[1] - surface.get_height() / 2)),
                    special_flags=pygame.BLEND_RGB_ADD)

    def hatch(self, target: pygame.Surface, color: RGB, center: Point,
              radius: float) -> None:
        """Fill a circle with diagonal stripes (restricted = slow zone)."""
        r = max(2, round(radius))
        key = (r, color)
        surface = self._hatches.get(key)
        if surface is None:
            size = 2 * r + 2
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            step = max(4, round(r / 3))
            for offset in range(-size, size, step):
                pygame.draw.aaline(surface, (*color, 255), (offset, size),
                                   (offset + size, 0), max(1, step // 3))
            mask = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.aacircle(mask, (255, 255, 255, 255),
                                 (size / 2, size / 2), r - 0.5)
            surface.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self._hatches[key] = surface
        self.blit_center(target, surface, center)
