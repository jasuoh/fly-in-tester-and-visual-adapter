"""Template adapter for a Python Fly-In project with a different structure.

The tester needs a command that takes a map path, prints the turns to the
terminal and exits with status 0, or prints an error and exits with a status
other than 0. If your project's own entry point opens a window, copy this
file, fill in the three marked places and run

    python3 -m fly_in_tester run --cmd "python3 my_adapter.py {map}" \\
        --cwd /path/to/your/project

Exactly one turn per line, e.g. ``D1-roof1 D2-corridorA``; other output is
ignored.
"""

import sys


def solve(map_path: str) -> list[str]:
    """Return the turns for ``map_path`` (one string per turn).

    FILL IN (1/3): call your parser, planner and simulation here and return
    the turn lines. Raise an exception for an invalid map or an unsolvable
    one; the message should contain the line number for parse errors.
    """
    # from my_project.parser import parse          # FILL IN (2/3)
    # from my_project.simulation import simulate   # FILL IN (2/3)
    # return simulate(parse(map_path))             # FILL IN (3/3)
    raise NotImplementedError("fill in solve() first")


def main(argv: list[str]) -> int:
    """Run ``solve`` and follow the tester's contract."""
    if len(argv) != 2:
        print(f"usage: {argv[0]} MAP", file=sys.stderr)
        return 2
    try:
        turns = solve(argv[1])
    except Exception as error:  # the message is what the tester reads
        print(error, file=sys.stderr)
        return 1
    print("\n".join(turns))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
