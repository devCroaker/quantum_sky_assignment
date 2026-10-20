"""Routing tests: three independent legs, as the testing policy requires.

Agreement between an implementation and itself is not evidence, so the router
is checked three ways that do not share a mechanism.

**Leg 1, the hand-worked fixture.** ``scripts/make_fixtures.py`` derives the
link loads of a seven-node cut-down on paper in its module docstring, and
``contracts/fixtures/baseline.json`` holds the result. The same network is
rebuilt here from model objects, the eight expected loads are restated as
literals with the hand reasoning on each, and the committed JSON is read as
well so that the fixture the front end builds against and the router that
will later feed it are pinned to each other.

**Leg 2, a naive reference implementation.** ``_reference_route`` below
enumerates every minimum-hop path and divides the demand by their count,
which is the obvious reading of R5 that D7 rejected for the shipped code
because the path count can grow exponentially. It shares no code with
``netscope.routing``: it rebuilds adjacency itself and derives the transit set
from node kinds rather than asking ``Network.transit_nodes``. The two are
compared on the real merged network, on the fixture, on random graphs with a
fixed seed, and under single node and single link failures.

**Leg 3, networkx as an oracle for path sets.** ``networkx.all_shortest_paths``
is an outside statement of which paths are minimum-hop, checked against the
set of chains admitted by our predecessor DAG.

Every expected number here comes from one of three places and says which: the
"verified facts" table in ``CLAUDE.md``, the hand calculation in the fixture
generator, or a structural fact of ``data/sites.csv`` quoted in the comment
that uses it.
"""

from __future__ import annotations

import json
import random
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from itertools import pairwise
from pathlib import Path

import networkx as nx
import pytest

