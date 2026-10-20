"""The wire contract, and the hand-worked numbers in its fixtures.

Two jobs. First, every committed fixture must validate against the schema it
claims to satisfy, so the front end can trust what it builds against.

Second, and more important, the baseline fixture's link loads are asserted
here against literals derived by hand in the docstring of
``scripts/make_fixtures.py``. The tests read the committed JSON rather than
importing the generator, so they are an outside check. When the routing
engine arrives in P9 it has to reproduce these same numbers, and a fixture
produced by the code under test could never catch that code being wrong.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

from netscope.api.schemas import (
    CriticalityReason,
    CriticalityResponse,
    ElementKind,
    ErrorResponse,
    NetworkResponse,
    ScenarioReport,
    ScenarioRequest,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "contracts" / "fixtures"

# Derived by hand in the docstring of scripts/make_fixtures.py. Kept at module
# level so the routing tests in P9 and P10 can import the same literals rather
# than restating them.
HAND_DERIVED_BASELINE_LOADS = {
    "ACC-OPS-EAST-1-HUB-EAST": 10.0,  # on both of D1's minimum-hop paths
    "ACC-HUB-EAST-Warsaw": 10.0,  # likewise
    "L4": 110.0,  # Berlin-Warsaw: 100 from D2 plus 10 from D1
    "L2": 105.0,  # Hamburg-Berlin: 100 from D2 plus D1's 5 via Hamburg
    "L3": 5.0,  # Copenhagen-Berlin: D1's Copenhagen path only
    "ACC-DC-NORTH-Hamburg": 5.0,
    "ACC-DC-NORTH-Copenhagen": 5.0,
    "L1": 0.0,  # Hamburg-Copenhagen is on no minimum-hop path
}


def load[ModelT: BaseModel](name: str, model: type[ModelT]) -> ModelT:
    return model.model_validate(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


class TestFixturesSatisfyTheSchema:
    def test_network_fixture_validates(self) -> None:
        network = load("network.json", NetworkResponse)
        assert network.totals.nodes == len(network.nodes) == 7
        assert network.totals.links == len(network.links) == 8

    def test_baseline_fixture_validates(self) -> None:
        baseline = load("baseline.json", ScenarioReport)
        assert baseline.failed.nodes == ()
        assert baseline.failed.links == ()

    def test_failure_fixture_validates(self) -> None:
        report = load("scenario-berlin-down.json", ScenarioReport)
        assert report.failed.nodes == ("Berlin",)

    def test_an_unknown_field_is_rejected(self) -> None:
        """extra="forbid" is what turns a response typo into an error."""
        payload = json.loads((FIXTURES / "network.json").read_text(encoding="utf-8"))
        payload["unexpected"] = 1
        with pytest.raises(ValueError, match="unexpected"):
            NetworkResponse.model_validate(payload)

    def test_models_are_frozen(self) -> None:
        network = load("network.json", NetworkResponse)
        with pytest.raises(ValueError, match="frozen"):
            network.nodes[0].id = "elsewhere"


class TestBaselineNumbersMatchTheHandCalculation:
    """Derived in the docstring of scripts/make_fixtures.py, not by the code.

    D2 runs Hamburg to Warsaw, 100 units, and has one minimum-hop path of two
    hops through Berlin. D1 runs OPS-EAST-1 to DC-NORTH, 10 units, and has two
    minimum-hop paths of five hops, one via Hamburg and one via Copenhagen, so
    each carries 5 units under R5.
    """

    def test_every_link_load_matches(self) -> None:
        baseline = load("baseline.json", ScenarioReport)
        actual = {entry.link_id: entry.load for entry in baseline.link_loads}
        assert actual == HAND_DERIVED_BASELINE_LOADS

    def test_the_two_demands_total_110_units_and_all_are_delivered(self) -> None:
        totals = load("baseline.json", ScenarioReport).totals
        assert (totals.demands, totals.units) == (2, 110.0)
        assert totals.units_delivered == 110.0
        assert totals.units_undeliverable == 0.0

    def test_utilization_is_a_fraction_of_capacity(self) -> None:
        """105 over 550 is the one value that is not a round number."""
        baseline = load("baseline.json", ScenarioReport)
        by_id = {entry.link_id: entry for entry in baseline.link_loads}
        assert by_id["L2"].utilization == pytest.approx(105.0 / 550.0)
        assert by_id["ACC-OPS-EAST-1-HUB-EAST"].utilization == 0.25

    def test_nothing_is_overloaded_at_baseline(self) -> None:
        baseline = load("baseline.json", ScenarioReport)
        assert baseline.overloaded_links == ()
        assert not baseline.partitioned
        assert baseline.components == 1


class TestRankingRule:
    """R10 needs five links, and the view must not disagree about which five."""

    def test_five_links_ranked_one_to_five_by_descending_utilization(self) -> None:
        ranked = load("baseline.json", ScenarioReport).most_utilized
        assert [entry.rank for entry in ranked] == [1, 2, 3, 4, 5]
        assert [entry.link_id for entry in ranked[:4]] == [
            "ACC-OPS-EAST-1-HUB-EAST",  # 10 of 40
            "L4",  # 110 of 550
            "L2",  # 105 of 550
            "ACC-HUB-EAST-Warsaw",  # 10 of 80
        ]

    def test_a_tie_breaks_on_link_id_ascending(self) -> None:
        """Both DC-NORTH access links sit at 5 of 200. Copenhagen sorts first.

        Without a stated rule this position would vary between runs, and the
        ranked list is exactly where that would be visible.
        """
        ranked = load("baseline.json", ScenarioReport).most_utilized
        assert ranked[4].link_id == "ACC-DC-NORTH-Copenhagen"
        assert ranked[4].utilization == 0.025


class TestFailureFixture:
    """Berlin carries every east-west path in the fixture network."""

    def test_losing_berlin_splits_the_network_in_two(self) -> None:
        report = load("scenario-berlin-down.json", ScenarioReport)
        assert report.partitioned
        assert report.components == 2

    def test_both_demands_are_undeliverable_and_neither_is_endpoint_affected(self) -> None:
        """R8 keeps these buckets apart. Berlin is an endpoint of neither demand."""
        report = load("scenario-berlin-down.json", ScenarioReport)
        assert {d.id for d in report.undeliverable_demands} == {"D1", "D2"}
        assert report.endpoint_affected_demands == ()
        assert report.totals.units_undeliverable == 110.0
        assert report.totals.units_delivered == 0.0

    def test_the_three_links_touching_berlin_are_gone_from_the_report(self) -> None:
        report = load("scenario-berlin-down.json", ScenarioReport)
        surviving = {entry.link_id for entry in report.link_loads}
        assert surviving.isdisjoint({"L2", "L3", "L4"})
        assert len(surviving) == 5


class TestContractDefaults:
    def test_an_empty_scenario_request_is_the_baseline(self) -> None:
        """R11's restore-everything is a request with nothing in it."""
        request = ScenarioRequest()
        assert request.failed_nodes == ()
        assert request.failed_links == ()

    def test_error_response_keeps_the_r2_location_parts_separate(self) -> None:
        parsed = ErrorResponse.model_validate(
            {
                "error": {
                    "message": "access_capacity must be a positive number, got '-5'",
                    "file": "sites.csv",
                    "row": 4,
                    "field": "access_capacity",
                }
            }
        )
        assert (parsed.error.file, parsed.error.row) == ("sites.csv", 4)
        assert parsed.error.line is None

    def test_the_four_reason_codes_are_the_only_ones(self) -> None:
        """R7 names three reasons. We report four, and the split is deliberate.

        The panel confirmed the literal reading of R7b, under which a demand
        lost because its own endpoint failed still counts. Keeping that as
        its own code is what lets a reader filter for the genuine single
        points of failure without recomputing anything, which matters
        because the literal reading marks 36 of the real network's 37 nodes
        critical.
        """
        assert [reason.value for reason in CriticalityReason] == [
            "partitions-network",
            "demands-undeliverable",
            "endpoint-demands-lost",
            "links-overloaded",
        ]


