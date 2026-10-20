"""Minimum-hop routing with an equal split per path (R5, R6), plus connectivity (R7a).

Every number the application reports comes from this module, so it is written
to be read rather than to be clever.

**The rule.** R5 routes each demand over the minimum-hop path or paths between
its endpoints and, where there is more than one, splits the demand equally per
path. D4 settled that reading: three minimum-hop paths carry a third each,
which is not what splitting per hop at every node would give.

**R6 without a special case.** Only backbone cities and the aggregation hub
forward traffic for others. The breadth-first search encodes that by deciding
whether to *expand* a node rather than whether to *visit* it: a node is
expanded only when it is the search's own source or when the network says it
may transit. A data center is therefore reachable, and so can end a path, but
no path continues through it.

**Counting, not enumerating.** The obvious implementation of an equal split is
to list the minimum-hop paths and divide. The number of equal-length paths can
grow exponentially with the graph, so D7 keeps enumeration out of the shipped
path and uses it as a test-only reference instead. What this module does
instead is exact and linear in the number of links per demand:

1. Breadth-first search from the source gives every node's hop distance and
   the predecessor directed acyclic graph of minimum-hop edges.
2. ``from_source[u]`` counts minimum-hop paths from the source to ``u``, read
   off the DAG in increasing distance order.
3. ``to_target[v]`` counts them from ``v`` to the target, read off the same
   DAG in decreasing distance order. A node that cannot reach the target
   counts zero and so contributes nothing.
4. A DAG edge from ``u`` to ``v`` lies on ``from_source[u] * to_target[v]`` of
   the ``total`` minimum-hop paths, so the link under it carries that fraction
   of the demand.

The counts are integers, so step 4 divides once per edge and nothing
accumulates rounding. Per-link contributions are then summed with
``math.fsum``, which is exact for a list of floats, and are never rounded:
presentation decides how to show 390.5 of 550, not this module.

**Failures are an argument, not a second code path.** Re-routing after a
failure is the same operation as routing, so ``route`` takes the failed sets
and works on the surviving graph. A link is a casualty of a failed node at
either end, so it neither carries traffic nor appears in the result.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from netscope.models import Demand, Network

__all__ = [
    "RoutingResult",
    "ShortestPathDag",
    "connected_components",
    "route",
    "shortest_path_dag",
]

#: Neighbour id to the id of the link reaching it, over surviving elements only.
type _Adjacency = Mapping[str, Mapping[str, str]]

#: A node's minimum-hop predecessors, each paired with the link reaching it.
type _Predecessors = Mapping[str, tuple[tuple[str, str], ...]]


@dataclass(frozen=True, slots=True)
class ShortestPathDag:
    """The minimum-hop reachability of one source over a surviving graph.

    ``predecessors[v]`` holds every ``(u, link_id)`` with ``u`` one hop closer
    to the source than ``v``, so the set of minimum-hop paths to ``v`` is
    exactly the set of chains back through it. Public because the test suite
    checks that set against ``networkx``; nothing in the application walks it.
    """

    source: str
    distance: Mapping[str, int]
    predecessors: _Predecessors


@dataclass(frozen=True, slots=True)
class RoutingResult:
    """What routing a whole network produced.

    The two demand buckets are kept apart because R8 reports them separately:
    a demand with an endpoint on a failed node was never going to be carried,
    which is a different finding from one whose path has gone.
    """

    #: Link id to units carried. Every surviving link is present, zero if unused.
    link_loads: Mapping[str, float]
    #: Both endpoints alive, but no legal path remains.
    undeliverable: tuple[Demand, ...]
    #: At least one endpoint is a failed node.
    endpoint_affected: tuple[Demand, ...]


def route(
    network: Network,
    *,
    failed_nodes: frozenset[str] = frozenset(),
    failed_links: frozenset[str] = frozenset(),
) -> RoutingResult:
    """Route every demand over the surviving graph under R5 and R6.

    Args:
        network: The network to route.
        failed_nodes: Node ids treated as absent, along with their links.
        failed_links: Link ids treated as absent.

    Returns:
        The per-link load and the two buckets of demands that were not carried.

    Raises:
        ValueError: If either failed set names an id the network does not have.
            A typo from the API layer is a bug worth stopping for, not
            something to route around silently.
    """
    _reject_unknown(network, failed_nodes, failed_links)
    adjacency = _surviving_adjacency(network, failed_nodes, failed_links)

    # One list per link, summed once at the end: fsum over the whole list is
    # exact, where a repeated += would accumulate error demand by demand.
    contributions: dict[str, list[float]] = {
        link_id: [] for node in adjacency.values() for link_id in node.values()
    }
    undeliverable: list[Demand] = []
    endpoint_affected: list[Demand] = []

    dags: dict[str, ShortestPathDag] = {}
    for demand in network.demands:
        source, target = demand.endpoints.a, demand.endpoints.b
        if source in failed_nodes or target in failed_nodes:
            endpoint_affected.append(demand)
            continue
        if source not in dags:
            # Demands share endpoints heavily, R4 alone gives every operations
            # site the same two targets, so the search is cached per source.
            dags[source] = _dag(adjacency, network.transit_nodes, source)
        dag = dags[source]
        if target not in dag.distance:
            undeliverable.append(demand)
            continue
        _accumulate(dag, target, demand.volume, contributions)

    return RoutingResult(
        link_loads=MappingProxyType(
            {link_id: math.fsum(values) for link_id, values in contributions.items()}
        ),
        undeliverable=tuple(undeliverable),
        endpoint_affected=tuple(endpoint_affected),
    )


def shortest_path_dag(
    network: Network,
    source: str,
    *,
    failed_nodes: frozenset[str] = frozenset(),
    failed_links: frozenset[str] = frozenset(),
) -> ShortestPathDag:
    """The minimum-hop predecessor DAG rooted at ``source``, honouring R6.

    Raises:
        ValueError: If ``source`` or either failed set names an unknown id, or
            if ``source`` is itself failed and so has no graph to search.
    """
    _reject_unknown(network, failed_nodes, failed_links)
    if source not in network.nodes:
        raise ValueError(f"unknown node id {source!r}")
    if source in failed_nodes:
        raise ValueError(f"node {source!r} has failed, so it cannot be a source")
    adjacency = _surviving_adjacency(network, failed_nodes, failed_links)
    return _dag(adjacency, network.transit_nodes, source)


def connected_components(
    network: Network,
    *,
    failed_nodes: frozenset[str] = frozenset(),
    failed_links: frozenset[str] = frozenset(),
) -> tuple[frozenset[str], ...]:
    """The components of the surviving graph, for R7a.

    Connectivity is judged on the plain graph, ignoring R6, because R7a asks
    whether the network is still in one piece and not whether every pair of
    nodes can exchange traffic. A site stranded behind its own failed access
    link is a partition under D12, while applying the transit rule here would
    instead make every leaf site its own component in the healthy network too.

    Returns:
        One frozenset per component, ordered by their sorted members so that
        the same graph always yields the same tuple.

    Raises:
        ValueError: If either failed set names an id the network does not have.
    """
    _reject_unknown(network, failed_nodes, failed_links)
    adjacency = _surviving_adjacency(network, failed_nodes, failed_links)

    seen: set[str] = set()
    components: list[frozenset[str]] = []
    for start in adjacency:
        if start in seen:
            continue
        component: set[str] = {start}
        seen.add(start)
        queue = deque([start])
        while queue:
            for neighbour in adjacency[queue.popleft()]:
                if neighbour not in component:
                    component.add(neighbour)
                    seen.add(neighbour)
                    queue.append(neighbour)
        components.append(frozenset(component))
    return tuple(sorted(components, key=sorted))


def _reject_unknown(
    network: Network, failed_nodes: Iterable[str], failed_links: Iterable[str]
) -> None:
    unknown_nodes = sorted(set(failed_nodes) - set(network.nodes))
    if unknown_nodes:
        raise ValueError(f"unknown node ids in the failed set: {', '.join(unknown_nodes)}")
    unknown_links = sorted(set(failed_links) - set(network.links))
    if unknown_links:
        raise ValueError(f"unknown link ids in the failed set: {', '.join(unknown_links)}")


def _surviving_adjacency(
    network: Network, failed_nodes: frozenset[str], failed_links: frozenset[str]
) -> _Adjacency:
    """Adjacency over what is left, with no entry for a failed node or link."""
    if not failed_nodes and not failed_links:
        return network.adjacency
    out: dict[str, dict[str, str]] = {
        node_id: {} for node_id in network.nodes if node_id not in failed_nodes
    }
    for link_id, link in network.links.items():
        if link_id in failed_links:
            continue
        a, b = link.endpoints.a, link.endpoints.b
        if a in failed_nodes or b in failed_nodes:
            continue
        out[a][b] = link_id
        out[b][a] = link_id
    return out


def _dag(adjacency: _Adjacency, transit: frozenset[str], source: str) -> ShortestPathDag:
    """Breadth-first search from ``source``, recording minimum-hop predecessors."""
    distance: dict[str, int] = {source: 0}
    predecessors: dict[str, list[tuple[str, str]]] = {}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        # R6 lives here: a node that may not transit is still reached, and so
        # may end a path, but it is never expanded, so no path runs through it.
        if node != source and node not in transit:
            continue
        next_distance = distance[node] + 1
        for neighbour, link_id in adjacency[node].items():
            if neighbour not in distance:
                distance[neighbour] = next_distance
                predecessors[neighbour] = [(node, link_id)]
                queue.append(neighbour)
            elif distance[neighbour] == next_distance:
                predecessors[neighbour].append((node, link_id))
    return ShortestPathDag(
        source=source,
        distance=MappingProxyType(distance),
        predecessors=MappingProxyType(
            {node: tuple(arrivals) for node, arrivals in predecessors.items()}
        ),
    )


def _accumulate(
    dag: ShortestPathDag, target: str, volume: float, contributions: dict[str, list[float]]
) -> None:
    """Add this demand's share of ``volume`` to every link on a minimum-hop path."""
    by_distance = sorted(dag.distance, key=lambda node: dag.distance[node])

    from_source: dict[str, int] = {dag.source: 1}
    for node in by_distance:
        if node != dag.source:
            from_source[node] = sum(from_source[u] for u, _ in dag.predecessors[node])

    # Walked from the far side inwards, so a node's own count is final before
    # it is pushed back to predecessors, which are strictly closer to the source.
    to_target: dict[str, int] = {target: 1}
    for node in reversed(by_distance):
        reaching = to_target.get(node, 0)
        if not reaching:
            # Nothing past the target, and nothing in a dead end, is on a path.
            continue
        for predecessor, _ in dag.predecessors.get(node, ()):
            to_target[predecessor] = to_target.get(predecessor, 0) + reaching

    total = from_source[target]
    for node, arrivals in dag.predecessors.items():
        reaching = to_target.get(node, 0)
        if not reaching:
            continue
        for predecessor, link_id in arrivals:
            # R5: this edge lies on this many of the total minimum-hop paths.
            on_paths = from_source[predecessor] * reaching
            if on_paths:
                contributions[link_id].append(volume * on_paths / total)
