"""A lower bound for the number of turns of any valid solution.

No schedule can beat it, so ``your turns - bound`` is the most you could
still win on a map. It is not always reachable (the exact optimum can be
higher); for the ``challenge`` and ``fuzz`` maps the optimum is known.

Two methods; ``lower_bound`` uses the better one.

**Flow over time** (``flow_bound``, maps up to a few thousand zone-turns):
the zones are copied once per turn and a max-flow checks whether all
drones can reach the end within T turns when zone capacities, connection
capacities per turn and the 2-turn restricted moves are respected, only
the identity of the drones ignored. Every valid schedule is such a flow,
so the smallest T that fits is a lower bound. It matches the exact
optimum on 230 of the 305 maps where the optimum is known.

**Simple limits** (``simple_bound``, any size), each a proven minimum:

* **distance** ``d``: the cheapest route for a single drone (restricted
  zones cost 2 turns).
* **leaving the start**: per turn at most ``K_out`` drones can leave it,
  where every exit counts ``min(max_link_capacity, max_drones of the
  next zone)`` (a zone holds what entered it this turn). The last drone
  leaves in turn ``ceil(n / K_out)`` or later and then still needs
  ``d - 1`` turns.
* **reaching the end**: per turn at most ``K_in`` drones arrive, every
  entrance counts ``min(max_link_capacity, max_drones of the zone before
  it)``. The first arrival is in turn ``d`` or later, so the last one is
  in turn ``d + ceil(n / K_in) - 1`` or later.

On the challenger map this gives 43 (one drone per turn leaves the start,
the route is 19 turns: 24 + 19).
"""

import math

from .mapfile import FlyMap, shortest_cost


def _rate(fly_map: FlyMap, zone: str) -> int:
    """Return how many drones per turn can leave the start or enter the
    end through its connections (``zone`` is one of the two)."""
    total = 0
    for other in fly_map.neighbors(zone):
        if fly_map.zones[other].kind == "blocked":
            continue
        link = fly_map.links[frozenset((zone, other))].capacity
        unlimited = other in (fly_map.start, fly_map.end)
        limit = link if unlimited else min(link,
                                           fly_map.zones[other].max_drones)
        total += max(0, limit)
    return total


def simple_bound(fly_map: FlyMap) -> int | None:
    """Return the distance / start / end bound, or None if there is no
    route."""
    distance = shortest_cost(fly_map)
    if distance is None:
        return None
    drones = fly_map.nb_drones
    bound = distance
    for zone in (fly_map.start, fly_map.end):
        rate = _rate(fly_map, zone)
        if rate:
            bound = max(bound, distance + math.ceil(drones / rate) - 1)
    return bound


def lower_bound(fly_map: FlyMap) -> int | None:
    """Return the minimum number of turns, or None if there is no route.

    The flow bound when the map is small enough, else the simple one.
    """
    simple = simple_bound(fly_map)
    if simple is None:
        return None
    return flow_bound(fly_map, simple) or simple


INF = 1 << 40