from netscope.loaders.merge import build_network
from netscope.loaders.sites_csv import load_sites
from netscope.loaders.sndlib_xml import load_backbone
from netscope.models import (
    Coordinates,
    Demand,
    Endpoints,
    Link,
    LinkKind,
    Network,
    Node,
    NodeKind,
)
from netscope.routing import (
    RoutingResult,
    ShortestPathDag,
    connected_components,
    route,
    shortest_path_dag,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SNDLIB = DATA / "nobel-eu.xml"
SITES = DATA / "sites.csv"
BASELINE_FIXTURE = ROOT / "contracts" / "fixtures" / "baseline.json"

# Loads are compared with pytest.approx throughout, because a third of ten
# units and most other equal splits are not exactly representable. Nothing in
# the router or in these tests is rounded.

# ---------------------------------------------------------------------------
# Networks under test
# ---------------------------------------------------------------------------

#: The seven-node cut-down from scripts/make_fixtures.py. Positions are the
#: real SNDlib ones for fidelity with the committed fixture; routing never
#: looks at geometry.
_FIXTURE_NODES: Mapping[str, tuple[NodeKind, float, float]] = {
    "Hamburg": (NodeKind.BACKBONE_CITY, 10.0, 53.33),
    "Copenhagen": (NodeKind.BACKBONE_CITY, 12.32, 55.41),
    "Berlin": (NodeKind.BACKBONE_CITY, 13.21, 52.31),
    "Warsaw": (NodeKind.BACKBONE_CITY, 20.59, 52.14),
    "DC-NORTH": (NodeKind.DATA_CENTER, 10.41, 53.87),
    "HUB-EAST": (NodeKind.AGGREGATION_HUB, 21.39, 51.74),
    "OPS-EAST-1": (NodeKind.OPERATIONS_SITE, 22.19, 51.34),
}

_FIXTURE_LINKS: Mapping[str, tuple[str, str, float, LinkKind]] = {
    "ACC-DC-NORTH-Copenhagen": ("Copenhagen", "DC-NORTH", 200.0, LinkKind.ACCESS),
    "ACC-DC-NORTH-Hamburg": ("DC-NORTH", "Hamburg", 200.0, LinkKind.ACCESS),
    "ACC-HUB-EAST-Warsaw": ("HUB-EAST", "Warsaw", 80.0, LinkKind.ACCESS),
    "ACC-OPS-EAST-1-HUB-EAST": ("HUB-EAST", "OPS-EAST-1", 40.0, LinkKind.ACCESS),
    "L1": ("Copenhagen", "Hamburg", 550.0, LinkKind.BACKBONE),
    "L2": ("Berlin", "Hamburg", 550.0, LinkKind.BACKBONE),
    "L3": ("Berlin", "Copenhagen", 550.0, LinkKind.BACKBONE),
    "L4": ("Berlin", "Warsaw", 550.0, LinkKind.BACKBONE),
}

_FIXTURE_DEMANDS: Sequence[tuple[str, str, str, float]] = (
    ("D1", "OPS-EAST-1", "DC-NORTH", 10.0),
    ("D2", "Hamburg", "Warsaw", 100.0),
)

# Hand-derived in the docstring of scripts/make_fixtures.py. D2 has one
# two-hop path, Hamburg-Berlin-Warsaw, so it takes all 100 units. D1 has two
# five-hop paths, OPS-EAST-1-HUB-EAST-Warsaw-Berlin then either Hamburg or
# Copenhagen, so under R5 each carries 5 of its 10 units.
HAND_WORKED_LOADS: Mapping[str, float] = {
    "ACC-OPS-EAST-1-HUB-EAST": 10.0,  # on both of D1's minimum-hop paths
    "ACC-HUB-EAST-Warsaw": 10.0,  # likewise
    "L4": 110.0,  # Berlin-Warsaw: 100 from D2 plus 10 from D1
    "L2": 105.0,  # Hamburg-Berlin: 100 from D2 plus D1's 5 via Hamburg
    "L3": 5.0,  # Copenhagen-Berlin: D1's Copenhagen path only
    "ACC-DC-NORTH-Hamburg": 5.0,  # D1's Hamburg path only
    "ACC-DC-NORTH-Copenhagen": 5.0,  # D1's Copenhagen path only
    "L1": 0.0,  # Hamburg-Copenhagen is on no minimum-hop path
}


def _network(
    nodes: Mapping[str, tuple[NodeKind, float, float]],
    links: Mapping[str, tuple[str, str, float, LinkKind]],
    demands: Sequence[tuple[str, str, str, float]],
) -> Network:
    return Network(
        nodes={
            node_id: Node(id=node_id, kind=kind, coordinates=Coordinates(x=x, y=y))
            for node_id, (kind, x, y) in nodes.items()
        },
        links={
            link_id: Link(id=link_id, endpoints=Endpoints(a, b), capacity=capacity, kind=kind)
            for link_id, (a, b, capacity, kind) in links.items()
        },
        demands=tuple(
            Demand(id=demand_id, endpoints=Endpoints(a, b), volume=volume)
            for demand_id, a, b, volume in demands
        ),
    )


@pytest.fixture(scope="module")
def fixture_network() -> Network:
    return _network(_FIXTURE_NODES, _FIXTURE_LINKS, _FIXTURE_DEMANDS)


@pytest.fixture(scope="module")
def real_network() -> Network:
    return build_network(load_backbone(SNDLIB), load_sites(SITES), sites_file=str(SITES))


# ---------------------------------------------------------------------------
# Leg 2: the enumerating reference implementation
# ---------------------------------------------------------------------------


def _reference_route(
    network: Network,
    *,
    failed_nodes: frozenset[str] = frozenset(),
    failed_links: frozenset[str] = frozenset(),
) -> tuple[dict[str, float], tuple[str, ...], tuple[str, ...]]:
    """Route by listing every minimum-hop path and dividing the demand by their count.

    This is R5 read literally, and the implementation D7 rejected for the
    shipped path. It deliberately duplicates the graph walk rather than
    importing anything from ``netscope.routing``, so a mistake in one is not a
    mistake in both.

    Returns:
        The surviving links' loads, the undeliverable demand ids and the
        endpoint-affected demand ids.
    """
    alive = {
        link_id: link
        for link_id, link in network.links.items()
        if link_id not in failed_links
        and link.endpoints.a not in failed_nodes
        and link.endpoints.b not in failed_nodes
    }
    neighbours: dict[str, list[str]] = {
        node_id: [] for node_id in network.nodes if node_id not in failed_nodes
    }
    link_between: dict[frozenset[str], str] = {}
    for link_id, link in alive.items():
        neighbours[link.endpoints.a].append(link.endpoints.b)
        neighbours[link.endpoints.b].append(link.endpoints.a)
        link_between[frozenset((link.endpoints.a, link.endpoints.b))] = link_id

    # R6 spelled out from the kinds, rather than asking Network.transit_nodes,
    # so the two implementations do not share even that.
    may_transit = {
        node.id
        for node in network.nodes.values()
        if node.kind in {NodeKind.BACKBONE_CITY, NodeKind.AGGREGATION_HUB}
    }

    loads = dict.fromkeys(alive, 0.0)
    undeliverable: list[str] = []
    endpoint_affected: list[str] = []
    for demand in network.demands:
        source, target = demand.endpoints.a, demand.endpoints.b
        if source in failed_nodes or target in failed_nodes:
            endpoint_affected.append(demand.id)
            continue
        paths = _enumerate_minimum_hop_paths(neighbours, may_transit, source, target)
        if not paths:
            undeliverable.append(demand.id)
            continue
        share = demand.volume / len(paths)
        for path in paths:
            for first, second in pairwise(path):
                loads[link_between[frozenset((first, second))]] += share
    return loads, tuple(undeliverable), tuple(endpoint_affected)


def _enumerate_minimum_hop_paths(
    neighbours: Mapping[str, Sequence[str]],
    may_transit: frozenset[str] | set[str],
    source: str,
    target: str,
) -> tuple[tuple[str, ...], ...]:
    """Every minimum-hop legal path from ``source`` to ``target``.

    Grows whole paths a hop at a time and stops at the first length that
    reaches the target, so every path returned has the same number of hops and
    none is longer than it needs to be. A path is extended only from a node
    that may transit, which is how R6 applies: the target is reached but never
    extended, so it may be a data center.
    """
    frontier: list[tuple[str, ...]] = [(source,)]
    while frontier:
        arrived = tuple(path for path in frontier if path[-1] == target)
        if arrived:
            return arrived
        grown: list[tuple[str, ...]] = []
        for path in frontier:
            last = path[-1]
            if last != source and last not in may_transit:
                continue
            for neighbour in neighbours[last]:
                if neighbour not in path:
                    grown.append((*path, neighbour))
        frontier = grown
    return ()


def _assert_agrees(
    network: Network,
    *,
    failed_nodes: frozenset[str] = frozenset(),
    failed_links: frozenset[str] = frozenset(),
) -> RoutingResult:
    """The shipped router and the enumerating reference must give one answer."""
    ours = route(network, failed_nodes=failed_nodes, failed_links=failed_links)
    loads, undeliverable, endpoint_affected = _reference_route(
        network, failed_nodes=failed_nodes, failed_links=failed_links
    )
    assert dict(ours.link_loads) == pytest.approx(loads)
    assert tuple(d.id for d in ours.undeliverable) == undeliverable
    assert tuple(d.id for d in ours.endpoint_affected) == endpoint_affected
    return ours


# ---------------------------------------------------------------------------
# Leg 3: networkx as an oracle for path sets
# ---------------------------------------------------------------------------


def _dag_path_set(dag: ShortestPathDag, target: str) -> set[tuple[str, ...]]:
    """Every path the predecessor DAG admits from its source to ``target``.

    Enumeration belongs here and not in the shipped code: this walks the DAG
    the router only counts, so the two legs disagree if the DAG is wrong.
    """
    if target not in dag.distance:
        return set()
    complete: set[tuple[str, ...]] = set()
    partial: list[tuple[str, ...]] = [(target,)]
    while partial:
        tail = partial.pop()
        head = tail[0]
        if head == dag.source:
            complete.add(tail)
            continue
        for predecessor, _ in dag.predecessors[head]:
            partial.append((predecessor, *tail))
    return complete


def _oracle_path_set(
    network: Network,
    source: str,
    target: str,
    *,
    failed_nodes: frozenset[str] = frozenset(),
    failed_links: frozenset[str] = frozenset(),
) -> set[tuple[str, ...]]:
    """``networkx.all_shortest_paths`` over a graph with R6 applied up front.

    The restriction is applied by deleting every non-transit node except the
    two endpoints before asking, rather than by filtering the paths networkx
    returns. Filtering afterwards would be wrong and not merely slower: where
    an illegal route is strictly shorter than every legal one, the shortest
    paths networkx reports are all illegal, and filtering them leaves nothing
    where the right answer is the longer legal route.
    """
    graph = nx.Graph()
    graph.add_nodes_from(node_id for node_id in network.nodes if node_id not in failed_nodes)
    for link_id, link in network.links.items():
        if link_id in failed_links:
            continue
        if link.endpoints.a in failed_nodes or link.endpoints.b in failed_nodes:
            continue
        graph.add_edge(link.endpoints.a, link.endpoints.b)
    for node in network.nodes.values():
        if not node.can_transit and node.id not in {source, target} and node.id in graph:
            graph.remove_node(node.id)
    if source not in graph or target not in graph or not nx.has_path(graph, source, target):
        return set()
    paths: set[tuple[str, ...]] = {
        tuple(path) for path in nx.all_shortest_paths(graph, source, target)
    }
    return paths


def _assert_path_sets_agree(
    network: Network,
    *,
    failed_nodes: frozenset[str] = frozenset(),
    failed_links: frozenset[str] = frozenset(),
) -> None:
    for demand in network.demands:
        source, target = demand.endpoints.a, demand.endpoints.b
        if source in failed_nodes or target in failed_nodes:
            continue
        dag = shortest_path_dag(
            network, source, failed_nodes=failed_nodes, failed_links=failed_links
        )
        assert _dag_path_set(dag, target) == _oracle_path_set(
            network, source, target, failed_nodes=failed_nodes, failed_links=failed_links
        )


# ---------------------------------------------------------------------------
# Random graphs, shared by legs 2 and 3
# ---------------------------------------------------------------------------

#: Fixed so a failure is reproducible, and large enough to cover disconnected
#: graphs and demands with no legal path, both of which are asserted below.
RANDOM_SEEDS = tuple(range(40))


def _random_network(seed: int) -> Network:
    """A small random network: size, density, kinds and demands all vary."""
    rng = random.Random(seed)
    size = rng.randint(2, 11)
    node_ids = [f"N{index:02d}" for index in range(size)]
    kinds = {
        # Weighted so that most graphs have some nodes that may not transit,
        # which is the case R6 is about, without making transit the exception.
        node_id: rng.choice(
            [
                NodeKind.BACKBONE_CITY,
                NodeKind.BACKBONE_CITY,
                NodeKind.AGGREGATION_HUB,
                NodeKind.DATA_CENTER,
                NodeKind.OPERATIONS_SITE,
            ]
        )
        for node_id in node_ids
    }
    pairs = [(a, b) for index, a in enumerate(node_ids) for b in node_ids[index + 1 :]]
    density = rng.choice([0.15, 0.3, 0.5, 0.8])
    chosen = [pair for pair in pairs if rng.random() < density]
    nodes = {node_id: (kinds[node_id], float(index), 0.0) for index, node_id in enumerate(node_ids)}
    links = {
        f"E{index:02d}": (a, b, float(rng.randint(1, 100)), LinkKind.BACKBONE)
        for index, (a, b) in enumerate(chosen)
    }
    demand_pairs = rng.sample(pairs, k=min(len(pairs), rng.randint(1, 6)))
    demands = [
        (f"D{index:02d}", a, b, float(rng.randint(1, 30)))
        for index, (a, b) in enumerate(demand_pairs)
    ]
    return _network(nodes, links, demands)


# ---------------------------------------------------------------------------
# Leg 1
# ---------------------------------------------------------------------------


class TestHandWorkedFixture:
    """The first worked example of R5 and R6, derived on paper in P4.

    Per D17 these numbers come from the fixture generator's docstring and not
    from any implementation, so they can disagree with the router when the
    router is wrong.
    """

    def test_every_link_load_matches_the_hand_calculation(self, fixture_network: Network) -> None:
        result = route(fixture_network)
        assert dict(result.link_loads) == pytest.approx(dict(HAND_WORKED_LOADS))

    def test_the_two_demands_are_both_carried(self, fixture_network: Network) -> None:
        result = route(fixture_network)
        assert result.undeliverable == ()
        assert result.endpoint_affected == ()

    def test_the_computed_loads_match_the_committed_fixture(self, fixture_network: Network) -> None:
        """Ties the fixture the front end builds against to the router."""
        payload = json.loads(BASELINE_FIXTURE.read_text(encoding="utf-8"))
        committed = {entry["link_id"]: entry["load"] for entry in payload["link_loads"]}
        assert dict(route(fixture_network).link_loads) == pytest.approx(committed)

    def test_d1_splits_over_exactly_the_two_hand_worked_paths(
        self, fixture_network: Network
    ) -> None:
        """Both are five hops, so R5 gives each 5 of D1's 10 units."""
        dag = shortest_path_dag(fixture_network, "DC-NORTH")
        assert _dag_path_set(dag, "OPS-EAST-1") == {
            ("DC-NORTH", "Hamburg", "Berlin", "Warsaw", "HUB-EAST", "OPS-EAST-1"),
            ("DC-NORTH", "Copenhagen", "Berlin", "Warsaw", "HUB-EAST", "OPS-EAST-1"),
        }

    def test_the_reference_implementation_agrees(self, fixture_network: Network) -> None:
        _assert_agrees(fixture_network)

    def test_networkx_agrees_on_the_path_sets(self, fixture_network: Network) -> None:
        _assert_path_sets_agree(fixture_network)

    def test_failing_berlin_strands_both_demands(self, fixture_network: Network) -> None:
        """Also hand-worked in the generator: Berlin carries every east-west path."""
        result = _assert_agrees(fixture_network, failed_nodes=frozenset({"Berlin"}))
        assert tuple(d.id for d in result.undeliverable) == ("D1", "D2")
        assert result.endpoint_affected == ()
        assert set(result.link_loads.values()) == {0.0}


# ---------------------------------------------------------------------------
# Leg 2
# ---------------------------------------------------------------------------


class TestAgreementWithTheEnumeratingReference:
    def test_on_the_real_network(self, real_network: Network) -> None:
        _assert_agrees(real_network)

    @pytest.mark.parametrize("seed", RANDOM_SEEDS)
    def test_on_random_graphs(self, seed: int) -> None:
        _assert_agrees(_random_network(seed))

    @pytest.mark.parametrize("seed", RANDOM_SEEDS[:12])
    def test_on_random_graphs_with_a_failure(self, seed: int) -> None:
        """Failures on a random graph, which is where the odd shapes turn up."""
        network = _random_network(seed)
        rng = random.Random(seed + 1_000)
        failed_node = rng.choice(sorted(network.nodes))
        _assert_agrees(network, failed_nodes=frozenset({failed_node}))
        if network.links:
            failed_link = rng.choice(sorted(network.links))
            _assert_agrees(network, failed_links=frozenset({failed_link}))

    def test_the_random_graphs_cover_the_awkward_cases(self) -> None:
        """The generator is only worth its seeds if it reaches both edge cases."""
        disconnected = 0
        stranded = 0
        for seed in RANDOM_SEEDS:
            network = _random_network(seed)
            if len(connected_components(network)) > 1:
                disconnected += 1
            if route(network).undeliverable:
                stranded += 1
        assert disconnected > 0
        assert stranded > 0

    @pytest.mark.parametrize(
        "failed_node",
        # One city of each shape: a hub of the busiest corridor, the two
        # single-homed attachment points, and a site-bearing city.
        ["Berlin", "Hamburg", "Dublin", "Athens", "Warsaw", "Paris", "HUB-EAST", "DC-NORTH"],
    )
    def test_single_node_failures_on_the_real_network(
        self, real_network: Network, failed_node: str
    ) -> None:
        _assert_agrees(real_network, failed_nodes=frozenset({failed_node}))

    @pytest.mark.parametrize(
        "failed_link",
        # L12 is Berlin to Hamburg, the most utilized link at baseline. L15 is
        # Berlin to Warsaw and L38 Stockholm to Warsaw, the two ways east. The
        # access links are the single-homed sites' only route in.
        ["L12", "L15", "L38", "ACC-HUB-EAST-Warsaw", "ACC-OPS-WEST-Dublin"],
    )
    def test_single_link_failures_on_the_real_network(
        self, real_network: Network, failed_link: str
    ) -> None:
        _assert_agrees(real_network, failed_links=frozenset({failed_link}))


# ---------------------------------------------------------------------------
# Leg 3
# ---------------------------------------------------------------------------


class TestAgreementWithNetworkx:
    def test_on_the_real_network(self, real_network: Network) -> None:
        _assert_path_sets_agree(real_network)

    @pytest.mark.parametrize("seed", RANDOM_SEEDS)
    def test_on_random_graphs(self, seed: int) -> None:
        _assert_path_sets_agree(_random_network(seed))

    @pytest.mark.parametrize("seed", RANDOM_SEEDS[:12])
    def test_on_random_graphs_with_a_failure(self, seed: int) -> None:
        network = _random_network(seed)
        failed_node = random.Random(seed + 2_000).choice(sorted(network.nodes))
        _assert_path_sets_agree(network, failed_nodes=frozenset({failed_node}))


# ---------------------------------------------------------------------------
# R6, the transit restriction
# ---------------------------------------------------------------------------

#: A graph where ignoring R6 gives a visibly different answer. S and T are
#: data centers with a demand between them. Through MID, also a data center,
#: they are two hops apart. The legal route through the two cities is three.
_R6_NODES: Mapping[str, tuple[NodeKind, float, float]] = {
    "S": (NodeKind.DATA_CENTER, 0.0, 0.0),
    "T": (NodeKind.DATA_CENTER, 4.0, 0.0),
    "MID": (NodeKind.DATA_CENTER, 2.0, 1.0),
    "CITY-A": (NodeKind.BACKBONE_CITY, 1.0, -1.0),
    "CITY-B": (NodeKind.BACKBONE_CITY, 3.0, -1.0),
}

_R6_LINKS: Mapping[str, tuple[str, str, float, LinkKind]] = {
    "SHORT-1": ("S", "MID", 100.0, LinkKind.ACCESS),
    "SHORT-2": ("MID", "T", 100.0, LinkKind.ACCESS),
    "LONG-1": ("S", "CITY-A", 100.0, LinkKind.ACCESS),
    "LONG-2": ("CITY-A", "CITY-B", 100.0, LinkKind.BACKBONE),
    "LONG-3": ("CITY-B", "T", 100.0, LinkKind.ACCESS),
}

_R6_DEMANDS: Sequence[tuple[str, str, str, float]] = (("D1", "S", "T", 12.0),)


class TestTransitRestriction:
    """R6: a data center or operations site may end a path, never continue one."""

    @pytest.fixture
    def network(self) -> Network:
        return _network(_R6_NODES, _R6_LINKS, _R6_DEMANDS)

    def test_the_longer_legal_route_is_taken(self, network: Network) -> None:
        result = route(network)
        assert result.undeliverable == ()
        # A router ignoring R6 would put all 12 units on the two-hop route
        # through MID and leave the three city links empty.
        assert dict(result.link_loads) == pytest.approx(
            {
                "SHORT-1": 0.0,
                "SHORT-2": 0.0,
                "LONG-1": 12.0,
                "LONG-2": 12.0,
                "LONG-3": 12.0,
            }
        )

    def test_the_reference_and_the_oracle_agree(self, network: Network) -> None:
        _assert_agrees(network)
        _assert_path_sets_agree(network)

    def test_with_no_legal_route_the_demand_is_undeliverable(self) -> None:
        """Dropping the city route leaves only the illegal one through MID."""
        only_illegal = {
            link_id: value for link_id, value in _R6_LINKS.items() if link_id.startswith("SHORT")
        }
        network = _network(_R6_NODES, only_illegal, _R6_DEMANDS)
        result = route(network)
        assert tuple(d.id for d in result.undeliverable) == ("D1",)
        assert set(result.link_loads.values()) == {0.0}

    def test_the_real_network_strands_the_east_behind_an_operations_site(
        self, real_network: Network
    ) -> None:
        """Failing Warsaw leaves HUB-EAST reachable only through OPS-EAST-2.

        ``data/sites.csv`` attaches OPS-EAST-2 to both HUB-EAST and Budapest,
        so the plain graph stays in one piece, but an operations site may not
        forward under R6 and OPS-EAST-1's two demands have nowhere to go.
        """
        result = _assert_agrees(real_network, failed_nodes=frozenset({"Warsaw"}))
        assert sorted(d.id for d in result.undeliverable) == [
            "SYN-DC-NORTH-OPS-EAST-1",
            "SYN-DC-SOUTH-OPS-EAST-1",
        ]
        assert connected_components(real_network, failed_nodes=frozenset({"Warsaw"})) == (
            frozenset(set(real_network.nodes) - {"Warsaw"}),
        )


# ---------------------------------------------------------------------------
# The two demand buckets, and the shape of the result
# ---------------------------------------------------------------------------


class TestDemandBuckets:
    def test_a_failed_endpoint_is_endpoint_affected_and_not_undeliverable(
        self, fixture_network: Network
    ) -> None:
        result = route(fixture_network, failed_nodes=frozenset({"DC-NORTH"}))
        assert tuple(d.id for d in result.endpoint_affected) == ("D1",)
        assert result.undeliverable == ()

    def test_a_demand_with_no_path_left_is_reported_not_dropped(
        self, fixture_network: Network
    ) -> None:
        """Cutting the hub's access link strands D1 with both endpoints alive."""
        result = route(fixture_network, failed_links=frozenset({"ACC-HUB-EAST-Warsaw"}))
        assert tuple(d.id for d in result.undeliverable) == ("D1",)
        assert result.endpoint_affected == ()
        # D2 is untouched, so the units it carries are still on the wire.
        assert result.link_loads["L2"] == pytest.approx(100.0)

    def test_the_buckets_account_for_every_demand_that_is_not_carried(
        self, real_network: Network
    ) -> None:
        result = route(real_network, failed_nodes=frozenset({"Dublin"}))
        carried = {d.id for d in real_network.demands}
        not_carried = {d.id for d in result.undeliverable} | {
            d.id for d in result.endpoint_affected
        }
        assert not_carried <= carried
        assert not {d.id for d in result.undeliverable} & {d.id for d in result.endpoint_affected}


class TestResultShape:
    def test_every_surviving_link_is_present_even_when_unused(
        self, fixture_network: Network
    ) -> None:
        loads = route(fixture_network).link_loads
        assert set(loads) == set(_FIXTURE_LINKS)
        assert loads["L1"] == 0.0  # Hamburg-Copenhagen carries nothing at baseline

    def test_a_failed_link_does_not_appear(self, fixture_network: Network) -> None:
        loads = route(fixture_network, failed_links=frozenset({"L1"})).link_loads
        assert "L1" not in loads
        assert set(loads) == set(_FIXTURE_LINKS) - {"L1"}

    def test_a_failed_node_takes_its_links_with_it(self, fixture_network: Network) -> None:
        """The scenario-berlin-down fixture lists exactly the links Berlin is not on."""
        loads = route(fixture_network, failed_nodes=frozenset({"Berlin"})).link_loads
        assert set(loads) == {
            link_id for link_id, (a, b, _, _) in _FIXTURE_LINKS.items() if "Berlin" not in {a, b}
        }

    def test_routing_is_deterministic(self, real_network: Network) -> None:
        first = route(real_network)
        second = route(real_network)
        assert dict(first.link_loads) == dict(second.link_loads)
        assert first.undeliverable == second.undeliverable
        assert first.endpoint_affected == second.endpoint_affected

    @pytest.mark.parametrize(
        ("failed_nodes", "failed_links", "expected"),
        [
            (frozenset({"Nowhere"}), frozenset(), "unknown node ids"),
            (frozenset(), frozenset({"L999"}), "unknown link ids"),
        ],
    )
    def test_an_unknown_id_raises(
        self,
        real_network: Network,
        failed_nodes: frozenset[str],
        failed_links: frozenset[str],
        expected: str,
    ) -> None:
        """A typo from the API layer is a bug, not something to route around."""
        with pytest.raises(ValueError, match=expected):
            route(real_network, failed_nodes=failed_nodes, failed_links=failed_links)
        with pytest.raises(ValueError, match=expected):
            connected_components(real_network, failed_nodes=failed_nodes, failed_links=failed_links)


# ---------------------------------------------------------------------------
# R7a, connectivity
# ---------------------------------------------------------------------------


class TestConnectedComponents:
    def test_the_healthy_real_network_is_one_piece(self, real_network: Network) -> None:
        """37 nodes in one component, from the verified facts in CLAUDE.md."""
        components = connected_components(real_network)
        assert len(components) == 1
        assert len(components[0]) == 37

    def test_failing_dublin_strands_its_single_homed_site(self, real_network: Network) -> None:
        """OPS-WEST attaches only to Dublin in data/sites.csv, so it is cut off."""
        components = connected_components(real_network, failed_nodes=frozenset({"Dublin"}))
        assert len(components) == 2
        assert frozenset({"OPS-WEST"}) in components
        assert sorted(len(component) for component in components) == [1, 35]

    def test_failing_an_access_link_strands_the_site_behind_it(self, real_network: Network) -> None:
        components = connected_components(
            real_network, failed_links=frozenset({"ACC-OPS-SOUTHEAST-Athens"})
        )
        assert len(components) == 2
        assert frozenset({"OPS-SOUTHEAST"}) in components

    def test_no_backbone_city_partitions_the_backbone(self, real_network: Network) -> None:
        """CLAUDE.md: the backbone has no articulation points.

        So the only components a city failure can produce are the sites that
        attach to it alone, never a split of the backbone itself.
        """
        cities = sorted(
            node.id for node in real_network.nodes.values() if node.kind is NodeKind.BACKBONE_CITY
        )
        for city in cities:
            components = connected_components(real_network, failed_nodes=frozenset({city}))
            largest = max(components, key=len)
            stranded = [c for c in components if c is not largest]
            assert all(len(c) == 1 for c in stranded), city

    def test_the_order_is_stable(self, real_network: Network) -> None:
        failed = frozenset({"Dublin", "Athens"})
        first = connected_components(real_network, failed_nodes=failed)
        second = connected_components(real_network, failed_nodes=failed)
        assert first == second
        assert [sorted(component) for component in first] == sorted(
            sorted(component) for component in first
        )

    def test_components_agree_with_networkx(self, real_network: Network) -> None:
        """The oracle again, on connectivity rather than on path sets."""
        for failed in (frozenset[str](), frozenset({"Dublin"}), frozenset({"Warsaw", "Budapest"})):
            graph = nx.Graph()
            graph.add_nodes_from(node_id for node_id in real_network.nodes if node_id not in failed)
            for link in real_network.links.values():
                if link.endpoints.a not in failed and link.endpoints.b not in failed:
                    graph.add_edge(link.endpoints.a, link.endpoints.b)
            oracle: set[frozenset[str]] = {
                frozenset(component) for component in nx.connected_components(graph)
            }
            assert set(connected_components(real_network, failed_nodes=failed)) == oracle


# ---------------------------------------------------------------------------
# End to end on the real data
# ---------------------------------------------------------------------------


class TestRealNetworkBaseline:
    """The strongest single check available: the verified facts in CLAUDE.md."""

    def test_nothing_is_undeliverable_and_nothing_is_overloaded(
        self, real_network: Network
    ) -> None:
        result = route(real_network)
        assert result.undeliverable == ()
        assert result.endpoint_affected == ()
        assert [
            link_id
            for link_id, load in result.link_loads.items()
            if load > real_network.links[link_id].capacity
        ] == []

    def test_the_peak_is_71_percent_on_berlin_to_hamburg(self, real_network: Network) -> None:
        """CLAUDE.md pins the baseline peak at 71.0% on Berlin to Hamburg.

        That link is L12. The load behind the figure is 390.546867167...
        of 550, which is 71.0085% and so 71.0% to one decimal place. The
        value is an equal split of demands whose path counts are not powers
        of ten, so it is not the round 390.5 units the task brief quoted;
        nothing here is rounded to make it fit.
        """
        result = route(real_network)
        peak_link_id = max(
            result.link_loads,
            key=lambda link_id: result.link_loads[link_id] / real_network.links[link_id].capacity,
        )
        assert peak_link_id == "L12"
        assert str(real_network.links["L12"].endpoints) == "Berlin--Hamburg"
        peak = result.link_loads["L12"] / real_network.links["L12"].capacity
        assert round(peak * 100, 1) == 71.0

    def test_all_the_units_are_carried_once_per_hop_of_their_paths(
        self, real_network: Network
    ) -> None:
        """A conservation check the reference implementation cannot give.

        Every demand is carried whole, so the total load over all links is the
        sum over demands of volume times hop count. Computed from the hop
        distances alone, which the loads never enter.
        """
        expected = 0.0
        for demand in real_network.demands:
            dag = shortest_path_dag(real_network, demand.endpoints.a)
            expected += demand.volume * dag.distance[demand.endpoints.b]
        result = route(real_network)
        assert sum(result.link_loads.values()) == pytest.approx(expected)


def _bfs_distances(neighbours: Mapping[str, Iterable[str]], source: str) -> dict[str, int]:
    """Plain hop distances, ignoring R6. Used only to check the oracle's reach."""
    distance = {source: 0}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        for neighbour in neighbours[node]:
            if neighbour not in distance:
                distance[neighbour] = distance[node] + 1
                queue.append(neighbour)
    return distance


class TestTransitRestrictionNeverShortensAPath:
    """R6 can only ever make a path longer, which is a cheap sanity check."""

    @pytest.mark.parametrize("seed", RANDOM_SEEDS)
    def test_on_random_graphs(self, seed: int) -> None:
        network = _random_network(seed)
        neighbours: dict[str, list[str]] = {node_id: [] for node_id in network.nodes}
        for link in network.links.values():
            neighbours[link.endpoints.a].append(link.endpoints.b)
            neighbours[link.endpoints.b].append(link.endpoints.a)
        for source in sorted(network.nodes):
            plain = _bfs_distances(neighbours, source)
            restricted = shortest_path_dag(network, source).distance
            for node, hops in restricted.items():
                assert hops >= plain[node]
