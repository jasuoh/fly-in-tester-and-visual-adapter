"""A deliberately naive Fly-In solver, to try the arena without a project.

Every drone flies the cheapest route alone; the next one starts when the
previous one has arrived. Always valid, never fast: watch it in the
visualizer and then beat it with your own algorithm.

    python3 examples/naive_solver.py MAP
    python3 -m fly_in_tester view MAP \\
        --cmd "python3 examples/naive_solver.py {map}"

It does not validate maps, so it fails most ``edge-invalid`` maps.
"""

import heapq
import re
import sys

COST = {"normal": 1, "priority": 1, "restricted": 2}


def parse(path: str) -> tuple[int, str, str, dict[str, str],
                              dict[str, list[str]]]:
    """Return drones, start, end, zone kinds and neighbours."""
    drones, start, end = 0, "", ""
    kinds: dict[str, str] = {}
    links: dict[str, list[str]] = {}
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.split("#")[0].strip()
            key, _, rest = line.partition(":")
            kind = re.search(r"zone=(\w+)", rest)
            if key == "nb_drones":
                drones = int(rest)
            elif key in ("start_hub", "end_hub", "hub"):
                name = rest.split()[0]
                kinds[name] = kind.group(1) if kind else "normal"
                links.setdefault(name, [])
                start = name if key == "start_hub" else start
                end = name if key == "end_hub" else end
            elif key == "connection":
                a, b = rest.split("[")[0].strip().split("-")
                links[a].append(b)
                links[b].append(a)
    return drones, start, end, kinds, links


def cheapest(start: str, end: str, kinds: dict[str, str],
             links: dict[str, list[str]]) -> list[str]:
    """Dijkstra on turns; blocked zones are never entered."""
    best, previous = {start: 0}, {start: start}
    queue = [(0, start)]
    while queue:
        cost, zone = heapq.heappop(queue)
        if zone == end:
            path = [end]
            while path[-1] != start:
                path.append(previous[path[-1]])
            return path[::-1]
        for other in links[zone]:
            if kinds[other] == "blocked":
                continue
            new = cost + COST[kinds[other]]
            if new < best.get(other, new + 1):
                best[other], previous[other] = new, zone
                heapq.heappush(queue, (new, other))
    raise ValueError("no route from start to end")


def main(argv: list[str]) -> int:
    """Print one line per turn."""
    try:
        drones, start, end, kinds, links = parse(argv[1])
        path = cheapest(start, end, kinds, links)
    except (OSError, ValueError, KeyError, IndexError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    for drone in range(1, drones + 1):
        for here, there in zip(path, path[1:]):
            if kinds[there] == "restricted":
                print(f"D{drone}-{here}-{there}")
            print(f"D{drone}-{there}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
