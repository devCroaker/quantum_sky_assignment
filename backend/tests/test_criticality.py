"""Tests for ``netscope.criticality``, the full R7 sweep.

Three legs, each against a source that does not share a mechanism with the
code under test:

1. ``contracts/fixtures/criticality.json``, fifteen assessments from a
   brute-force implementation written before ``netscope`` had any routing
   code (see ``TestFixtureAsOracle``).
2. The real network, against the figures in this task's brief, each one
   measured by hand against this very sweep before the brief was written
   (see ``TestRealNetwork``).
3. Structural properties the sweep must hold regardless of the network:
   reason ordering, the critical flag matching a non-empty reason list,
   determinism, and the summary agreeing with the assessments (see
   ``TestSweepProperties``).

Also asserts that the domain ``CriticalityReason`` here and the wire
``netscope.api.schemas.CriticalityReason`` cannot drift apart, since the
domain module is forbidden by the layering rule from importing the wire one
and so has to redeclare it (see ``test_reason_enum_matches_the_wire_enum``,
which is allowed to import ``api`` because tests sit outside that rule).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from netscope.criticality import CriticalityReason, ElementKind, sweep
from netscope.loaders.merge import build_network
from netscope.loaders.sites_csv import load_sites
from netscope.loaders.sndlib_xml import load_backbone
from netscope.models import Coordinates, Demand, Endpoints, Link, LinkKind, Network, Node, NodeKind

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SNDLIB = DATA / "nobel-eu.xml"
SITES = DATA / "sites.csv"
FIXTURES = ROOT / "contracts" / "fixtures"


@pytest.fixture(scope="module")
def real_network() -> Network:
    return build_network(load_backbone(SNDLIB), load_sites(SITES), sites_file=str(SITES))


# ---------------------------------------------------------------------------
# The seven-node fixture network, restated from model objects rather than
# imported from scripts/make_fixtures.py, so this test does not share a
# mechanism with the code that produced the committed JSON it checks against.
# ---------------------------------------------------------------------------

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


@pytest.fixture(scope="module")
def fixture_network() -> Network:
    return Network(
        nodes={
            node_id: Node(id=node_id, kind=kind, coordinates=Coordinates(x=x, y=y))
            for node_id, (kind, x, y) in _FIXTURE_NODES.items()
        },
        links={
            link_id: Link(id=link_id, endpoints=Endpoints(a, b), capacity=capacity, kind=kind)
            for link_id, (a, b, capacity, kind) in _FIXTURE_LINKS.items()
        },
        demands=tuple(
            Demand(id=demand_id, endpoints=Endpoints(a, b), volume=volume)
            for demand_id, a, b, volume in _FIXTURE_DEMANDS
        ),
    )


def _fixture_assessments() -> list[dict[str, object]]:
    payload = json.loads((FIXTURES / "criticality.json").read_text(encoding="utf-8"))
    assessments: list[dict[str, object]] = payload["assessments"]
    return assessments


# ---------------------------------------------------------------------------
# Enum parity with the wire contract
# ---------------------------------------------------------------------------


def test_reason_enum_matches_the_wire_enum() -> None:
    """The domain enum here and api.schemas.CriticalityReason must never drift.

    criticality.py cannot import from api (layering rule in CLAUDE.md), so it
    redeclares the four reason codes. This test is the guard against the two
    copies disagreeing; it is allowed to import api because tests sit outside
    the layering rule.
    """
    from netscope.api.schemas import CriticalityReason as WireReason

    domain_members = {member.name: member.value for member in CriticalityReason}
    wire_members = {member.name: member.value for member in WireReason}
    assert domain_members == wire_members


# ---------------------------------------------------------------------------
# Leg 1: the criticality fixture as an oracle
# ---------------------------------------------------------------------------


class TestFixtureAsOracle:
    """All fifteen assessments from the brute-force implementation."""

    def test_all_fifteen_assessments_match(self, fixture_network: Network) -> None:
        expected = _fixture_assessments()
        assert len(expected) == 15

        result = sweep(fixture_network)
        actual_by_key = {(a.kind.value, a.id): a for a in result.assessments}
        assert set(actual_by_key) == {(e["kind"], e["id"]) for e in expected}

        mismatches: list[str] = []
        for entry in expected:
            key = (str(entry["kind"]), str(entry["id"]))
            actual = actual_by_key[key]
            expected_impact = entry["impact"]
            assert isinstance(expected_impact, dict)

            if actual.critical != entry["critical"]:
                mismatches.append(f"{key}: critical got {actual.critical} want {entry['critical']}")
            if [r.value for r in actual.reasons] != entry["reasons"]:
                mismatches.append(
                    f"{key}: reasons got {[r.value for r in actual.reasons]} "
                    f"want {entry['reasons']}"
                )

            impact_checks = (
                ("components", actual.impact.components),
                ("undeliverable_demands", actual.impact.undeliverable_demands),
                ("undeliverable_units", actual.impact.undeliverable_units),
                ("endpoint_affected_demands", actual.impact.endpoint_affected_demands),
                ("endpoint_affected_units", actual.impact.endpoint_affected_units),
                ("overloaded_links", actual.impact.overloaded_links),
                ("max_utilization", actual.impact.max_utilization),
            )
            for field, got in impact_checks:
                want = expected_impact[field]
                if got != pytest.approx(want):
                    mismatches.append(f"{key}: {field} got {got!r} want {want!r}")

        assert not mismatches, "\n".join(mismatches)

    def test_summary_matches_the_fixture(self, fixture_network: Network) -> None:
        payload = json.loads((FIXTURES / "criticality.json").read_text(encoding="utf-8"))
        expected_summary = payload["summary"]
        result = sweep(fixture_network)
        assert result.summary.nodes_evaluated == expected_summary["nodes_evaluated"]
        assert result.summary.links_evaluated == expected_summary["links_evaluated"]
        assert result.summary.critical_nodes == expected_summary["critical_nodes"]
        assert result.summary.critical_links == expected_summary["critical_links"]


# ---------------------------------------------------------------------------
# Leg 2: the real network, against figures measured directly from this sweep
# ---------------------------------------------------------------------------


class TestRealNetwork:
    """Figures measured directly by running this sweep against ``data/``."""

    def test_counts_evaluated(self, real_network: Network) -> None:
        result = sweep(real_network)
        assert result.summary.nodes_evaluated == 37
        assert result.summary.links_evaluated == 55

    def test_six_of_thirty_seven_nodes_are_critical(self, real_network: Network) -> None:
        """Only an element whose loss hurts somebody else is critical.

        Four nodes break something structurally: `Athens`, `Dublin` and
        `HUB-EAST` partition the network, and `Warsaw` strands two demands
        between nodes that both survive. Two more, `Berlin` and `Hamburg`,
        drive a surviving link over capacity. Six in total.

        This test replaced one asserting 37 of 37. The project briefly read
        R7b literally, so that a demand lost because its own endpoint failed
        counted too. Every node that originates traffic was then critical,
        which on this network is 36 of the 37, with `HUB-EAST` critical for
        partitioning instead. The count could not be lower whatever the
        network looked like, so it described the demand matrix rather than
        the network, and the panel reverted it (docs/DECISIONS.md D24).

        The endpoint-affected traffic is still reported, in `FailureImpact`
        and as its own bucket in a scenario report, because R8 requires that.
        It is simply not a reason for being critical. The test below pins
        that distinction on `Hamburg`, which is critical for overloading a
        link while also losing 100 units of its own traffic.
        """
        result = sweep(real_network)
        nodes = [a for a in result.assessments if a.kind is ElementKind.NODE]
        assert len(nodes) == 37
        assert result.summary.critical_nodes == 6
        assert {a.id for a in nodes if a.critical} == {
            "Athens",
            "Berlin",
            "Dublin",
            "HUB-EAST",
            "Hamburg",
            "Warsaw",
        }

    def test_losing_only_your_own_traffic_is_reported_but_is_not_a_reason(
        self, real_network: Network
    ) -> None:
        """The distinction the revert turned on, pinned on two real nodes.

        `Amsterdam` originates traffic and nothing else: losing it costs its
        own demands and breaks nothing for anyone still there, so it is not
        critical, and its endpoint-affected figures are still filled in.

        `Hamburg` loses its own traffic too, and is critical anyway, but only
        for overloading a surviving link. Its reasons must not mention the
        traffic it originates.
        """
        result = sweep(real_network)
        by_id = {a.id: a for a in result.assessments if a.kind is ElementKind.NODE}

        amsterdam = by_id["Amsterdam"]
        assert not amsterdam.critical
        assert amsterdam.reasons == ()
        assert amsterdam.impact.endpoint_affected_demands > 0
        assert amsterdam.impact.endpoint_affected_units > 0.0

        hamburg = by_id["Hamburg"]
        assert hamburg.critical
        assert hamburg.reasons == (CriticalityReason.LINKS_OVERLOADED,)
        assert hamburg.impact.endpoint_affected_units > 0.0

    def test_critical_links(self, real_network: Network) -> None:
        result = sweep(real_network)
        links = [a for a in result.assessments if a.kind is ElementKind.LINK]
        assert len(links) == 55
        assert result.summary.critical_links == 6
        critical_ids = {a.id for a in links if a.critical}
        assert critical_ids == {
            "ACC-HUB-EAST-Warsaw",
            "ACC-OPS-EAST-1-HUB-EAST",
            "ACC-OPS-SOUTHEAST-Athens",
            "ACC-OPS-WEST-Dublin",
            "L12",
            "L26",
        }

    def test_reasons_by_kind_and_reason_for_nodes(self, real_network: Network) -> None:
        result = sweep(real_network)
        nodes = [a for a in result.assessments if a.kind is ElementKind.NODE]

        def ids_with(reason: CriticalityReason) -> set[str]:
            return {a.id for a in nodes if reason in a.reasons}

        assert ids_with(CriticalityReason.PARTITIONS_NETWORK) == {"Athens", "Dublin", "HUB-EAST"}
        assert ids_with(CriticalityReason.DEMANDS_UNDELIVERABLE) == {
            "Athens",
            "Dublin",
            "HUB-EAST",
            "Warsaw",
        }
        assert ids_with(CriticalityReason.LINKS_OVERLOADED) == {"Berlin", "Hamburg"}

    def test_reasons_by_kind_and_reason_for_links(self, real_network: Network) -> None:
        result = sweep(real_network)
        links = [a for a in result.assessments if a.kind is ElementKind.LINK]

        def ids_with(reason: CriticalityReason) -> set[str]:
            return {a.id for a in links if reason in a.reasons}

        assert ids_with(CriticalityReason.PARTITIONS_NETWORK) == {
            "ACC-OPS-SOUTHEAST-Athens",
            "ACC-OPS-WEST-Dublin",
            "ACC-OPS-EAST-1-HUB-EAST",
        }
        assert ids_with(CriticalityReason.DEMANDS_UNDELIVERABLE) == {
            "ACC-OPS-SOUTHEAST-Athens",
            "ACC-OPS-WEST-Dublin",
            "ACC-OPS-EAST-1-HUB-EAST",
            "ACC-HUB-EAST-Warsaw",
        }
        assert ids_with(CriticalityReason.LINKS_OVERLOADED) == {"L12", "L26"}

    def test_no_link_ever_loses_a_demand_to_its_own_endpoint(self, real_network: Network) -> None:
        """Losing a link never removes a node, so no demand can lose an endpoint.

        Asserted across all 55 links, not spot-checked, because this is a
        structural guarantee of R8's definition of "endpoint-affected", not
        a coincidence of this particular network. It is checked on the impact
        figures rather than on the reasons, because losing your own traffic is
        no longer a reason for being critical.
        """
        result = sweep(real_network)
        links = [a for a in result.assessments if a.kind is ElementKind.LINK]
        assert len(links) == 55
        assert all(a.impact.endpoint_affected_demands == 0 for a in links)
        assert all(a.impact.endpoint_affected_units == 0.0 for a in links)

    def test_warsaw_strands_demands_without_partitioning(self, real_network: Network) -> None:
        """Warsaw is the D12 finding: it strands two demands but splits nothing.

        OPS-EAST-2 attaches to both HUB-EAST and Budapest, which accidentally
        dual-homes the aggregation hub, so the graph stays in one piece when
        Warsaw fails. But OPS-EAST-2 is an operations site and may not
        forward traffic under R6, so the hub's own demands still have no
        legal path. A connectivity check alone would call Warsaw safe; R7b
        does not.
        """
        result = sweep(real_network)
        warsaw = next(
            a for a in result.assessments if a.kind is ElementKind.NODE and a.id == "Warsaw"
        )
        assert CriticalityReason.DEMANDS_UNDELIVERABLE in warsaw.reasons
        assert CriticalityReason.PARTITIONS_NETWORK not in warsaw.reasons


# ---------------------------------------------------------------------------
# Leg 3: properties the sweep must hold regardless of which network it runs on
# ---------------------------------------------------------------------------


class TestSweepProperties:
    def test_critical_flag_matches_non_empty_reasons(self, real_network: Network) -> None:
        result = sweep(real_network)
        assert len(result.assessments) == 92
        for assessment in result.assessments:
            assert assessment.critical == bool(assessment.reasons)

    def test_reasons_appear_in_declaration_order(self, real_network: Network) -> None:
        declaration_order = list(CriticalityReason)
        result = sweep(real_network)
        for assessment in result.assessments:
            positions = [declaration_order.index(r) for r in assessment.reasons]
            assert positions == sorted(positions), assessment

    def test_sweep_is_deterministic(self, real_network: Network) -> None:
        first = sweep(real_network)
        second = sweep(real_network)
        assert first.assessments == second.assessments
        assert first.summary == second.summary

    def test_assessments_are_sorted_by_kind_then_id(self, real_network: Network) -> None:
        result = sweep(real_network)
        keys = [(a.kind.value, a.id) for a in result.assessments]
        assert keys == sorted(keys)

    def test_summary_counts_agree_with_the_assessments(self, real_network: Network) -> None:
        result = sweep(real_network)
        nodes = [a for a in result.assessments if a.kind is ElementKind.NODE]
        links = [a for a in result.assessments if a.kind is ElementKind.LINK]
        assert result.summary.nodes_evaluated == len(nodes)
        assert result.summary.links_evaluated == len(links)
        assert result.summary.critical_nodes == sum(1 for a in nodes if a.critical)
        assert result.summary.critical_links == sum(1 for a in links if a.critical)
