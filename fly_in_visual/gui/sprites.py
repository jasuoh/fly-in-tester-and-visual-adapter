"""Small pixel-art sprites for the ashen theme, defined as text grids."""

from typing import Dict, Optional, Tuple

import pygame

from fly_in_visual.gui.themes import RGB


class PixelSprite:
    """A sprite given as rows of characters plus a palette.

    Why text grids: every pixel is visible in the source, the sprites
    need no image files, and a test can check that each row has the
    same width and each character has a colour. ``"."`` is transparent;
    ``"a"`` is the accent colour chosen at render time (e.g. the plume
    of a knight in its drone colour).
    """

    TRANSPARENT: str = "."
    ACCENT: str = "a"

    def __init__(self, rows: Tuple[str, ...], palette: Dict[str, RGB]
                 ) -> None:
        """Store the grid; see :meth:`validate` for the rules."""
        self.rows: Tuple[str, ...] = rows
        self.palette: Dict[str, RGB] = palette
        self._cache: Dict[Tuple[int, Optional[RGB], bool],
                          pygame.Surface] = {}

    @property
    def size(self) -> Tuple[int, int]:
        """Return (width, height) in sprite pixels."""
        return len(self.rows[0]), len(self.rows)

    def validate(self) -> None:
        """Check that the grid is rectangular and fully coloured.

        Raises:
            ValueError: On ragged rows or a character without colour.
        """
        width = len(self.rows[0])
        for row in self.rows:
            if len(row) != width:
                raise ValueError(f"row '{row}' has not {width} pixels")
            for char in row:
                if char not in self.palette and char not in (
                        self.TRANSPARENT, self.ACCENT):
                    raise ValueError(f"no colour for '{char}'")

    def render(self, scale: int, accent: Optional[RGB] = None,
               flip: bool = False) -> pygame.Surface:
        """Return the sprite scaled crisply (nearest neighbour)."""
        key = (max(1, scale), accent, flip)
        cached = self._cache.get(key)
        if cached is None:
            cached = pygame.transform.scale_by(self._base(accent), key[0])
            if flip:
                cached = pygame.transform.flip(cached, True, False)
            self._cache[key] = cached
        return cached

    def _base(self, accent: Optional[RGB]) -> pygame.Surface:
        """Paint the grid 1:1 into a transparent surface."""
        width, height = self.size
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        for y, row in enumerate(self.rows):
            for x, char in enumerate(row):
                if char == self.TRANSPARENT:
                    continue
                color = accent if char == self.ACCENT else \
                    self.palette.get(char)
                if color is not None:
                    surface.set_at((x, y), (*color, 255))
        return surface


