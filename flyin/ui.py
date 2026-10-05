"""Terminal pickers: arrow keys in a real terminal, numbers elsewhere.

In a terminal (macOS, Linux): ``↑`` ``↓`` move, ``Enter`` chooses,
``Space`` marks several, ``*`` marks all, typing filters, ``Esc`` goes
back. Without a terminal (pipes, scripts, tests, Windows) the same
choices are made by typing numbers: ``3``, ``1,3,5``, ``2-6``, ``all``
or part of a name.
"""

import os
import select
import shutil
import sys
from dataclasses import dataclass

CSI = "\033["
COLORS = {"ok": "32", "warn": "33", "bad": "31", "dim": "2", "bold": "1",
          "accent": "36"}


@dataclass
class Item:
    """One choice.

    Attributes:
        label: Main text.
        hint: Dim text on the right.
        mark: A status sign in front (e.g. ``✓``), may be empty.
        color: Colour of the mark (``ok``, ``warn``, ``bad``, ``dim``).
    """

    label: str
    hint: str = ""
    mark: str = ""
    color: str = ""


def paint(text: str, color: str) -> str:
    """Colour ``text`` on a terminal."""
    if not color or not sys.stdout.isatty():
        return text
    return f"{CSI}{COLORS[color]}m{text}{CSI}0m"


def arrows_available() -> bool:
    """Return True when keys can be read one by one."""
    if os.name == "nt" or os.environ.get("FLYIN_NUMBERS"):
        return False
    try:
        import termios  # noqa: F401
        import tty  # noqa: F401
    except ImportError:
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()


def selection(text: str, count: int) -> list[int] | None:
    """Parse ``all``, ``1,3,5`` or ``2-6`` into 0-based indexes.

    Returns None if ``text`` is not a selection (e.g. a map name).
    """
    text = text.replace(" ", "")
    if text.lower() == "all":
        return list(range(count))
    indexes: list[int] = []
    for part in text.split(","):
        first, dash, last = part.partition("-")
        if not first.isdigit() or (dash and not last.isdigit()):
            return None
        stop = int(last) if dash else int(first)
        for number in range(int(first), stop + 1):
            if 1 <= number <= count and number - 1 not in indexes:
                indexes.append(number - 1)
    return indexes or None


def pick(title: str, items: list[Item], multi: bool = False,
         filterable: bool = False, back: str = "back") -> list[int] | None:
    """Let the user choose; return the chosen indexes or None for back.

    Args:
        title: Question above the list.
        items: The choices.
        multi: Several may be chosen.
        filterable: Typing narrows the list (by label).
        back: Text of the way out (``back`` or ``quit``).
    """
    if not items:
        return None
    if arrows_available():
        return _ArrowPicker(title, items, multi, filterable, back).run()
    return _number_pick(title, items, multi, filterable, back)


# numbers -----------------------------------------------------------------

def _mark(item: Item, used: bool) -> str:
    """Return the mark column: the sign, or blanks to keep alignment."""
    if item.mark:
        return paint(item.mark, item.color) + " "
    return "  " if used else ""


def _line(number: str, item: Item, width: int, marks: bool) -> str:
    """Format one numbered row."""
    mark = _mark(item, marks)
    hint = paint(item.hint, "dim") if item.hint else ""
    label = item.label.ljust(width) if hint else item.label
    return f"  {number:>3}  {mark}{label}  {hint}".rstrip()


