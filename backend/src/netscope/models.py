"""The domain model: nodes, undirected links and demands, and the network.

Three invariants live here rather than in the loaders, so that no caller can
construct a network that breaks them.

**Links and demands have no direction** (R3). Both store an ``Endpoints``
pair that sorts itself, so ``(Paris, Lyon)`` and ``(Lyon, Paris)`` are the
same value and the same dictionary key. Nothing downstream needs to remember
to normalise, and a reversed duplicate in an input file is detectable.

**Transit eligibility is a property of node kind** (R6). Backbone cities and
the aggregation hub forward traffic for others. Data centers and operations
sites are endpoints only. Routing asks the node, so the rule is stated once.

**A network is referentially whole.** ``Network`` rejects a link or demand
naming a node it does not have, so routing never has to defend against it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from math import isfinite

__all__ = [
    "Coordinates",
    "Demand",
    "Endpoints",
    "Link",
    "LinkKind",
    "Network",
    "Node",
    "NodeKind",
]


class NodeKind(StrEnum):
    """What a node is, which decides whether it may forward traffic."""

    BACKBONE_CITY = "backbone-city"
    DATA_CENTER = "data-center"
    OPERATIONS_SITE = "operations-site"
    AGGREGATION_HUB = "aggregation-hub"

    @property
    def can_transit(self) -> bool:
        """R6: only backbone cities and the aggregation hub forward traffic."""
        return self in {NodeKind.BACKBONE_CITY, NodeKind.AGGREGATION_HUB}


class LinkKind(StrEnum):
    """Where a link came from, which decides how its capacity was set."""

    BACKBONE = "backbone"
    ACCESS = "access"


@dataclass(frozen=True, slots=True)
class Coordinates:
    """A geographical position.

    SNDlib names these x and y, where x is longitude and y is latitude. The
    names are kept so the model reads like the source file, and the meaning
    is recorded here once.
    """

    x: float
    y: float

    @property
    def longitude(self) -> float:
        return self.x

    @property
    def latitude(self) -> float:
        return self.y


@dataclass(frozen=True, order=True, slots=True)
class Endpoints:
    """An unordered pair of distinct node ids, stored in sorted order.

    Construct with either ordering and get the same value back. Sorting in
    ``__post_init__`` rather than at every call site is what makes
    undirectedness an invariant instead of a convention.
    """

    a: str
    b: str

    def __post_init__(self) -> None:
        if self.a == self.b:
            raise ValueError(f"endpoints must be distinct, got {self.a!r} twice")
        if self.a > self.b:
            # Hold the original before overwriting, or the second assignment
            # reads the value the first one just wrote and both ends become
            # the same string.
            low, high = self.b, self.a
            object.__setattr__(self, "a", low)
            object.__setattr__(self, "b", high)

    def other(self, node_id: str) -> str:
        """The endpoint that is not ``node_id``."""
        if node_id == self.a:
            return self.b
        if node_id == self.b:
            return self.a
        raise KeyError(f"{node_id!r} is not an endpoint of {self}")

    def __contains__(self, node_id: object) -> bool:
        return node_id in (self.a, self.b)

    def __iter__(self) -> Iterator[str]:
        yield self.a
        yield self.b

    def __str__(self) -> str:
        return f"{self.a}--{self.b}"


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    kind: NodeKind
    coordinates: Coordinates

    @property
    def can_transit(self) -> bool:
        return self.kind.can_transit


@dataclass(frozen=True, slots=True)
class Link:
    id: str
    endpoints: Endpoints
    capacity: float
    kind: LinkKind

    def __post_init__(self) -> None:
        # isfinite, not a bare > 0 comparison: float("nan") <= 0 is False, so a
        # NaN capacity would otherwise pass silently and then poison every
        # utilization computed from it. An independent review traced this to
        # NETSCOPE_BACKBONE_CAPACITY, which goes through float() with no
        # isfinite check of its own before it ever reaches here; this is the
        # one place every capacity value passes through regardless of source,
        # so it is the right place to close the gap.
        if not isfinite(self.capacity) or self.capacity <= 0:
            raise ValueError(f"link {self.id!r} needs a positive capacity, got {self.capacity}")


@dataclass(frozen=True, slots=True)
class Demand:
    id: str
    endpoints: Endpoints
    volume: float

    def __post_init__(self) -> None:
        # Same reasoning as Link.capacity above: isfinite first, so NaN cannot
        # slip past a bare > 0 comparison.
        if not isfinite(self.volume) or self.volume <= 0:
            raise ValueError(f"demand {self.id!r} needs a positive volume, got {self.volume}")


@dataclass(frozen=True, eq=False)
class Network:
    """A whole network: every link and demand names a node that exists.

    The derived views are cached because the network is immutable and both
    the routing code and the failure sweep walk them repeatedly. That cache
    is why this class alone does not use ``slots``: ``cached_property`` needs
    an instance dictionary to write into.
    """

    nodes: Mapping[str, Node]
    links: Mapping[str, Link]
    demands: Sequence[Demand]

    def __post_init__(self) -> None:
        for link in self.links.values():
            for node_id in link.endpoints:
                if node_id not in self.nodes:
                    raise ValueError(f"link {link.id!r} names unknown node {node_id!r}")
        for demand in self.demands:
            for node_id in demand.endpoints:
                if node_id not in self.nodes:
                    raise ValueError(f"demand {demand.id!r} names unknown node {node_id!r}")

    @cached_property
    def adjacency(self) -> Mapping[str, Mapping[str, str]]:
        """Neighbour id to the id of the link reaching it."""
        out: dict[str, dict[str, str]] = {node_id: {} for node_id in self.nodes}
        for link in self.links.values():
            out[link.endpoints.a][link.endpoints.b] = link.id
            out[link.endpoints.b][link.endpoints.a] = link.id
        return out

    @cached_property
    def link_by_endpoints(self) -> Mapping[Endpoints, str]:
        return {link.endpoints: link.id for link in self.links.values()}

    @cached_property
    def transit_nodes(self) -> frozenset[str]:
        """R6: the nodes permitted to forward traffic for others."""
        return frozenset(n.id for n in self.nodes.values() if n.can_transit)

    @property
    def total_demand(self) -> float:
        return sum(d.volume for d in self.demands)
