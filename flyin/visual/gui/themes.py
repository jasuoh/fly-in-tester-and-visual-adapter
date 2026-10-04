"""The three looks of the GUI, all settings in one place."""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from flyin.visual.errors import FlyInError

RGB = Tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    """Every colour and style switch of one look.

    Why a dataclass: the renderers never hard-code a colour, so a new
    look is just one more ``Theme(...)`` in :class:`ThemeBook`.

    Attributes:
        name: Identifier used on the command line (``--theme``).
        title: Human readable name shown in the panel.
        dark: True for dark backgrounds (affects colour legibility).
        background: Main background colour (bottom of the gradient).
        background_top: Top colour of the vertical background gradient.
        grid: Colour of the fine background grid, or None for no grid.
        grid_major: Colour of every fifth grid line (or dot).
        grid_step: Grid spacing in pixels at scale 1.
        grid_dots: Draw dots at grid crossings instead of lines.
        panel: Side panel background.
        panel_border: Panel border colour, or None.
        rule: Colour of thin separator lines.
        text: Primary text colour.
        muted: Secondary text colour.
        accent: Main accent (headings, playhead, occupancy).
        success: Delivered drones / progress bar.
        warning: Full zones and transit moves.
        danger: Broken rules (invalid solutions only).
        edge: Colour of idle connections.
        edge_active: Colour of connections used in the current turn.
        zone_fill_mix: Share of the map colour in a zone fill (0..1).
        zone_ring: Ring width relative to the zone radius (0 = no ring).
        tint: Colour mixed into every map colour (print look), or None.
        tint_amount: Strength of ``tint``.
        drone: Drone colour when ``drone_hues`` is False.
        drone_text: Colour of the drone id inside a drone marker.
        drone_hues: Give every drone its own hue.
        glow: Draw soft glows under zones (dark themes only).
        mono_labels: Use the monospace font for zone labels.
        saturation: Factor applied to the saturation of map colours.
        brightness: Upper limit for the brightness of map colours.
        art: ``"flat"`` (vector shapes) or ``"ashen"`` (pixel sprites,
            see :mod:`flyin.visual.gui.ashen`).
        display_role: Font role for headings (``"ui"`` or ``"display"``).
        hue_saturation: Saturation of per-drone hues.
        hue_value: Brightness of per-drone hues.
        embers: Draw slowly rising embers over the map.
        agent_label: What the legend and hover card call a drone.
    """

    name: str
    title: str
    dark: bool
    background: RGB
    background_top: RGB
    grid: Optional[RGB]
    grid_major: Optional[RGB]
    grid_step: int
    grid_dots: bool
    panel: RGB
    panel_border: Optional[RGB]
    rule: RGB
    text: RGB
    muted: RGB
    accent: RGB
    success: RGB
    warning: RGB
    edge: RGB
    edge_active: RGB
    zone_fill_mix: float
    zone_ring: float
    tint: Optional[RGB]
    tint_amount: float
    drone: RGB
    drone_text: RGB
    drone_hues: bool
    glow: bool
    mono_labels: bool
    saturation: float = 1.0
    brightness: float = 1.0
    art: str = "flat"
    display_role: str = "ui"
    hue_saturation: float = 0.5
    hue_value: float = 1.0
    embers: bool = False
    agent_label: str = "Drone"
    danger: RGB = (255, 84, 96)


class ThemeBook:
    """Registry of the built-in themes (order = order of the T key)."""

    THEMES: Tuple[Theme, ...] = (
        Theme(
            name="mission", title="Mission Control", dark=True,
            background=(9, 15, 27), background_top=(14, 24, 42),
            grid=(22, 36, 58), grid_major=(34, 54, 84), grid_step=32,
            grid_dots=True,
            panel=(12, 21, 37), panel_border=(32, 58, 92),
            rule=(28, 46, 72), text=(226, 238, 250), muted=(120, 146, 176),
            accent=(56, 220, 230), success=(80, 230, 160),
            warning=(255, 184, 64), edge=(54, 84, 122),
            edge_active=(56, 220, 230), zone_fill_mix=0.22, zone_ring=0.16,
            tint=None, tint_amount=0.0, drone=(56, 220, 230),
            drone_text=(8, 16, 28), drone_hues=True, glow=True,
            mono_labels=False, saturation=0.9,
        ),
        Theme(
            name="blueprint", title="Blueprint", dark=False,
            background=(244, 241, 232), background_top=(247, 245, 238),
            grid=(226, 224, 214), grid_major=(206, 210, 214), grid_step=16,
            grid_dots=False,
            panel=(250, 249, 244), panel_border=(32, 62, 120),
            rule=(200, 204, 210), text=(22, 40, 82), muted=(98, 112, 140),
            accent=(32, 82, 180), success=(30, 130, 90),
            warning=(204, 92, 20), edge=(128, 142, 168),
            edge_active=(32, 82, 180), zone_fill_mix=0.10, zone_ring=0.12,
            tint=(22, 40, 82), tint_amount=0.18, drone=(22, 46, 110),
            drone_text=(250, 249, 244), drone_hues=False, glow=False,
            mono_labels=True, danger=(196, 36, 48),
        ),
        Theme(
            name="graphite", title="Graphite", dark=True,
            background=(22, 23, 26), background_top=(22, 23, 26),
            grid=None, grid_major=None, grid_step=0, grid_dots=False,
            panel=(28, 29, 33), panel_border=None,
            rule=(44, 46, 52), text=(236, 237, 240), muted=(132, 135, 144),
            accent=(240, 240, 244), success=(98, 214, 140),
            warning=(250, 170, 60), edge=(76, 79, 88),
            edge_active=(150, 154, 166), zone_fill_mix=1.0, zone_ring=0.0,
            tint=None, tint_amount=0.0, drone=(250, 250, 252),
            drone_text=(22, 23, 26), drone_hues=False, glow=False,
            mono_labels=False, saturation=0.66, brightness=0.84,
        ),
        Theme(
            name="ashen", title="Ashen", dark=True,
            background=(21, 19, 18), background_top=(31, 28, 26),
            grid=None, grid_major=None, grid_step=0, grid_dots=False,
            panel=(29, 27, 26), panel_border=(146, 114, 60),
            rule=(66, 57, 46), text=(228, 220, 204), muted=(150, 140, 124),
            accent=(214, 172, 94), success=(214, 172, 94),
            warning=(206, 122, 66), edge=(96, 86, 74),
            edge_active=(214, 172, 94), zone_fill_mix=0.16, zone_ring=0.10,
            tint=None, tint_amount=0.0, drone=(200, 190, 170),
            drone_text=(20, 18, 16), drone_hues=True, glow=True,
            mono_labels=False, saturation=0.55, brightness=0.80,
            art="ashen", display_role="display", hue_saturation=0.42,
            hue_value=0.88, embers=True, agent_label="Knight",
        ),
    )

    @classmethod
    def names(cls) -> List[str]:
        """Return the theme names in presentation order."""
        return [theme.name for theme in cls.THEMES]

    @classmethod
    def get(cls, name: str) -> Theme:
        """Return the theme called ``name``.

        Raises:
            FlyInError: If no theme has that name.
        """
        for theme in cls.THEMES:
            if theme.name == name:
                return theme
        raise FlyInError(
            f"unknown theme '{name}' (choose from {', '.join(cls.names())})"
        )

    @classmethod
    def following(cls, theme: Theme) -> Theme:
        """Return the theme after ``theme`` (wrapping around)."""
        names = cls.names()
        return cls.THEMES[(names.index(theme.name) + 1) % len(names)]
