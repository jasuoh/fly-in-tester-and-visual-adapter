"""The library: everything the menu does, callable from your own code.

    import flyin

    flyin.show("easy/01", my_turn_lines)          # watch it
    result = flyin.check("easy/01", my_turn_lines)  # .valid, .errors, .turns
    outcomes = flyin.test("python3 main.py {map}", cwd="../my-project")

A map is a path to any map file, or a short name of a bundled map
(``"easy/01"``, ``"city_grid"``). An output is the text your program
printed, a list of turn lines, or a :class:`~pathlib.Path` to a file.
"""

from pathlib import Path
from typing import Iterable, Union

from flyin.tester.checker import CheckResult, check_solution
from flyin.tester.mapfile import FlyMap, read_map
from flyin.tester.runner import (
    GROUP_ORDER, MAPS_DIR, Case, Outcome, Runner, extract_turns,
    load_manifest,
)

MapRef = Union[str, Path]
Output = Union[str, Path, Iterable[str]]


def maps(query: str | None = None) -> list[Case]:
    """Return the bundled maps: all, one group, or those matching a text.

    Args:
        query: A group (``"challenge"``) or part of a map path
            (``"easy"``, ``"hard/03"``); None for all.
    """
    cases = load_manifest()
    if not query:
        return cases
    if query in GROUP_ORDER:
        return [c for c in cases if c.group == query]
    return [c for c in cases if query.lower() in c.name.lower()]


def find_map(ref: MapRef) -> Path:
    """Return the path of a map file or of a bundled map's short name.

    Raises:
        LookupError: If nothing or more than one bundled map matches.
    """
    path = Path(ref)
    if path.is_file():
        return path
    if (MAPS_DIR / path).is_file():
        return MAPS_DIR / path
    if str(ref) in GROUP_ORDER:
        raise LookupError(f"{str(ref)!r} is a group, not one map")
    found = maps(str(ref))
    if len(found) == 1:
        return found[0].path
    if not found:
        raise LookupError(f"no map matches {str(ref)!r}")
    names = ", ".join(c.name for c in found[:5])
    more = f" (+{len(found) - 5} more)" if len(found) > 5 else ""
    raise LookupError(f"{str(ref)!r} matches {len(found)} maps: "
                      f"{names}{more}")


def case_for(ref: MapRef) -> Case:
    """Return the manifest entry of a map (with its target), or a plain
    entry for a map of your own."""
    path = find_map(ref).resolve()
    for case in load_manifest():
        if case.path.resolve() == path:
            return case
    return Case(path=path, name=path.name, group="", expect="solve")


def load_map(ref: MapRef) -> FlyMap:
    """Read a map with the tester's own, independent reader."""
    return read_map(find_map(ref))


def output_text(output: Output) -> str:
    """Return an output given as text, lines or a file as one text."""
    if isinstance(output, Path):
        return output.read_text("utf-8", errors="replace")
    if isinstance(output, str):
        return output
    return "\n".join(output)


def check(ref: MapRef, output: Output) -> CheckResult:
    """Check a solution against every rule of the subject.

    Lines that are not turns (banners, debug prints) are ignored.
    """
    turns, _ = extract_turns(output_text(output))
    return check_solution(load_map(ref), turns)


def show(ref: MapRef, output: Output, theme: str = "mission",
         screenshot: str | None = None, turn: int | None = None) -> bool:
    """Check a solution, print the verdict and play it in the visualizer.

    Invalid solutions are shown too, so you can watch the mistake.

    Args:
        ref: The map.
        output: What your program printed.
        theme: ``mission``, ``blueprint``, ``graphite`` or ``ashen``.
        screenshot: Save a PNG instead of opening a window.
        turn: 1-based turn for the screenshot (default: the last).

    Returns:
        True if the solution is valid.
    """
    from flyin.visual.view import show as play
    return play(str(find_map(ref)), output_text(output), theme,
                screenshot, turn) == 0


def run(ref: MapRef, command: str, cwd: str | None = None,
        timeout: float = 60.0, output_file: str = "") -> Outcome:
    """Run your program on one map and judge it.

    ``outcome.output`` holds the solution: what it printed, or the file it
    wrote (``{out}`` in the command, or a fixed ``output_file``).
    """
    return Runner(command, timeout=timeout, cwd=cwd,
                  output_file=output_file).run_case(case_for(ref))


def test(command: str, cwd: str | None = None,
         only: str | list[str] | None = None, timeout: float = 30.0,
         jobs: int = 4, strict_targets: bool = False,
         output_file: str = "") -> list[Outcome]:
    """Run your program on many maps and judge every one.

    Args:
        command: Runs one map, ``{map}`` is replaced by its path.
        cwd: Folder the command runs in.
        only: A group, part of a map path, or a list of those; None
            for all bundled maps.
        timeout: Seconds per map.
        jobs: Maps in parallel.
        strict_targets: Turns above the target fail instead of warn.
        output_file: The fixed file your program writes, if any (the maps
            then run one by one).
    """
    queries = [only] if isinstance(only, str) else only
    if queries is None:
        cases = maps()
    else:
        wanted = {c.name for q in queries for c in maps(q)}
        cases = [c for c in maps() if c.name in wanted]
    runner = Runner(command, timeout=timeout, cwd=cwd,
                    strict_targets=strict_targets, output_file=output_file)
    return runner.run_all(cases, jobs=jobs)
