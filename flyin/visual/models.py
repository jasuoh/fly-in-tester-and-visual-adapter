"""Shared data model of the Fly-in project.

Taken from the reference project (42-fly-in-claude): the GUI only reads
these classes. :mod:`flyin.visual.loader` and :mod:`flyin.visual.replay`
build them from any map and any program's output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, Iterator, List, Optional, Tuple


class ZoneType(Enum):
    """Type of a zone; it defines the cost of moving *into* the zone."""

    NORMAL = "normal"
    BLOCKED = "blocked"
    RESTRICTED = "restricted"
    PRIORITY = "priority"

    @property
    def move_cost(self) -> int:
        """Return the number of turns needed to enter a zone of this type.

        Raises:
            ValueError: If the zone type is ``BLOCKED`` (never enterable).
        """
        if self is ZoneType.BLOCKED:
            raise ValueError("blocked zones cannot be entered")
        if self is ZoneType.RESTRICTED:
            return 2
        return 1


@dataclass
class Zone:
    """A node of the network (hub) where drones can wait.

    Attributes:
        name: Unique zone name (never contains dashes or spaces).
        x: Integer x coordinate.
        y: Integer y coordinate.
        zone_type: Zone type, defines movement cost.
        color: Optional colour for the visual representation.
        max_drones: Maximum number of drones in the zone at the same time.
        is_start: True for the unique ``start_hub``.
        is_end: True for the unique ``end_hub``.
    """

    name: str
    x: int
    y: int
    zone_type: ZoneType = ZoneType.NORMAL
    color: Optional[str] = None
    max_drones: int = 1
    is_start: bool = False
    is_end: bool = False

    @property
    def is_passable(self) -> bool:
        """Return True if drones may enter this zone."""
        return self.zone_type is not ZoneType.BLOCKED

    @property
    def has_unlimited_capacity(self) -> bool:
        """Return True for start and end zone (capacity is ignored there)."""
        return self.is_start or self.is_end

    @property
    def move_cost(self) -> int:
        """Return the number of turns needed to move into this zone."""
        return self.zone_type.move_cost


@dataclass
class Connection:
    """A bidirectional edge between two zones.

    Attributes:
        zone_a: Name of the first zone (as written in the map file).
        zone_b: Name of the second zone.
        max_link_capacity: Maximum number of drones on the connection per
            turn, both directions counted together.
    """

    zone_a: str
    zone_b: str
    max_link_capacity: int = 1

    @property
    def key(self) -> FrozenSet[str]:
        """Return an order-independent key identifying the connection."""
        return frozenset((self.zone_a, self.zone_b))

    def other(self, name: str) -> str:
        """Return the zone at the opposite end of ``name``.

        Raises:
            ValueError: If ``name`` is not an end of this connection.
        """
        if name == self.zone_a:
            return self.zone_b
        if name == self.zone_b:
            return self.zone_a
        raise ValueError(f"{name} is not part of connection {self}")

    @staticmethod
    def transit_name(source: str, destination: str) -> str:
        """Return the output name of a connection in flight direction.

        Used for ``D<ID>-<connection>`` lines, e.g. ``"roof1-roof2"``.
        """
        return f"{source}-{destination}"

    def __str__(self) -> str:
        """Return the connection as written in the map file."""
        return f"{self.zone_a}-{self.zone_b}"


@dataclass
class Drone:
    """A drone travelling from the start to the end zone.

    Attributes:
        drone_id: Identifier from 1 to ``nb_drones``.
        position: Name of the zone the drone is in (or has just left when
            it is in transit).
        in_transit_to: Destination zone while flying over a connection
            towards a restricted zone, otherwise None.
        delivered: True once the drone reached the end zone.
    """

    drone_id: int
    position: str
    in_transit_to: Optional[str] = None
    delivered: bool = False

    @property
    def label(self) -> str:
        """Return the output label, e.g. ``"D3"``."""
        return f"D{self.drone_id}"


class Graph:
    """The zone network read from a map file."""

    def __init__(self, nb_drones: int) -> None:
        """Create an empty graph.

        Args:
            nb_drones: Number of drones to route (positive).
        """
        self.nb_drones: int = nb_drones
        self._zones: Dict[str, Zone] = {}
        self._connections: Dict[FrozenSet[str], Connection] = {}
        self._adjacency: Dict[str, List[str]] = {}
        self._start: Optional[str] = None
        self._end: Optional[str] = None

    def add_zone(self, zone: Zone) -> None:
        """Add a zone.

        Raises:
            ValueError: On a duplicate name or a second start/end zone.
        """
        if zone.name in self._zones:
            raise ValueError(f"duplicate zone name '{zone.name}'")
        if zone.is_start:
            if self._start is not None:
                raise ValueError("more than one start_hub")
            self._start = zone.name
        if zone.is_end:
            if self._end is not None:
                raise ValueError("more than one end_hub")
            self._end = zone.name
        self._zones[zone.name] = zone
        self._adjacency[zone.name] = []

    def add_connection(self, connection: Connection) -> None:
        """Add a connection between two existing zones.

        Raises:
            ValueError: On unknown zones, a self loop or a duplicate.
        """
        for name in (connection.zone_a, connection.zone_b):
            if name not in self._zones:
                raise ValueError(f"unknown zone '{name}'")
        if connection.zone_a == connection.zone_b:
            raise ValueError("a zone cannot be connected to itself")
        if connection.key in self._connections:
            raise ValueError(f"duplicate connection '{connection}'")
        self._connections[connection.key] = connection
        self._adjacency[connection.zone_a].append(connection.zone_b)
        self._adjacency[connection.zone_b].append(connection.zone_a)

    @property
    def start(self) -> Zone:
        """Return the start zone.

        Raises:
            ValueError: If no start zone was defined.
        """
        if self._start is None:
            raise ValueError("missing start_hub")
        return self._zones[self._start]

    @property
    def end(self) -> Zone:
        """Return the end zone.

        Raises:
            ValueError: If no end zone was defined.
        """
        if self._end is None:
            raise ValueError("missing end_hub")
        return self._zones[self._end]

    def has_zone(self, name: str) -> bool:
        """Return True if a zone called ``name`` exists."""
        return name in self._zones

    def zone(self, name: str) -> Zone:
        """Return the zone called ``name`` (KeyError if unknown)."""
        return self._zones[name]

    @property
    def zones(self) -> List[Zone]:
        """Return all zones in definition order."""
        return list(self._zones.values())

    @property
    def connections(self) -> List[Connection]:
        """Return all connections in definition order."""
        return list(self._connections.values())

    def neighbors(self, name: str) -> List[str]:
        """Return the names of all zones connected to ``name``."""
        return list(self._adjacency[name])

    def connection(self, a: str, b: str) -> Optional[Connection]:
        """Return the connection between ``a`` and ``b`` or None."""
        return self._connections.get(frozenset((a, b)))

    def __iter__(self) -> Iterator[Zone]:
        """Iterate over all zones."""
        return iter(self._zones.values())

    def __len__(self) -> int:
        """Return the number of zones."""
        return len(self._zones)


@dataclass(frozen=True)
class Move:
    """One entry of an output line.

    Attributes:
        drone_id: The moving drone.
        target: Destination zone name, or the transit name
            ``"<from>-<to>"`` when the drone enters a connection towards a
            restricted zone.
    """

    drone_id: int
    target: str

    def __str__(self) -> str:
        """Return the move in output format, e.g. ``"D1-roof1"``."""
        return f"D{self.drone_id}-{self.target}"


@dataclass
class TurnRecord:
    """Everything that happened during one simulation turn.

    Attributes:
        number: Turn number, starting at 1.
        moves: Moves of this turn, sorted by drone id.
        positions: State *after* the turn for every drone not yet
            delivered before this turn: zone name, or ``"<from>-<to>"``
            while in transit. Drones delivered in this turn map to the
            end zone name; later turns omit them.
    """

    number: int
    moves: List[Move] = field(default_factory=list)
    positions: Dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Issue:
    """A broken rule the GUI marks on the map.

    Attributes:
        turn: 1-based turn whose resulting state breaks the rule (0: the
            whole run).
        message: What is wrong.
        zones: Zones to mark.
        link: Connection to mark, if any.
    """

    turn: int
    message: str
    zones: Tuple[str, ...] = ()
    link: Optional[Tuple[str, str]] = None


@dataclass
class SimulationResult:
    """Result of a complete simulation run.

    Attributes:
        graph: The network.
        turns: One record per output line.
        id_base: Id of the first drone: 1 (``D1..Dn``) or 0 (``D0..``).
        issues: Broken rules to show (empty for a valid solution).
    """

    graph: Graph
    turns: List[TurnRecord] = field(default_factory=list)
    id_base: int = 1
    issues: List[Issue] = field(default_factory=list)

    @property
    def turn_count(self) -> int:
        """Return the number of simulation turns (the score)."""
        return len(self.turns)
