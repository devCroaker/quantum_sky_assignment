"""Tests for ``netscope.analysis``, which answers R7c, R8 and R10.

Four legs, each checking the module against a source that does not share its
mechanism with the code under test:

1. The real network's baseline, against the literals in ``CLAUDE.md``'s
   "verified facts" table and against a five-link ranking worked out by a
   separate implementation (see ``TestRealNetworkBaseline``).
2. The hand-worked seven-node fixture from ``scripts/make_fixtures.py``,
   checked against the committed ``contracts/fixtures/baseline.json`` and
   ``scenario-berlin-down.json`` payloads (see ``TestHandWorkedFixture``).
3. ``contracts/fixtures/criticality.json``, fifteen scenarios produced by a
   brute-force implementation written before this module existed (see
   ``TestCriticalityFixtureAsOracle``).
4. Structural facts about the real network: which elements partition it, and
   the Warsaw case where connectivity alone gives the wrong answer (see
   ``TestRealNetworkStructuralFacts``).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from netscope.analysis import LinkUtilization, ScenarioAnalysis, analyse
from netscope.api.schemas import CriticalityResponse, ElementKind, ScenarioReport
from netscope.loaders.merge import build_network
from netscope.loaders.sites_csv import load_sites
from netscope.loaders.sndlib_xml import load_backbone
from netscope.models import Coordinates, Demand, Endpoints, Link, LinkKind, Network, Node, NodeKind

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SNDLIB = DATA / "nobel-eu.xml"
SITES = DATA / "sites.csv"
FIXTURES = ROOT / "contracts" / "fixtures"


def _scenario_fixture(name: str) -> ScenarioReport:
    return ScenarioReport.model_validate(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def _criticality_fixture() -> CriticalityResponse:
    payload = json.loads((FIXTURES / "criticality.json").read_text(encoding="utf-8"))
    return CriticalityResponse.model_validate(payload)


# ---------------------------------------------------------------------------
# Networks under test
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_network() -> Network:
    return build_network(load_backbone(SNDLIB), load_sites(SITES), sites_file=str(SITES))


#: The seven-node cut-down documented in scripts/make_fixtures.py, restated
#: here from model objects rather than imported from the generator, so this
#: test does not share a mechanism with the code that produced the fixture
#: JSON. Positions are the real SNDlib ones, which routing never looks at.
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


# ---------------------------------------------------------------------------
# Leg 1: the real network's baseline
# ---------------------------------------------------------------------------


class TestRealNetworkBaseline:
    """Nothing failed. Figures reproduced from CLAUDE.md's verified facts table."""

    def test_nothing_is_undeliverable(self, real_network: Network) -> None:
        result = analyse(real_network)
        assert result.undeliverable == ()
        assert result.endpoint_affected == ()

    def test_no_link_is_above_100_percent(self, real_network: Network) -> None:
        result = analyse(real_network)
        assert result.overloaded == ()

    def test_peak_utilization_rounds_to_71_percent(self, real_network: Network) -> None:
        peak = analyse(real_network).most_utilized[0]
        assert round(peak.utilization * 100, 1) == 71.0

    def test_peak_link_is_l12_berlin_to_hamburg(self, real_network: Network) -> None:
        peak = analyse(real_network).most_utilized[0]
        assert peak.link_id == "L12"
        assert set(real_network.links["L12"].endpoints) == {"Berlin", "Hamburg"}

    def test_peak_load_is_the_exact_float_not_the_rounded_display_value(
        self, real_network: Network
    ) -> None:
        """390.5468671679198, not 390.5.

        CLAUDE.md calls out that rounding this to one decimal already caused
        one error in this project. The raw float and the rounded percentage
        are asserted as two separate facts so neither can stand in for the
        other.
        """
        peak = analyse(real_network).most_utilized[0]
        assert peak.load == 390.5468671679198
        assert peak.capacity == 550.0

    def test_five_most_utilized_links_match_an_independent_implementation(
        self, real_network: Network
    ) -> None:
        """Verified separately, before this module existed.

        The percentages below were worked out by a second implementation
        and are kept here only as a comment; the assertions use the ranked
        order and link identity, with a tolerance on the load.

             71.0%  Berlin     Hamburg     load 390.5   L12
             68.4%  Amsterdam  Hamburg     load 376.2   L3
             62.1%  Frankfurt  Munich      load 341.7   L26
             58.8%  Milan      Munich      load 323.5   L30
             50.6%  Berlin     Munich      load 278.5   L13
        """
        expected = [
            ("L12", {"Berlin", "Hamburg"}, 390.5, 71.0),
            ("L3", {"Amsterdam", "Hamburg"}, 376.2, 68.4),
            ("L26", {"Frankfurt", "Munich"}, 341.7, 62.1),
            ("L30", {"Milan", "Munich"}, 323.5, 58.8),
            ("L13", {"Berlin", "Munich"}, 278.5, 50.6),
        ]
        ranked = analyse(real_network).most_utilized
        assert len(ranked) == 5
        for entry, (link_id, endpoints, load, percent) in zip(ranked, expected, strict=True):
            assert entry.link_id == link_id
            assert set(real_network.links[link_id].endpoints) == endpoints
            assert entry.load == pytest.approx(load, abs=0.1)
            assert round(entry.utilization * 100, 1) == percent


