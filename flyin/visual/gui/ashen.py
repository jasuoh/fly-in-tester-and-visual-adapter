"""Static scenery of the ashen theme: stone, paths, zone sprites."""

import math
import random
from typing import Optional, Tuple

import pygame

from flyin.visual.gui.colors import Colors
from flyin.visual.gui.painter import Painter, Point
from flyin.visual.gui.sprites import PixelSprite, SpriteBook
from flyin.visual.gui.themes import RGB
from flyin.visual.models import Zone, ZoneType


class AshenScenery:
    """Draw the parts of the ashen look that never move.

    Why separate: the flat themes stay untouched; :class:`MapScene`
    only asks this class to paint background, paths and zones when the
    theme's ``art`` is ``"ashen"``. Pixel sprites mark the zone types;
    everything else (lines, rings, text) stays smooth and readable.
    """

    STONE: RGB = (46, 42, 39)
    CURSE: RGB = (92, 30, 28)
    SEED: int = 1729

    def __init__(self, painter: Painter, sprites: SpriteBook) -> None:
        """Bind the scenery to a painter and the sprite book."""
        self.painter: Painter = painter
        self.theme = painter.theme
        self.sprites: SpriteBook = sprites

    # background ---------------------------------------------------------

    def background(self, surface: pygame.Surface, area: pygame.Rect,
                   scale: float) -> None:
        """Add stone grain, a low fog and a dark vignette."""
        self._grain(surface, area)
        self._fog(surface, area)
        self._vignette(surface)

    def _grain(self, surface: pygame.Surface, area: pygame.Rect) -> None:
        """Sprinkle faint light and dark specks (same every time)."""
        rng = random.Random(self.SEED)
        base = self.theme.background
        for _ in range(area.width * area.height // 260):
            x = rng.randrange(area.left, area.right)
            y = rng.randrange(area.top, area.bottom)
            shade = rng.choice((-7, -5, 5, 8))
            surface.set_at((x, y), tuple(max(0, min(255, c + shade))
                                         for c in base))

    def _fog(self, surface: pygame.Surface, area: pygame.Rect) -> None:
        """Brighten the lower third very slightly, like ground fog."""
        height = area.height // 3
        fog = pygame.Surface((area.width, height))
        for y in range(height):
            level = round(9 * (y / max(1, height)) ** 2)
            pygame.draw.line(fog, (level, level, level - 1 if level else 0),
                             (0, y), (area.width, y))
        surface.blit(fog, (area.left, area.bottom - height),
                     special_flags=pygame.BLEND_RGB_ADD)

    @staticmethod
    def _vignette(surface: pygame.Surface) -> None:
        """Darken the corners with a smooth multiplicative mask."""
        small = pygame.Surface((48, 27))
        for y in range(27):
            for x in range(48):
                dx, dy = (x - 23.5) / 24, (y - 13) / 13.5
                level = round(255 * (1 - 0.42 * min(1.0, (dx * dx + dy * dy)
                                                    * 0.75)))
                small.set_at((x, y), (level, level, level))
        mask = pygame.transform.smoothscale(small, surface.get_size())
        surface.blit(mask, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    # paths --------------------------------------------------------------

    def path(self, surface: pygame.Surface, start: Point, stop: Point,
             width: float, faded: bool) -> None:
        """Draw a weathered path: a stone line with worn gaps."""
        theme = self.theme
        color = theme.edge
        if faded:
            color = Colors.mix(color, theme.background, 0.55)
        self.painter.line(surface, color, start, stop, width)
        length = math.hypot(stop[0] - start[0], stop[1] - start[1])
        worn = Colors.mix(color, theme.background, 0.6)
        step = max(6.0, width * 4)
        for index in range(1, int(length // step)):
            t = index * step / length
            x = start[0] + (stop[0] - start[0]) * t
            y = start[1] + (stop[1] - start[1]) * t
            size = max(1, round(width * 0.6))
            pygame.draw.rect(surface, worn, (round(x - size / 2),
                                             round(y - size / 2), size,
                                             size))

    # zones --------------------------------------------------------------

    def zone(self, surface: pygame.Surface, zone: Zone, center: Point,
             radius: float, color: RGB) -> None:
        """Draw a stone base tinted by the map colour and a type sprite."""
        theme, painter = self.theme, self.painter
        fill = Colors.mix(self.STONE, color, 0.16)
        if zone.zone_type is ZoneType.RESTRICTED:
            fill = Colors.mix(fill, self.CURSE, 0.45)
        if not zone.is_passable:
            color = Colors.mix(color, theme.background, 0.55)
            fill = Colors.mix(fill, theme.background, 0.5)
        if zone.is_end:
            painter.glow(surface, theme.accent, center, radius * 1.3, 0.30)
        painter.disc(surface, theme.background, center, radius + 2)
        painter.disc(surface, fill, center, radius)
        painter.ring(surface, color, center, radius,
                     max(1.5, radius * theme.zone_ring))
        if zone.zone_type is ZoneType.NORMAL and not zone.is_start \
                and not zone.is_end:
            painter.disc(surface, Colors.mix(fill, color, 0.28), center,
                         radius * 0.72)
        sprite = self.sprite_for(zone)
        if sprite is not None:
            self.blit_sprite(surface, sprite, center, radius * 1.45)

    def sprite_for(self, zone: Zone) -> Optional[PixelSprite]:
        """Return the static sprite of a zone (the bonfire is animated)."""
        if zone.is_start:
            return None
        if zone.is_end:
            return self.sprites.archway
        return {ZoneType.RESTRICTED: self.sprites.sigil,
                ZoneType.PRIORITY: self.sprites.rune,
                ZoneType.BLOCKED: self.sprites.rubble}.get(
                    zone.zone_type, self.sprites.plinth)

    @staticmethod
    def blit_sprite(surface: pygame.Surface, sprite: PixelSprite,
                    center: Point, box: float,
                    accent: Optional[RGB] = None) -> None:
        """Draw ``sprite`` centred, scaled to fit a ``box`` pixel square."""
        image = sprite.render(SpriteBook.fit_scale(sprite, box), accent)
        Painter.blit_center(surface, image, center)

    # legend -------------------------------------------------------------

    def legend_icon(self, target: pygame.Surface, key: str,
                    center: Tuple[float, float], radius: int) -> bool:
        """Draw the ashen version of a legend symbol; False if none."""
        sprites = {"normal": self.sprites.plinth,
                   "restricted": self.sprites.sigil,
                   "priority": self.sprites.rune,
                   "blocked": self.sprites.rubble,
                   "drone": self.sprites.knight[0]}
        if key not in sprites:
            return False
        accent = Colors.drone(1, self.theme)
        self.blit_sprite(target, sprites[key], center, radius * 3.0, accent)
        return True
