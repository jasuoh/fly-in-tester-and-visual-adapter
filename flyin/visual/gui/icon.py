"""The window icon: a quadcopter in the mission colours, drawn in code."""

from typing import Tuple

import pygame

from flyin.visual.gui.colors import Colors
from flyin.visual.gui.themes import RGB


class AppIcon:
    """Draw the app icon at any size without an image file.

    Why procedural: no asset can go missing, and the same drawing works
    for 32, 64 and 256 pixels. It is drawn four times larger and then
    smoothly scaled down, which gives clean anti-aliased edges.
    """

    NAVY_TOP: RGB = (16, 30, 54)
    NAVY: RGB = (8, 14, 26)
    CYAN: RGB = (56, 220, 230)
    WHITE: RGB = (236, 248, 252)
    SUPERSAMPLE: int = 4
    ARM: float = 58.0

    def render(self, size: int) -> pygame.Surface:
        """Return the icon as a ``size`` x ``size`` surface with alpha."""
        big = max(256, size * self.SUPERSAMPLE)
        surface = pygame.Surface((big, big), pygame.SRCALPHA)
        unit = big / 256
        self._background(surface, big, unit)
        self._drone(surface, unit)
        return pygame.transform.smoothscale(surface, (size, size))

    def _background(self, surface: pygame.Surface, big: int,
                    unit: float) -> None:
        """Rounded navy square with a soft vertical gradient."""
        gradient = pygame.Surface((big, big), pygame.SRCALPHA)
        for y in range(big):
            color = Colors.mix(self.NAVY_TOP, self.NAVY, y / big)
            pygame.draw.line(gradient, (*color, 255), (0, y), (big, y))
        mask = pygame.Surface((big, big), pygame.SRCALPHA)
        inset = round(8 * unit)
        pygame.draw.rect(mask, (255, 255, 255, 255),
                         pygame.Rect(inset, inset, big - 2 * inset,
                                     big - 2 * inset),
                         border_radius=round(56 * unit))
        gradient.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(gradient, (0, 0))

    def _drone(self, surface: pygame.Surface, unit: float) -> None:
        """Four rotors on diagonal arms around a round body."""
        center = (128 * unit, 128 * unit)
        rotor_ring = Colors.mix(self.NAVY, self.CYAN, 0.22)
        for corner in self._rotor_centers(center, self.ARM * unit):
            pygame.draw.aaline(surface, self.CYAN, center, corner,
                               max(1, round(13 * unit)))
        for corner in self._rotor_centers(center, self.ARM * unit):
            pygame.draw.aacircle(surface, rotor_ring, corner, 31 * unit)
            pygame.draw.aacircle(surface, self.CYAN, corner, 31 * unit,
                                 max(1, round(10 * unit)))
            pygame.draw.aacircle(surface, self.CYAN, corner, 8 * unit)
        pygame.draw.aacircle(surface, self.NAVY, center, 31 * unit)
        pygame.draw.aacircle(surface, self.CYAN, center, 25 * unit)
        pygame.draw.aacircle(surface, self.WHITE, center, 9 * unit)

    @staticmethod
    def _rotor_centers(center: Tuple[float, float], distance: float
                       ) -> Tuple[Tuple[float, float], ...]:
        """Return the four rotor centres on the diagonals."""
        cx, cy = center
        return ((cx - distance, cy - distance), (cx + distance, cy - distance),
                (cx - distance, cy + distance), (cx + distance, cy + distance))