# ---------------------------------------------------------------------------
# Leg 2: the hand-worked seven-node fixture, checked against the committed JSON
# ---------------------------------------------------------------------------


class TestHandWorkedFixture:
    """The network from scripts/make_fixtures.py, checked against its committed payloads.

    Both ``baseline.json`` and ``scenario-berlin-down.json`` were derived by
    hand in the generator's docstring, not produced by routing code, so
    agreeing with them is real evidence rather than self-agreement.
    """

    def test_baseline_link_loads_and_utilizations_match_the_fixture(
        self, fixture_network: Network
    ) -> None:
        expected = _scenario_fixture("baseline.json")
        actual = analyse(fixture_network)
        by_id = {entry.link_id: entry for entry in actual.link_utilizations}
        assert set(by_id) == {entry.link_id for entry in expected.link_loads}
        for entry in expected.link_loads:
            got = by_id[entry.link_id]
            assert got.load == pytest.approx(entry.load)
            assert got.capacity == entry.capacity
            assert got.utilization == pytest.approx(entry.utilization)

    def test_baseline_ranking_matches_the_fixture_including_the_tie(
        self, fixture_network: Network
    ) -> None:
        """Both DC-NORTH access links sit at 0.025. Copenhagen's id sorts first."""
        expected = _scenario_fixture("baseline.json").most_utilized
        actual = analyse(fixture_network).most_utilized
        assert [entry.link_id for entry in actual] == [entry.link_id for entry in expected]
        assert actual[4].link_id == "ACC-DC-NORTH-Copenhagen"
        assert actual[4].utilization == pytest.approx(0.025)

    def test_baseline_demand_buckets_and_totals_match_the_fixture(
        self, fixture_network: Network
    ) -> None:
        expected = _scenario_fixture("baseline.json").totals
        actual = analyse(fixture_network)
        assert actual.undeliverable == ()
        assert actual.endpoint_affected == ()
        assert actual.demands_total == expected.demands
        assert actual.units_total == pytest.approx(expected.units)
        assert actual.units_delivered == pytest.approx(expected.units_delivered)
        assert actual.units_undeliverable == pytest.approx(expected.units_undeliverable)
        assert actual.units_endpoint_affected == pytest.approx(expected.units_endpoint_affected)

    def test_berlin_down_partitions_strands_both_demands_and_zeros_every_link(
        self, fixture_network: Network
    ) -> None:
        expected = _scenario_fixture("scenario-berlin-down.json")
        actual = analyse(fixture_network, failed_nodes=frozenset({"Berlin"}))

        assert actual.partitioned is expected.partitioned
        assert actual.components == expected.components

        by_id = {entry.link_id: entry for entry in actual.link_utilizations}
        assert set(by_id) == {entry.link_id for entry in expected.link_loads}
        for entry in expected.link_loads:
            assert by_id[entry.link_id].load == pytest.approx(entry.load)

        assert {d.id for d in actual.undeliverable} == {
            d.id for d in expected.undeliverable_demands
        }
        assert actual.endpoint_affected == ()
        assert actual.units_undeliverable == pytest.approx(expected.totals.units_undeliverable)
        assert actual.units_delivered == pytest.approx(expected.totals.units_delivered)
        assert actual.units_endpoint_affected == pytest.approx(
            expected.totals.units_endpoint_affected
        )


