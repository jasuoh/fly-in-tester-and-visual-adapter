"""Colour maths on plain ``(r, g, b)`` tuples."""

import colorsys
from typing import Optional, Tuple

import pygame

from flyin.visual.gui.themes import RGB, Theme


class Colors:
    """Mix, measure and adapt colours.

    Why: map colours are free words (``crimson``, ``rainbow`` ...). They
    must stay recognisable but readable on every theme background.
    """

    RAINBOW: Tuple[RGB, ...] = (
        (239, 68, 68), (249, 146, 40), (250, 204, 21),
        (52, 199, 89), (56, 140, 248), (168, 85, 247),
    )
    STAR: RGB = (250, 204, 21)

    @staticmethod
    def mix(a: RGB, b: RGB, amount: float) -> RGB:
        """Return ``a`` moved towards ``b`` by ``amount`` (0..1)."""
        t = max(0.0, min(1.0, amount))
        return (round(a[0] + (b[0] - a[0]) * t),
                round(a[1] + (b[1] - a[1]) * t),
                round(a[2] + (b[2] - a[2]) * t))

    @staticmethod
    def luminance(color: RGB) -> float:
        """Return the perceived brightness of ``color`` (0..1)."""
        r, g, b = color
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255

    @staticmethod
    def parse(name: Optional[str]) -> Optional[RGB]:
        """Return the RGB value of a colour name, None if unknown.

        pygame knows several hundred X11 names (``crimson``, ``darkred``).
        """
        if not name:
            return None
        try:
            color = pygame.Color(name.lower())
        except ValueError:
            return None
        return (color.r, color.g, color.b)

    @staticmethod
    def soften(color: RGB, saturation: float, brightness: float) -> RGB:
        """Scale the saturation and cap the brightness of ``color``."""
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in color))
        r, g, b = colorsys.hsv_to_rgb(h, s * saturation, min(v, brightness))
        return (round(r * 255), round(g * 255), round(b * 255))

    @classmethod
    def for_zone(cls, name: Optional[str], theme: Theme) -> RGB:
        """Return a map colour adjusted to stay legible on ``theme``.

        Dark colours are lightened on dark themes, light colours darkened
        on light themes; the hue stays recognisable. Unknown names get a
        neutral grey.
        """
        if name and name.lower() == "rainbow":
            color: RGB = cls.RAINBOW[4]
        else:
            color = cls.parse(name) or cls.mix(theme.muted, theme.text, 0.2)
        color = cls.soften(color, theme.saturation, theme.brightness)
        if theme.tint is not None:
            color = cls.mix(color, theme.tint, theme.tint_amount)
        for _ in range(8):
            lum = cls.luminance(color)
            if theme.dark and lum < 0.36:
                color = cls.mix(color, (255, 255, 255), 0.14)
            elif not theme.dark and lum > 0.60:
                color = cls.mix(color, (0, 0, 0), 0.14)
            else:
                break
        return color

    @staticmethod
    def drone(drone_id: int, theme: Theme) -> RGB:
        """Return the marker colour of a drone.

        With ``drone_hues`` the golden ratio spreads hues evenly, so
        neighbouring ids get clearly different colours.
        """
        if not theme.drone_hues:
            return theme.drone
        hue = (0.52 + drone_id * 0.618034) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, theme.hue_saturation,
                                      theme.hue_value)
        return (round(r * 255), round(g * 255), round(b * 255))