def _number_pick(title: str, items: list[Item], multi: bool,
                 filterable: bool, back: str) -> list[int] | None:
    """The numbered fallback."""
    print(f"\n{paint(title, 'bold')}")
    width = max(len(i.label) for i in items)
    marks = any(i.mark for i in items)
    for number, item in enumerate(items, 1):
        print(_line(str(number), item, width, marks))
    print(f"    0  {back}")
    hint = "number"
    if multi:
        hint += ", 1,3,5, 2-6 or all"
    if filterable:
        hint += " or part of a name"
    try:
        answer = input(f"Choose ({hint}): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)
    if answer.lower() in ("", "0", "q"):
        return None
    if answer.isdigit():
        if 1 <= int(answer) <= len(items):
            return [int(answer) - 1]
        print(paint("not a choice", "bad"))
        return None
    if multi:
        chosen = selection(answer, len(items))
        if chosen:
            return chosen
    if filterable:
        matches = [i for i, item in enumerate(items)
                   if answer.lower() in item.label.lower()]
        if len(matches) == 1:
            return matches
        if matches:
            again = _number_pick(f"{len(matches)} match '{answer}':",
                                 [items[i] for i in matches], multi, False,
                                 back)
            return None if again is None else [matches[i] for i in again]
        print(paint(f"nothing matches '{answer}'", "bad"))
        return None
    print(paint("not a choice", "bad"))
    return None


# arrow keys --------------------------------------------------------------

class _ArrowPicker:
    """An interactive list drawn in place below the cursor."""

    def __init__(self, title: str, items: list[Item], multi: bool,
                 filterable: bool, back: str) -> None:
        """Prepare the state; nothing is drawn yet."""
        self.title, self.items = title, items
        self.multi, self.filterable, self.back = multi, filterable, back
        self.cursor = 0
        self.top = 0
        self.query = ""
        self.marked: set[int] = set()
        self.drawn = 0

    def visible(self) -> list[int]:
        """Return the indexes that match the filter."""
        query = self.query.lower()
        return [i for i, item in enumerate(self.items)
                if query in item.label.lower()]

    def run(self) -> list[int] | None:
        """Read keys until a choice is made or the user goes back."""
        import termios
        import tty
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        sys.stdout.write(f"{CSI}?25l")
        try:
            tty.setcbreak(fd)
            while True:
                self.draw()
                result = self.handle(self.read_key(fd))
                if result is not None:
                    return result or None
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
            sys.stdout.write(f"{CSI}?25h")
            sys.stdout.flush()

    def handle(self, key: str) -> list[int] | None:
        """Apply a key; return the result ([] = back) or None to go on."""
        shown = self.visible()
        if key == "esc" or (key == "q" and not self.filterable):
            self.finish("")
            return []
        if key in ("up", "k") and not (key == "k" and self.filterable):
            self.cursor = max(0, self.cursor - 1)
        elif key in ("down", "j") and not (key == "j" and self.filterable):
            self.cursor = min(len(shown) - 1, self.cursor + 1)
        elif key in ("pgup", "pgdown"):
            step = self.rows() * (1 if key == "pgdown" else -1)
            self.cursor = max(0, min(len(shown) - 1, self.cursor + step))
        elif key == "space" and self.multi and shown:
            self.marked ^= {shown[self.cursor]}
        elif key == "*" and self.multi:
            self.marked = set(shown) if set(shown) - self.marked else set()
        elif key == "enter" and shown:
            chosen = sorted(self.marked) if self.marked else \
                [shown[self.cursor]]
            names = ", ".join(self.items[i].label for i in chosen[:3])
            more = f" +{len(chosen) - 3}" if len(chosen) > 3 else ""
            self.finish(f"{names}{more}")
            return chosen
        elif key == "backspace" and self.filterable:
            self.query = self.query[:-1]
            self.cursor = 0
        elif self.filterable and len(key) == 1 and key.isprintable():
            self.query += key
            self.cursor = 0
        elif key.isdigit() and not self.filterable:
            number = int(key) - 1
            if 0 <= number < len(shown):
                self.cursor = number
        return None

    @staticmethod
    def read_key(fd: int) -> str:
        """Return one key as a name (``up``, ``enter``, ...) or a char."""
        char = os.read(fd, 1)
        if char == b"\x1b":
            ready, _, _ = select.select([fd], [], [], 0.04)
            if not ready:
                return "esc"
            sequence = os.read(fd, 2)
            if sequence[-1:] in (b"5", b"6"):
                os.read(fd, 1)
            return {b"[A": "up", b"[B": "down", b"OA": "up", b"OB": "down",
                    b"[5": "pgup", b"[6": "pgdown"}.get(sequence, "")
        if char in (b"\r", b"\n"):
            return "enter"
        if char == b" ":
            return "space"
        if char in (b"\x7f", b"\x08"):
            return "backspace"
        if char == b"\x03":
            raise KeyboardInterrupt
        if char == b"\x04":
            return "esc"
        return char.decode("utf-8", errors="ignore")

    @staticmethod
    def rows() -> int:
        """Return how many list rows fit on the screen."""
        return max(5, min(16, shutil.get_terminal_size().lines - 8))

    def draw(self) -> None:
        """Redraw the picker in place."""
        width = shutil.get_terminal_size().columns - 1
        shown = self.visible()
        self.cursor = max(0, min(self.cursor, len(shown) - 1))
        rows = self.rows()
        if self.cursor < self.top:
            self.top = self.cursor
        elif self.cursor >= self.top + rows:
            self.top = self.cursor - rows + 1
        self.top = max(0, min(self.top, max(0, len(shown) - rows)))
        keys = ["↑↓ move", "enter choose"]
        if self.multi:
            keys += ["space mark", "* all"]
        if self.filterable:
            keys.append("type to filter")
        keys.append(f"esc {self.back}")
        lines = [paint(self.title, "bold"), paint(" · ".join(keys), "dim")]
        if self.filterable:
            lines.append(paint("filter: ", "dim") + self.query
                         + paint("▏", "accent"))
        label_width = min(48, max((len(self.items[i].label)
                                   for i in shown), default=0))
        for row, index in enumerate(shown[self.top:self.top + rows]):
            item = self.items[index]
            here = self.top + row == self.cursor
            pointer = paint("❯", "accent") if here else " "
            box = ""
            if self.multi:
                box = paint("◉", "accent") if index in self.marked else "○"
                box += " "
            mark = _mark(item, any(i.mark for i in self.items))
            label = item.label[:label_width].ljust(label_width)
            if here:
                label = paint(label, "bold")
            text = f" {pointer} {box}{mark}{label}  {paint(item.hint, 'dim')}"
            lines.append(text)
        if not shown:
            lines.append(paint("   nothing matches", "dim"))
        hidden = len(shown) - rows
        if hidden > 0:
            lines.append(paint(f"   {self.top + 1}-"
                               f"{min(len(shown), self.top + rows)} of "
                               f"{len(shown)}", "dim"))
        if self.multi and self.marked:
            lines.append(paint(f"   {len(self.marked)} marked", "accent"))
        self.write(lines, width)

    def write(self, lines: list[str], width: int) -> None:
        """Replace the previous drawing with ``lines``."""
        out = sys.stdout
        if self.drawn:
            out.write(f"{CSI}{self.drawn}F")
        out.write(f"{CSI}J")
        for line in lines:
            out.write(_clip(line, width) + "\n")
        out.flush()
        self.drawn = len(lines)

    def finish(self, summary: str) -> None:
        """Remove the picker, leaving one line with the choice."""
        out = sys.stdout
        if self.drawn:
            out.write(f"{CSI}{self.drawn}F{CSI}J")
        if summary:
            out.write(f"{paint(self.title, 'bold')} "
                      f"{paint(summary, 'accent')}\n")
        out.flush()
        self.drawn = 0


def _clip(line: str, width: int) -> str:
    """Cut a line with colour codes to ``width`` visible characters."""
    visible = 0
    out = []
    index = 0
    while index < len(line):
        if line.startswith(CSI, index):
            end = line.index("m", index) + 1
            out.append(line[index:end])
            index = end
            continue
        if visible >= width:
            break
        out.append(line[index])
        visible += 1
        index += 1
    return "".join(out) + f"{CSI}0m" if CSI in line else "".join(out)