class _Dinic:
    """A small integer max-flow (Dinic's algorithm), iterative."""

    def __init__(self) -> None:
        """Start with no nodes."""
        self.adjacent: list[list[int]] = []
        self.target: list[int] = []
        self.capacity: list[int] = []

    def node(self) -> int:
        """Add a node and return its number."""
        self.adjacent.append([])
        return len(self.adjacent) - 1

    def edge(self, a: int, b: int, capacity: int) -> None:
        """Add an edge and its reverse."""
        self.adjacent[a].append(len(self.target))
        self.target.append(b)
        self.capacity.append(capacity)
        self.adjacent[b].append(len(self.target))
        self.target.append(a)
        self.capacity.append(0)

    def flow(self, source: int, sink: int, limit: int) -> int:
        """Return the max flow from ``source`` to ``sink``, at most
        ``limit``."""
        total = 0
        while total < limit:
            level = self._levels(source)
            if level[sink] < 0:
                break
            pointer = [0] * len(self.adjacent)
            while total < limit:
                pushed = self._push(source, sink, limit - total, level,
                                    pointer)
                if not pushed:
                    break
                total += pushed
        return total

    def _levels(self, source: int) -> list[int]:
        """Breadth-first distances in the residual graph."""
        level = [-1] * len(self.adjacent)
        level[source] = 0
        queue = [source]
        for node in queue:
            for edge in self.adjacent[node]:
                other = self.target[edge]
                if self.capacity[edge] > 0 and level[other] < 0:
                    level[other] = level[node] + 1
                    queue.append(other)
        return level

    def _push(self, source: int, sink: int, limit: int, level: list[int],
              pointer: list[int]) -> int:
        """Find one augmenting path along the levels (iterative DFS)."""
        path: list[int] = []
        node = source
        while True:
            if node == sink:
                amount = min([limit] + [self.capacity[e] for e in path])
                for edge in path:
                    self.capacity[edge] -= amount
                    self.capacity[edge ^ 1] += amount
                return amount
            edges = self.adjacent[node]
            while pointer[node] < len(edges):
                edge = edges[pointer[node]]
                other = self.target[edge]
                if self.capacity[edge] > 0 and level[other] == level[node] + 1:
                    break
                pointer[node] += 1
            if pointer[node] == len(edges):
                if not path:
                    return 0
                level[node] = -1
                edge = path.pop()
                node = self.target[edge ^ 1]
                pointer[node] += 1
                continue
            edge = edges[pointer[node]]
            path.append(edge)
            node = self.target[edge]


def _fits(fly_map: FlyMap, turns: int) -> bool:
    """Return whether all drones can reach the end within ``turns`` in a
    relaxed flow over time.

    Every valid schedule is such a flow: zones hold at most ``max_drones``
    at the end of a turn, a connection carries at most its capacity of
    departures per turn (both directions share it) and a move into a zone
    lands ``move cost`` turns later. Only the order of the drones is
    ignored, so ``not fits`` proves that more turns are needed.
    """
    net = _Dinic()
    source = net.node()
    zones = [z for z in fly_map.zones.values() if z.kind != "blocked"]
    cost = {z.name: 2 if z.kind == "restricted" else 1 for z in zones}
    enter: list[dict[str, int]] = []
    leave: list[dict[str, int]] = []
    for _ in range(turns + 1):
        enter.append({})
        leave.append({})
        for zone in zones:
            a, b = net.node(), net.node()
            unlimited = zone.name in (fly_map.start, fly_map.end)
            net.edge(a, b, INF if unlimited else max(0, zone.max_drones))
            enter[-1][zone.name], leave[-1][zone.name] = a, b
    net.edge(source, enter[0][fly_map.start], fly_map.nb_drones)
    for t in range(turns):
        for zone in zones:
            net.edge(leave[t][zone.name], enter[t + 1][zone.name], INF)
        for link in fly_map.links.values():
            if link.a not in cost or link.b not in cost:
                continue
            gate_in, gate_out = net.node(), net.node()
            net.edge(gate_in, gate_out, max(0, link.capacity))
            for here, there in ((link.a, link.b), (link.b, link.a)):
                net.edge(leave[t][here], gate_in, INF)
                if t + cost[there] <= turns:
                    net.edge(gate_out, enter[t + cost[there]][there], INF)
    sink = leave[turns][fly_map.end]
    return net.flow(source, sink, fly_map.nb_drones) >= fly_map.nb_drones


def flow_bound(fly_map: FlyMap, at_least: int,
               max_nodes: int = 60_000) -> int | None:
    """Return the fewest turns the relaxed flow needs, or None when the
    time-expanded network would exceed ``max_nodes`` (huge maps)."""
    per_turn = 2 * len(fly_map.zones) + 2 * len(fly_map.links)

    def fits(turns: int) -> bool | None:
        if per_turn * (turns + 1) > max_nodes:
            return None
        return _fits(fly_map, turns)

    low, step = at_least, 1
    high = low
    while True:
        verdict = fits(high)
        if verdict is None:
            return None
        if verdict:
            break
        low, high, step = high + 1, high + step, step * 2
    while low < high:
        middle = (low + high) // 2
        if fits(middle):
            high = middle
        else:
            low = middle + 1
    return high
