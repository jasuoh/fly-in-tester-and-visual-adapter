"""Moving parts of the ashen theme: knights, fire, fog, embers."""

import math
from typing import List, Tuple

import pygame

from fly_in_visual.gui.animation import DroneSprite, Easing
from fly_in_visual.gui.colors import Colors
from fly_in_visual.gui.painter import Painter, Point
from fly_in_visual.gui.sprites import SpriteBook
from fly_in_visual.gui.themes import RGB


class Embers:
    """A few sparks drifting slowly upwards, fully determined by time.

    Why deterministic: every ember's start, speed and sway come from a
    fixed hash of its index, so the same ``clock`` always gives the same
    picture (``render_frame`` stays reproducible, tests can check it).
    """

    COUNT: int = 16
    MIN_AREA: Tuple[int, int] = (640, 380)
    COLOR: RGB = (232, 140, 70)

    @staticmethod
    def _hash(index: int, salt: float) -> float:
        """Return a stable pseudo-random number in 0..1."""
        value = math.sin(index * 12.9898 + salt * 78.233) * 43758.5453
        return value - math.floor(value)

    def positions(self, clock: float, area: pygame.Rect
                  ) -> List[Tuple[float, float, float]]:
        """Return (x, y, opacity) of every ember; none if space is short."""
        if area.width < self.MIN_AREA[0] or area.height < self.MIN_AREA[1]:
            return []
        embers: List[Tuple[float, float, float]] = []
        for index in range(self.COUNT):
            speed = 0.025 + 0.025 * self._hash(index, 2.0)
            life = (clock * speed + self._hash(index, 3.0)) % 1.0
            sway = math.sin(clock * 0.6 + index * 1.7) * 12
            x = area.left + self._hash(index, 1.0) * area.width + sway
            y = area.bottom - life * area.height * 0.8
            embers.append((x, y, math.sin(math.pi * life) * 0.55))
        return embers

    def draw(self, target: pygame.Surface, clock: float, area: pygame.Rect,
             background: RGB, size: int) -> None:
        """Draw the embers as tiny square pixels."""
        for x, y, opacity in self.positions(clock, area):
            color = Colors.mix(background, self.COLOR, opacity)
            pygame.draw.rect(target, color, (round(x), round(y), size, size))