class SpriteBook:
    """All ashen sprites: three knight frames and the zone symbols.

    Palette keys: ``k`` outline, ``m``/``l`` armour mid/light, ``s``
    steel, stone ``d``/``S``/``L``, warm sandstone ``T``/``P``/``p``
    (plinth, lit from above), fire ``f``/``y``/``o``, gold
    ``g``/``G``/``W`` and curse red ``r``/``R``.
    """

    PALETTE: Dict[str, RGB] = {
        "k": (14, 12, 12), "m": (92, 88, 84), "l": (142, 136, 126),
        "s": (168, 164, 156),
        "d": (40, 36, 34), "S": (88, 82, 76), "L": (128, 121, 111),
        "f": (186, 98, 42), "y": (232, 176, 84), "o": (252, 226, 156),
        "b": (44, 36, 32),
        "g": (138, 102, 44), "G": (214, 172, 94), "W": (246, 226, 176),
        "r": (104, 38, 34), "R": (164, 60, 50),
        "T": (206, 188, 154), "P": (156, 138, 112), "p": (104, 90, 74),
    }
    _TORSO: Tuple[str, ...] = (
        "....aa....",
        "...aak....",
        "...kkkk...",
        "..kmllmk.s",
        "..kmkkmk.s",
        "...kmmk..s",
        ".kkmmmmkks",
        "kaakmmmmk.",
        "kaakmlmmk.",
        "kaakmmmmk.",
    )
    _LEGS: Tuple[Tuple[str, ...], ...] = (
        (".kk.kmmk..", "....k..k..", "...kk..kk."),
        (".kk.kmmk..", "...k...k..", "..kk....kk"),
        (".kk.kmmk..", "....kk.k..", "....kk.kk."),
    )
    BONFIRE: Tuple[Tuple[str, ...], ...] = (
        ("......s.....", "......s.....", ".....fsf....", "....fysyf...",
         "....fyoyf...", "...fyoooyf..", "...fyoooyf..", "..ffyyoyyff.",
         "..bbffyffbb.", ".SbbbbbbbbS.", "SSbSbbSbbSbS", ".SSSSSSSSSS."),
        ("......s.....", ".....fs.....", "....ffsf....", "....fysyf...",
         "...fyyoyf...", "...fyooyyf..", "..fyoooyyf..", "..fyyooyyff.",
         "..bbfyyffbb.", ".SbbbbbbbbS.", "SSbSbbSbbSbS", ".SSSSSSSSSS."),
    )
    ARCHWAY: Tuple[str, ...] = (
        "...gggggg...", "..gGGGGGGg..", ".gGg....gGg.", ".gG......Gg.",
        ".gG..WW..Gg.", ".gG.WWWW.Gg.", ".gG.WWWW.Gg.", ".gG.WWWW.Gg.",
        ".gG.WWWW.Gg.", ".gG..WW..Gg.", "ggGg....gGgg", "GGGGGGGGGGGG",
        "gggggggggggg")
    PLINTH: Tuple[str, ...] = (
        "..TTTTTT..", ".TPPPPPPT.", "..pPPPPp..", "..pPdPPp..",
        "..pPPdPp..", ".TPPPPPPT.", "pppppppppp")
    RUNE: Tuple[str, ...] = (
        "..ggggg..", ".g.....g.", "g...G...g", "g..GGG..g", "g.G.G.G.g",
        "g...G...g", "g...G...g", ".g.....g.", "..ggggg..")
    SIGIL: Tuple[str, ...] = (
        "..rrrrr..", ".r.....r.", "r..RRR..r", "r.RRkRR.r", "r..RRR..r",
        ".r.....r.", "..rrrrr..")
    RUBBLE: Tuple[str, ...] = (
        "....S.......", "...SLS..S...", "..SLLLS.SLS.", ".SLSSLSSLLLS",
        "SLLSSdSSLSSS", "dddddddddddd")

    def __init__(self) -> None:
        """Build every sprite once."""
        palette = self.PALETTE
        self.knight: Tuple[PixelSprite, ...] = tuple(
            PixelSprite(self._TORSO + legs, palette) for legs in self._LEGS)
        self.bonfire: Tuple[PixelSprite, ...] = tuple(
            PixelSprite(rows, palette) for rows in self.BONFIRE)
        self.archway: PixelSprite = PixelSprite(self.ARCHWAY, palette)
        self.plinth: PixelSprite = PixelSprite(self.PLINTH, palette)
        self.rune: PixelSprite = PixelSprite(self.RUNE, palette)
        self.sigil: PixelSprite = PixelSprite(self.SIGIL, palette)
        self.rubble: PixelSprite = PixelSprite(self.RUBBLE, palette)

    def all(self) -> Dict[str, PixelSprite]:
        """Return every sprite by name (sprite sheet, tests)."""
        sprites: Dict[str, PixelSprite] = {
            f"knight{i}": s for i, s in enumerate(self.knight)}
        sprites.update({f"bonfire{i}": s for i, s in
                        enumerate(self.bonfire)})
        sprites.update(archway=self.archway, plinth=self.plinth,
                       rune=self.rune, sigil=self.sigil, rubble=self.rubble)
        return sprites

    @staticmethod
    def fit_scale(sprite: PixelSprite, box: float) -> int:
        """Return the largest whole scale that fits ``box`` pixels."""
        width, height = sprite.size
        return max(1, int(box // max(width, height)))
