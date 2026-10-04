"""Playback state: what to show and how time advances."""

import math
from dataclasses import dataclass
from typing import Optional, Tuple

Point = Tuple[float, float]


@dataclass
class View:
    """What one frame shows.

    Attributes:
        turn_index: 0-based index of the animated turn.
        progress: 0 = state before the turn, 1 = state after it.
        playing: Play state for the status icon (None = not interactive).
        speed: Playback speed in turns per second.
        mouse: Mouse position for the hover card, or None.
        clock: Real time in seconds for ambient effects (embers, fire);
            None makes them follow the playback position instead.
    """

    turn_index: int
    progress: float
    playing: Optional[bool] = None
    speed: float = 1.0
    mouse: Optional[Point] = None
    clock: Optional[float] = None


class Player:
    """Playback position (in turns) driven by elapsed real time.

    Why time based: ``advance(seconds)`` uses the real frame time, so
    the animation runs at the same speed on a slow and a fast machine.
    Long hiccups (window dragged, debugger) are capped so the playhead
    never jumps.
    """

    SPEEDS: Tuple[float, ...] = (0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0)
    MAX_STEP: float = 0.1

    def __init__(self, turn_count: int) -> None:
        """Start at the beginning, playing at 1 turn per second."""
        self.turn_count: int = turn_count
        self.position: float = 0.0
        self.playing: bool = True
        self.speed_index: int = 2

    @property
    def speed(self) -> float:
        """Return the speed in turns per second."""
        return self.SPEEDS[self.speed_index]

    def advance(self, seconds: float) -> None:
        """Move the playhead forward while playing."""
        if not self.playing:
            return
        step = max(0.0, min(seconds, self.MAX_STEP)) * self.speed
        self.position = min(float(self.turn_count), self.position + step)
        if self.position >= self.turn_count:
            self.playing = False

    def toggle(self) -> None:
        """Play/pause; restart when the end was reached."""
        if self.position >= self.turn_count:
            self.position = 0.0
        self.playing = not self.playing

    def step(self, direction: int) -> None:
        """Jump to the previous or next whole turn and pause."""
        self.playing = False
        if direction > 0:
            target = math.floor(self.position) + 1
        else:
            target = math.ceil(self.position) - 1
        self.seek(float(target))

    def change_speed(self, direction: int) -> None:
        """Select the next slower or faster speed."""
        self.speed_index = max(0, min(len(self.SPEEDS) - 1,
                                      self.speed_index + direction))

    def restart(self) -> None:
        """Go back to the start and play."""
        self.position = 0.0
        self.playing = True

    def seek(self, position: float) -> None:
        """Jump to ``position`` (in turns)."""
        self.position = max(0.0, min(float(self.turn_count), position))

    def view(self) -> Tuple[int, float]:
        """Return (turn index, progress) for the current position."""
        if self.turn_count == 0:
            return 0, 0.0
        index = min(int(self.position), self.turn_count - 1)
        return index, self.position - index