class AshenMotion:
    """Animated ashen details, drawn by :class:`MapLayer` every frame.

    All movement comes from the shared easing and the playback position;
    only the bonfire flicker, the curse shimmer and the embers use the
    ``clock`` so they keep living while playback is paused.
    """

    CURSE: RGB = (150, 40, 34)
    MIN_TAG_ZONE: float = 7.0

    def __init__(self, painter: Painter, sprites: SpriteBook,
                 drone_radius: float, zone_radius: float) -> None:
        """Bind to painter, sprites and the marker sizes of the map.

        Knights grow with the zones (pixel scale 1 to 3), but never
        beyond what the drone slots around a zone leave room for. At
        scale 1 a knight is only 10x13 pixels, so it is drawn on a small
        token (disc + ring in its colour) to stay easy to spot; its id
        goes above the token when the zones are not too dense.
        """
        self.painter: Painter = painter
        self.theme = painter.theme
        self.sprites: SpriteBook = sprites
        height = sprites.knight[0].size[1]
        size = max(drone_radius * 3.0, min(drone_radius * 4.2,
                                           zone_radius * 1.6))
        self.knight_scale: int = max(1, min(3, round(size / height)))
        self.compact: bool = self.knight_scale == 1
        self.compact_ids: bool = zone_radius >= self.MIN_TAG_ZONE

    @staticmethod
    def flicker(clock: float) -> float:
        """Return a calm, irregular 0..1 flicker for fire light."""
        return 0.5 + 0.3 * math.sin(clock * 5.1) + 0.2 * math.sin(
            clock * 8.3 + 1.0)

    def bonfire(self, target: pygame.Surface, center: Point, radius: float,
                clock: float) -> None:
        """Draw the resting place in the start zone with warm light."""
        strength = round(0.22 + 0.08 * self.flicker(clock), 2)
        self.painter.glow(target, (232, 150, 70), center, radius * 1.15,
                          strength)
        frame = self.sprites.bonfire[int(clock * 4) % 2]
        scale = SpriteBook.fit_scale(frame, radius * 1.5)
        Painter.blit_center(target, frame.render(scale), center)

    def curse(self, target: pygame.Surface, center: Point, radius: float,
              clock: float, index: int) -> None:
        """Let a restricted zone shimmer faintly in dark red."""
        strength = round(0.10 + 0.05 * math.sin(clock * 1.3 + index), 2)
        self.painter.glow(target, self.CURSE, center, radius * 1.05,
                          strength)

    def knight(self, target: pygame.Surface, sprite: DroneSprite,
               progress: float) -> None:
        """Draw one knight; walking knights cycle three frames and bob."""
        if sprite.opacity <= 0.02:
            return
        frame = int(progress * 6) % 3 if sprite.moving else 0
        image = self.sprites.knight[frame].render(
            self.knight_scale, Colors.drone(sprite.drone_id, self.theme),
            sprite.heading < 0)
        if sprite.opacity < 1:
            image = image.copy()
            image.set_alpha(round(255 * sprite.opacity))
        bob = -self.knight_scale if sprite.moving and frame == 1 else 0
        x, y = sprite.point
        if self.compact:
            self._token(target, sprite, image, bob)
            return
        shadow = pygame.Rect(0, 0, image.get_width() * 0.8,
                             max(2, self.knight_scale * 2))
        shadow.center = (round(x), round(y + image.get_height() / 2))
        pygame.draw.ellipse(target, Colors.mix(self.theme.background,
                                               (0, 0, 0), 0.5), shadow)
        left = round(x - image.get_width() / 2)
        top = round(y - image.get_height() / 2 + bob)
        target.blit(image, (left, top))
        if self.knight_scale >= 2 and sprite.opacity > 0.6:
            self._id_tag(target, sprite.drone_id,
                         (left + image.get_width(), top))

    def _token(self, target: pygame.Surface, sprite: DroneSprite,
               image: pygame.Surface, bob: int) -> None:
        """Draw a 1x knight on a token, with its id above if there is room.

        The token fades with the knight (departure, arrival).
        """
        theme, painter = self.theme, self.painter
        x, y = sprite.point
        radius = image.get_height() / 2 + 2.5
        ring = Colors.mix(theme.background,
                          Colors.drone(sprite.drone_id, theme),
                          sprite.opacity)
        painter.disc(target, Colors.mix(theme.background, ring, 0.3),
                     sprite.point, radius)
        painter.ring(target, ring, sprite.point, radius, 1.5)
        target.blit(image, (round(x - image.get_width() / 2),
                            round(y - image.get_height() / 2 + bob)))
        if self.compact_ids and sprite.opacity > 0.6:
            label = painter.halo_text(str(sprite.drone_id), 9, theme.text,
                                      theme.background, "mono")
            painter.blit_center(target, label,
                                (x, y - radius - label.get_height() / 2 + 2))

    def _id_tag(self, target: pygame.Surface, drone_id: int,
                corner: Point) -> None:
        """Write the drone id small and haloed next to the helmet."""
        size = max(9, self.knight_scale * 5)
        label = self.painter.halo_text(str(drone_id), size, self.theme.text,
                                       self.theme.background, "mono")
        target.blit(label, (round(corner[0] - label.get_width() * 0.1),
                            round(corner[1] - label.get_height() * 0.7)))

    def transit_fog(self, target: pygame.Surface, sprite: DroneSprite
                    ) -> None:
        """Faint red fog around a knight walking towards a curse zone."""
        if sprite.transit:
            radius = self.knight_scale * 9
            self.painter.glow(target, self.CURSE, sprite.point, radius, 0.22)

    def arrival_flash(self, target: pygame.Surface, sprite: DroneSprite,
                      goal: Point, radius: float, progress: float) -> None:
        """A short golden flash when a knight reaches the goal."""
        if not sprite.arriving:
            return
        pulse = math.sin(math.pi * Easing.window(0.6, 1.0, progress))
        if pulse > 0.02:
            self.painter.glow(target, self.theme.accent, goal, radius * 1.4,
                              round(0.5 * pulse, 2))
