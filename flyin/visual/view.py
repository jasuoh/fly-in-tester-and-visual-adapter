"""``view``: play any program's solution in the pygame window.

Imported lazily by :mod:`flyin.tester.cli`, so the tester itself
keeps working without pygame.
"""

import argparse
import os
import sys
from pathlib import Path

from flyin.tester.mapfile import MapError, read_map
from flyin.tester.runner import Case, Runner, load_manifest
from flyin.visual.replay import Replay, build_replay

THEMES = ("mission", "blueprint", "graphite", "ashen")
MAX_LISTED = 8


def report(replay: Replay) -> None:
    """Print the checker's verdict and the tokens the GUI left out."""
    check = replay.check
    if replay.valid:
        print(f"VALID solution: {check.turns} turns, {check.moves} moves")
    else:
        print(f"INVALID solution ({len(check.errors)} problems), shown "
              "anyway so you can watch it happen:")
        for problem in check.errors[:MAX_LISTED]:
            print(f"  - {problem}")
    if replay.skipped:
        print(f"{len(replay.skipped)} tokens cannot be drawn and are left "
              "out:")
        for token in replay.skipped[:MAX_LISTED]:
            print(f"  - {token}")


def show(map_path: str, text: str, theme: str = "mission",
         screenshot: str | None = None, turn: int | None = None,
         raw: bool = False, title: str = "") -> int:
    """Check ``text`` against the map, report, then show it.

    Args:
        map_path: The map file.
        text: The program's output (turn lines, noise is ignored).
        theme: GUI theme.
        screenshot: Save a PNG of one turn instead of opening a window.
        turn: 1-based turn for the screenshot (default: the last one).
        raw: Treat every line as a turn.
        title: Name shown in the panel (default: the map's file name).

    Returns:
        The exit status: 0 for a valid solution, 1 otherwise, 2 if the
        map or the GUI cannot be used.
    """
    try:
        fly_map = read_map(map_path)
        replay = build_replay(fly_map, text, raw)
    except (MapError, OSError) as error:
        print(f"cannot read map: {error}", file=sys.stderr)
        return 2
    report(replay)
    if not replay.result.turns:
        print("nothing to show: the output contains no turn lines",
              file=sys.stderr)
        return 1
    try:
        from flyin.visual.errors import FlyInError
        from flyin.visual.gui import GuiVisualizer
    except ImportError as error:
        print(f"the visualizer needs pygame-ce: pip install pygame-ce "
              f"({error})", file=sys.stderr)
        return 2
    name = title or Path(map_path).stem
    if not replay.valid:
        name += " · INVALID"
    gui = GuiVisualizer(replay.result.graph, theme, map_name=name)
    try:
        if screenshot:
            count = len(replay.result.turns)
            index = count - 1 if turn is None else \
                max(0, min(count - 1, turn - 1))
            gui.save_screenshot(replay.result, index, screenshot)
            print(f"saved turn {index + 1}/{count} to {screenshot}")
        elif headless():
            print("no display here (SSH or a server?): cannot open a "
                  "window. Use a screenshot instead, e.g. "
                  "flyin show MAP --screenshot frame.png", file=sys.stderr)
            return 2
        else:
            gui.run(replay.result)
    except FlyInError as error:
        print(f"{error} (no display? use --screenshot FILE.png)",
              file=sys.stderr)
        return 2
    return 0 if replay.valid else 1


