"""A lower bound for the number of turns of any valid solution.

No schedule can beat it, so ``your turns - bound`` is the most you could
still win on a map. It is not always reachable (the exact optimum can be
higher); for the ``challenge`` and ``fuzz`` maps the optimum is known.

Three limits, each a proven minimum:

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


def lower_bound(fly_map: FlyMap) -> int | None:
    """Return the minimum number of turns, or None if there is no route."""
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