# ---------------------------------------------------------------------------
# Leg 3: the criticality fixture as an oracle for all fifteen single failures
# ---------------------------------------------------------------------------


class TestCriticalityFixtureAsOracle:
    """Fifteen scenarios from a brute-force implementation written first.

    Each element of ``contracts/fixtures/criticality.json`` already carries
    the components, undeliverable and endpoint-affected counts and units,
    overloaded-link count and peak utilization that result from failing it.
    This is the strongest check in the suite: fifteen independent scenarios
    with externally derived expected values, none of them touched by this
    module or by ``routing.py``.
    """

    def test_all_fifteen_scenarios_match(self, fixture_network: Network) -> None:
        criticality = _criticality_fixture()
        assert len(criticality.assessments) == 15

        mismatches: list[str] = []
        for assessment in criticality.assessments:
            if assessment.kind is ElementKind.NODE:
                actual = analyse(fixture_network, failed_nodes=frozenset({assessment.id}))
            else:
                actual = analyse(fixture_network, failed_links=frozenset({assessment.id}))

            expected = assessment.impact
            max_utilization = (
                max(entry.utilization for entry in actual.link_utilizations)
                if actual.link_utilizations
                else 0.0
            )

            checks = (
                ("components", actual.components, expected.components),
                (
                    "undeliverable_demands",
                    len(actual.undeliverable),
                    expected.undeliverable_demands,
                ),
                ("undeliverable_units", actual.units_undeliverable, expected.undeliverable_units),
                (
                    "endpoint_affected_demands",
                    len(actual.endpoint_affected),
                    expected.endpoint_affected_demands,
                ),
                (
                    "endpoint_affected_units",
                    actual.units_endpoint_affected,
                    expected.endpoint_affected_units,
                ),
                ("overloaded_links", len(actual.overloaded), expected.overloaded_links),
                ("max_utilization", max_utilization, expected.max_utilization),
            )
            for field, got, want in checks:
                if got != pytest.approx(want):
                    mismatches.append(
                        f"{assessment.kind.value} {assessment.id}: {field} "
                        f"got {got!r} want {want!r}"
                    )

        assert not mismatches, "\n".join(mismatches)


# ---------------------------------------------------------------------------
# Leg 4: structural facts about the real network
# ---------------------------------------------------------------------------


class TestRealNetworkStructuralFacts:
    """Facts from CLAUDE.md's "verified facts" table, D12 and the R7b discussion."""

    def test_exactly_three_nodes_partition_the_network(self, real_network: Network) -> None:
        partitioning = {
            node_id
            for node_id in real_network.nodes
            if analyse(real_network, failed_nodes=frozenset({node_id})).partitioned
        }
        assert partitioning == {"Athens", "Dublin", "HUB-EAST"}

    def test_exactly_three_links_partition_the_network(self, real_network: Network) -> None:
        partitioning = {
            link_id
            for link_id in real_network.links
            if analyse(real_network, failed_links=frozenset({link_id})).partitioned
        }
        assert partitioning == {
            "ACC-OPS-SOUTHEAST-Athens",
            "ACC-OPS-WEST-Dublin",
            "ACC-OPS-EAST-1-HUB-EAST",
        }

    def test_losing_warsaw_leaves_one_component_but_strands_two_demands(
        self, real_network: Network
    ) -> None:
        """OPS-EAST-2 dual-homes HUB-EAST by accident, per D12.

        It attaches to both Warsaw and Budapest, so the graph stays in one
        piece of 36 nodes when Warsaw is lost. But OPS-EAST-2 is an
        operations site and may not forward traffic under R6, so the hub's
        own two demands still have no legal path. A connectivity check alone
        would call this network safer than it is, which is the point D12
        and the R7b discussion make.
        """
        result = analyse(real_network, failed_nodes=frozenset({"Warsaw"}))

        assert not result.partitioned
        assert result.components == 1

        assert {d.id for d in result.undeliverable} == {
            "SYN-DC-NORTH-OPS-EAST-1",
            "SYN-DC-SOUTH-OPS-EAST-1",
        }
        assert result.units_undeliverable == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Rules that are easiest to prove with a small constructed network