def compare(map_path: str, left: str, right: str,
            labels: tuple[str, str] = ("A", "B"), theme: str = "mission",
            screenshot: str | None = None, turn: int | None = None) -> int:
    """Check two outputs for one map and play them side by side.

    Returns:
        0 if both are valid, 1 if one is not, 2 if nothing can be shown.
    """
    try:
        fly_map = read_map(map_path)
        replays = [build_replay(fly_map, text) for text in (left, right)]
    except (MapError, OSError) as error:
        print(f"cannot read map: {error}", file=sys.stderr)
        return 2
    for label, replay in zip(labels, replays):
        print(f"[{label}] ", end="")
        report(replay)
    if not all(r.result.turns for r in replays):
        print("nothing to compare: an output has no turn lines",
              file=sys.stderr)
        return 2
    try:
        from flyin.visual.errors import FlyInError
        from flyin.visual.gui import GuiVisualizer
        from flyin.visual.gui.player import View
        import pygame
        from flyin.visual.gui.window import CompareWindow, compose_pair
    except ImportError as error:
        print(f"the visualizer needs pygame-ce: pip install pygame-ce "
              f"({error})", file=sys.stderr)
        return 2
    guis = [GuiVisualizer(r.result.graph, theme, map_name=f"{label} · "
                          f"{len(r.result.turns)} turns"
                          + ("" if r.valid else " · INVALID"))
            for label, r in zip(labels, replays)]
    a, b = replays[0].result, replays[1].result
    try:
        if screenshot:
            count = max(len(a.turns), len(b.turns))
            index = count - 1 if turn is None else \
                max(0, min(count - 1, turn - 1))
            frame = compose_pair(guis[0], a, guis[1], b, View(index, 1.0),
                                 (1700, 860))
            pygame.image.save(frame, screenshot)
            print(f"saved turn {index + 1}/{count} to {screenshot}")
        elif headless():
            print("no display here: cannot open a window (use "
                  "--screenshot FILE.png)", file=sys.stderr)
            return 2
        else:
            CompareWindow(guis[0], a, guis[1], b).run()
    except (FlyInError, pygame.error) as error:
        print(f"{error}", file=sys.stderr)
        return 2
    return 0 if all(r.valid for r in replays) else 1


def _case_for(map_path: Path) -> Case:
    """Return the manifest case of a bundled map (with its target)."""
    path = map_path.resolve()
    for case in load_manifest():
        if case.path.resolve() == path and case.expect == "solve":
            return case
    return Case(path=path, name=path.name, group="", expect="solve")


def command_view(args: argparse.Namespace) -> int:
    """Show a solution: from ``--cmd``, a file, or stdin (``-``)."""
    if args.cmd:
        runner = Runner(args.cmd, timeout=args.timeout, cwd=args.cwd,
                        source=args.source, shell=args.shell)
        outcome = runner.run_case(_case_for(Path(args.map)))
        print(f"{outcome.status}: {outcome.message} "
              f"({outcome.seconds:.1f}s)")
        text = outcome.output
    elif args.output is None or args.output == "-":
        if sys.stdin.isatty():
            print("give an output file, '-' with a pipe, or --cmd",
                  file=sys.stderr)
            return 2
        text = sys.stdin.read()
    else:
        try:
            text = Path(args.output).read_text("utf-8", errors="replace")
        except OSError as error:
            print(f"cannot read output: {error}", file=sys.stderr)
            return 2
    return show(args.map, text, args.theme, args.screenshot, args.turn,
                args.raw)


def add_view_parser(sub: "argparse._SubParsersAction[argparse.ArgumentParser]"
                    ) -> None:
    """Register the ``view`` subcommand."""
    view = sub.add_parser(
        "view", help="play a solution in the visualizer (needs pygame-ce)")
    view.add_argument("map")
    view.add_argument("output", nargs="?",
                      help="file with the output, or - for stdin")
    view.add_argument("--cmd", help="run this command on the map and show "
                      "its output ({map}, {out} as for run)")
    view.add_argument("--cwd", help="working directory for --cmd")
    view.add_argument("--source", choices=("stdout", "file"),
                      default="stdout")
    view.add_argument("--shell", action="store_true")
    view.add_argument("--timeout", type=float, default=60.0)
    view.add_argument("--theme", choices=THEMES, default="mission")
    view.add_argument("--screenshot", metavar="PNG",
                      help="save one frame instead of opening a window")
    view.add_argument("--turn", type=int,
                      help="turn for --screenshot (default: last)")
    view.add_argument("--raw", action="store_true",
                      help="every line is a turn (no noise filtering)")
    view.set_defaults(func=command_view)


def headless() -> bool:
    """Return True when no window can be opened (Linux without a display).

    A dummy SDL video driver (used by the tests) never counts as headless.
    """
    if os.environ.get("SDL_VIDEODRIVER") == "dummy":
        return False
    return sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
