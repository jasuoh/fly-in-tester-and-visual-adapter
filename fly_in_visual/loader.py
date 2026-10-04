"""Turn the tester's independent map reader into the GUI's graph.

The visualizer never uses the program under test to read a map: it reuses
:mod:`fly_in_tester.mapfile`, the same reader the checker trusts.
"""

from pathlib import Path

from fly_in_tester.mapfile import FlyMap, MapError, read_map
from fly_in_visual.models import Connection, Graph, Zone, ZoneType


def graph_from_map(fly_map: FlyMap) -> Graph:
    """Build a :class:`Graph` from a parsed map.

    Raises:
        MapError: If a connection names an unknown zone or a zone itself.
    """
    graph = Graph(fly_map.nb_drones)
    if fly_map.start not in fly_map.zones or fly_map.end not in fly_map.zones:
        raise MapError("start_hub or end_hub is not a zone")
    for zone in fly_map.zones.values():
        graph.add_zone(Zone(
            name=zone.name, x=zone.x, y=zone.y,
            zone_type=ZoneType(zone.kind), color=zone.color,
            max_drones=zone.max_drones,
            is_start=zone.name == fly_map.start,
            is_end=zone.name == fly_map.end,
        ))
    for link in fly_map.links.values():
        try:
            graph.add_connection(Connection(link.a, link.b, link.capacity))
        except ValueError as error:
            raise MapError(f"connection {link.a}-{link.b}: {error}") from error
    return graph


def load_graph(path: str | Path) -> Graph:
    """Read the map at ``path`` and return its graph.

    Raises:
        fly_in_tester.mapfile.MapError: If the map cannot be read.
        OSError: If the file cannot be opened.
    """
    return graph_from_map(read_map(path))