def test_committed_schema_is_up_to_date() -> None:
    """Guards against editing schemas.py and forgetting to regenerate."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_contract.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


class TestCriticalityFixture:
    """The fifteen assessments over the seven-node fixture network.

    These numbers come from a separate brute-force implementation written
    before netscope had any routing code, described in the docstring of
    scripts/make_fixtures.py. Its credential is that it reproduces the
    hand-derived baseline loads above exactly. P12 has to reproduce these in
    turn, which is the point of asserting them here.
    """

    def test_every_element_is_assessed(self) -> None:
        """R7 is answered for all 15 elements, not only the critical ones.

        That is what lets one payload answer both the "where are the single
        points of failure" question and the "which links does traffic depend
        on most" question, by filtering versus sorting.
        """
        report = load("criticality.json", CriticalityResponse)
        assert len(report.assessments) == 15
        assert report.summary.nodes_evaluated == 7
        assert report.summary.links_evaluated == 8
        kinds = [a.kind for a in report.assessments]
        assert kinds.count(ElementKind.NODE) == 7
        assert kinds.count(ElementKind.LINK) == 8

    def test_six_of_seven_nodes_are_critical_and_only_copenhagen_is_not(self) -> None:
        """The fixture-scale version of what R7b's literal reading costs.

        Copenhagen survives because both demands still have a minimum-hop
        path without it, and it is an endpoint of neither.
        """
        report = load("criticality.json", CriticalityResponse)
        assert report.summary.critical_nodes == 6
        safe = [a.id for a in report.assessments if a.kind is ElementKind.NODE and not a.critical]
        assert safe == ["Copenhagen"]

    def test_three_of_eight_links_are_critical(self) -> None:
        """The two single-homed access links, plus the only path east.

        Both DC-NORTH access links are safe because it is dual-homed, and the
        three links of the western triangle each have an alternative.
        """
        report = load("criticality.json", CriticalityResponse)
        assert report.summary.critical_links == 3
        critical = sorted(
            a.id for a in report.assessments if a.kind is ElementKind.LINK and a.critical
        )
        assert critical == ["ACC-HUB-EAST-Warsaw", "ACC-OPS-EAST-1-HUB-EAST", "L4"]

    def test_the_critical_flag_follows_the_reasons_list(self) -> None:
        report = load("criticality.json", CriticalityResponse)
        for assessment in report.assessments:
            assert assessment.critical == bool(assessment.reasons)

    def test_warsaw_is_the_only_element_firing_three_reasons(self) -> None:
        """It partitions the network, strands D1, and is an endpoint of D2.

        Worth pinning because it is the one case where all three mechanisms
        coincide, so a bug that conflates any two of them shows up here.
        """
        report = load("criticality.json", CriticalityResponse)
        by_id = {(a.kind, a.id): a for a in report.assessments}
        warsaw = by_id[(ElementKind.NODE, "Warsaw")]
        assert set(warsaw.reasons) == {
            CriticalityReason.PARTITIONS_NETWORK,
            CriticalityReason.DEMANDS_UNDELIVERABLE,
            CriticalityReason.ENDPOINT_DEMANDS_LOST,
        }
        assert warsaw.impact.components == 2
        assert (warsaw.impact.undeliverable_demands, warsaw.impact.undeliverable_units) == (1, 10.0)
        assert (
            warsaw.impact.endpoint_affected_demands,
            warsaw.impact.endpoint_affected_units,
        ) == (1, 100.0)

    def test_the_endpoint_only_cases_are_distinguishable(self) -> None:
        """Hamburg, DC-NORTH and OPS-EAST-1 are critical for one reason only.

        None of them partitions anything or strands a demand between two
        survivors. Under the stricter reading of R7b they would not be
        critical at all, and this test is what proves the payload still
        carries enough to tell the difference.
        """
        report = load("criticality.json", CriticalityResponse)
        endpoint_only = sorted(
            a.id
            for a in report.assessments
            if a.reasons == (CriticalityReason.ENDPOINT_DEMANDS_LOST,)
        )
        assert endpoint_only == ["DC-NORTH", "Hamburg", "OPS-EAST-1"]

    def test_no_fixture_scenario_overloads_a_link(self) -> None:
        """Stated so its absence is not mistaken for a result.

        The backbone links are 550 and the largest demand is 100, so R7c
        cannot fire on this network. It is exercised against the real
        network in P12, where the baseline peak is 71 percent.
        """
        report = load("criticality.json", CriticalityResponse)
        assert all(a.impact.overloaded_links == 0 for a in report.assessments)
        assert all(a.impact.max_utilization < 1.0 for a in report.assessments)
        assert not any(CriticalityReason.LINKS_OVERLOADED in a.reasons for a in report.assessments)

    def test_no_link_failure_has_an_endpoint_affected_demand(self) -> None:
        """Losing a link never removes a node, so the bucket must be empty."""
        report = load("criticality.json", CriticalityResponse)
        for assessment in report.assessments:
            if assessment.kind is ElementKind.LINK:
                assert assessment.impact.endpoint_affected_demands == 0
                assert assessment.impact.endpoint_affected_units == 0.0
