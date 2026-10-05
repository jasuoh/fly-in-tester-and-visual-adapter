"""flyin as a library: check and watch your own solver from Python.

    python3 examples/use_as_library.py

In your project, install it once:

    pip install git+https://github.com/jasuoh/fly-in-tester-and-visual-adapter
    pip install pygame-ce        # for flyin.show


or put this repository on ``sys.path`` (as below).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import flyin  # noqa: E402


def my_solver(map_path: Path) -> list[str]:
    """Stand-in for YOUR algorithm: returns one string per turn."""
    sys.path.insert(0, str(Path(__file__).parent))
    from naive_solver import cheapest, parse
    drones, start, end, kinds, links = parse(str(map_path))
    path = cheapest(start, end, kinds, links)
    turns = []
    for drone in range(1, drones + 1):
        for here, there in zip(path, path[1:]):
            if kinds[there] == "restricted":
                turns.append(f"D{drone}-{here}-{there}")
            turns.append(f"D{drone}-{there}")
    return turns


if __name__ == "__main__":
    map_path = flyin.find_map("fork_merge")   # a short name or any file
    turns = my_solver(map_path)

    result = flyin.check(map_path, turns)     # every rule of the subject
    print("valid:", result.valid, "| turns:", result.turns)
    for problem in result.errors:
        print("  -", problem)

    flyin.show(map_path, turns)               # opens the visualizer
