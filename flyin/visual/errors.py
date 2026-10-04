"""Exceptions used across the Fly-in project."""

from typing import Optional


class FlyInError(Exception):
    """Base class for all expected (user facing) errors."""


class MapParseError(FlyInError):
    """Raised when a map file is syntactically or semantically invalid."""

    def __init__(self, message: str, line_no: Optional[int] = None) -> None:
        """Create a parse error.

        Args:
            message: Human readable cause.
            line_no: 1-based line number in the map file, None if the error
                concerns the whole file (e.g. missing end_hub).
        """
        self.message: str = message
        self.line_no: Optional[int] = line_no
        super().__init__(str(self))

    def __str__(self) -> str:
        """Return ``"line <n>: <message>"`` or just the message."""
        if self.line_no is None:
            return self.message
        return f"line {self.line_no}: {self.message}"


class NoPathError(FlyInError):
    """Raised when the end zone cannot be reached from the start zone."""