# ---------------------------------------------------------------------------


class TestOverloadIsStrictlyGreaterThan1:
    """R7c, and the contract's conventions section: 1.0 is exactly full.

    The real network's peak is 71%, and the fixture's largest demand of 100
    can never fill a 550-unit backbone link, so neither source can produce a
    link sitting at exactly 100%. A small constructed network is the only way
    to exercise this boundary.
    """

    def test_a_link_at_exactly_100_percent_is_not_overloaded(self) -> None:
        network = Network(
            nodes={
                "A": Node(id="A", kind=NodeKind.BACKBONE_CITY, coordinates=Coordinates(0, 0)),
                "B": Node(id="B", kind=NodeKind.BACKBONE_CITY, coordinates=Coordinates(1, 1)),
            },
            links={
                "L1": Link(
                    id="L1", endpoints=Endpoints("A", "B"), capacity=100.0, kind=LinkKind.BACKBONE
                )
            },
            demands=(Demand(id="D1", endpoints=Endpoints("A", "B"), volume=100.0),),
        )
        result = analyse(network)
        [only_link] = result.link_utilizations
        assert only_link.utilization == 1.0
        assert result.overloaded == ()
        assert result.most_utilized[0].utilization == 1.0


class TestRankingIsDeterministic:
    def test_repeated_calls_give_the_same_order(self, fixture_network: Network) -> None:
        first = analyse(fixture_network).most_utilized
        second = analyse(fixture_network).most_utilized
        assert [entry.link_id for entry in first] == [entry.link_id for entry in second]


class TestTotalsAddUp:
    """A scenario's three unit buckets must sum back to the total, every time."""

    @pytest.mark.parametrize(
        "failed_nodes,failed_links",
        [
            (frozenset(), frozenset()),
            (frozenset({"Berlin"}), frozenset()),
            (frozenset(), frozenset({"L4"})),
        ],
    )
    def test_fixture_network_totals(
        self,
        fixture_network: Network,
        failed_nodes: frozenset[str],
        failed_links: frozenset[str],
    ) -> None:
        result = analyse(fixture_network, failed_nodes=failed_nodes, failed_links=failed_links)
        assert (
            result.units_delivered + result.units_undeliverable + result.units_endpoint_affected
            == pytest.approx(result.units_total)
        )
        assert result.demands_total == len(fixture_network.demands)

    def test_real_network_baseline_totals(self, real_network: Network) -> None:
        result = analyse(real_network)
        assert result.units_total == pytest.approx(2068.0)  # R1's merged demand total
        assert (
            result.units_delivered + result.units_undeliverable + result.units_endpoint_affected
            == pytest.approx(result.units_total)
        )

    def test_real_network_warsaw_down_totals(self, real_network: Network) -> None:
        result = analyse(real_network, failed_nodes=frozenset({"Warsaw"}))
        assert (
            result.units_delivered + result.units_undeliverable + result.units_endpoint_affected
            == pytest.approx(result.units_total)
        )


class TestUnknownIdRaises:
    """routing.route already rejects an unknown id; analyse does not swallow it."""

    def test_an_unknown_failed_node_raises(self, fixture_network: Network) -> None:
        with pytest.raises(ValueError, match="unknown node"):
            analyse(fixture_network, failed_nodes=frozenset({"Nowhere"}))

    def test_an_unknown_failed_link_raises(self, fixture_network: Network) -> None:
        with pytest.raises(ValueError, match="unknown link"):
            analyse(fixture_network, failed_links=frozenset({"NOPE"}))


# Keep the dataclasses' public names exercised directly, so a signature
# change here is caught even if every other test only reads field values.
def test_public_names_are_importable() -> None:
    assert LinkUtilization is not None
    assert ScenarioAnalysis is not None
