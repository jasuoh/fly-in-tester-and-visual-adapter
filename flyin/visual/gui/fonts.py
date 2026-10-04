"""Font loading with fallbacks that never crash."""

from pathlib import Path
from typing import Dict, Tuple

import pygame


class FontBook:
    """Load the bundled Geist fonts once and cache them per size.

    Why separate weight files: pygame cannot pick a weight from a
    variable font and synthetic bold looks smeared at small sizes, so
    Regular, Medium and SemiBold are real files
    (``flyin.visual/assets/fonts``).
    If a file is missing we fall back to a system font, then to the
    pygame default font.
    """

    DIRECTORY: Path = (Path(__file__).resolve().parent.parent
                       / "assets" / "fonts")
    FAMILIES: Dict[str, str] = {"ui": "Geist", "mono": "GeistMono",
                                "display": "Cinzel"}
    WEIGHTS: Dict[str, str] = {"regular": "Regular", "medium": "Medium",
                               "semibold": "SemiBold"}
    DISPLAY_WEIGHTS: Dict[str, str] = {"regular": "Regular",
                                       "medium": "Regular",
                                       "semibold": "Bold"}
    SYSTEM: Dict[str, str] = {"ui": "dejavusans,ubuntu,freesans",
                              "mono": "dejavusansmono,ubuntumono",
                              "display": "dejavuserif,freeserif"}

    def __init__(self) -> None:
        """Create an empty font cache."""
        if not pygame.font.get_init():
            pygame.font.init()
        self._fonts: Dict[Tuple[str, int, str], pygame.font.Font] = {}

    def get(self, role: str, size: int, weight: str = "regular"
            ) -> pygame.font.Font:
        """Return a font.

        Args:
            role: ``"ui"`` (Geist), ``"mono"`` (Geist Mono, tabular
                digits, used for every number) or ``"display"`` (Cinzel,
                headings of the ashen theme; only Regular and Bold).
            size: Pixel size.
            weight: ``"regular"``, ``"medium"`` or ``"semibold"``.
        """
        key = (role, max(6, size), weight)
        if key not in self._fonts:
            self._fonts[key] = self._load(*key)
        return self._fonts[key]

    def _load(self, role: str, size: int, weight: str) -> pygame.font.Font:
        """Try the bundled file, then a system font, then the default."""
        weights = self.DISPLAY_WEIGHTS if role == "display" else self.WEIGHTS
        name = f"{self.FAMILIES[role]}-{weights[weight]}.ttf"
        try:
            return pygame.font.Font(str(self.DIRECTORY / name), size)
        except (OSError, pygame.error):
            pass
        try:
            font = pygame.font.SysFont(self.SYSTEM[role], size)
        except (OSError, pygame.error):
            font = pygame.font.Font(None, size)
        font.set_bold(weight == "semibold")
        return font
