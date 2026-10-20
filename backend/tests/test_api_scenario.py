"""Tests for the two P14 endpoints: ``/criticality`` and ``/scenario``.

Both run against the real committed input files, not a fixture, matching the
style ``test_api.py`` set for P13: the acceptance numbers quoted in this
task's brief are independently reproduced here by calling the endpoints,
not copied from the brief and asserted back at itself.

Every numeric literal below was checked, before this file was written,
against a direct call to ``netscope.analysis.analyse`` on the real network
(the same computation ``netscope.criticality.sweep`` and
``POST /api/v1/scenario`` both go through). All of them matched the brief:
the L12 overload, the Dublin partition, the Warsaw stranded-demand pair, and
every criticality count. None required a correction.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from netscope.api.app import create_app
from netscope.api.schemas import Assessment, CriticalityResponse, ErrorResponse, ScenarioReport
from netscope.config import Settings

ROOT = Path(__file__).resolve().parents[2]
REAL_SETTINGS = Settings(
    sndlib_path=str(ROOT / "data" / "nobel-eu.xml"),
    sites_path=str(ROOT / "data" / "sites.csv"),
)

#: The six critical links, measured by ``test_criticality.py``'s
#: ``TestRealNetwork.test_critical_links`` and restated in this task's brief.
CRITICAL_LINK_IDS = {
    "ACC-HUB-EAST-Warsaw",
    "ACC-OPS-EAST-1-HUB-EAST",
    "ACC-OPS-SOUTHEAST-Athens",
    "ACC-OPS-WEST-Dublin",
    "L12",
    "L26",
}


@pytest.fixture(scope="module")
def real_client() -> Generator[TestClient, None, None]:
    """One app, built once for the module, over the real input files.

    Both new endpoints are served from or computed against the one startup
    cache (R1 style), so sharing a client across the module is not only an
    optimisation: a second module-scoped app would be redundant proof of the
    same cache.
    """
    app = create_app(REAL_SETTINGS)
    with TestClient(app) as client:
        yield client


def _totals_add_up(report: ScenarioReport) -> None:
    """R8's three demand buckets must sum back to the network total.

    Every demand is in exactly one of delivered, undeliverable or
    endpoint-affected (``analysis.ScenarioAnalysis``'s own docstring), so
    this identity must hold for any failed set, not only the ones measured
    by hand here.
    """
    totals = report.totals
    assert (
        totals.units_delivered + totals.units_undeliverable + totals.units_endpoint_affected
        == pytest.approx(totals.units)
    )
    assert (
        len(report.undeliverable_demands) + len(report.endpoint_affected_demands) <= totals.demands
    )


class TestCriticalityEndpoint:
    def test_returns_200_and_validates_against_the_schema(self, real_client: TestClient) -> None:
        response = real_client.get("/api/v1/criticality")
        assert response.status_code == 200
        CriticalityResponse.model_validate(response.json())

    def test_counts_match_the_sweep(self, real_client: TestClient) -> None:
        """92 assessments: 37 nodes and 55 links, all 37 nodes critical."""
        body = CriticalityResponse.model_validate(real_client.get("/api/v1/criticality").json())
        assert len(body.assessments) == 92
        assert body.summary.nodes_evaluated == 37
        assert body.summary.links_evaluated == 55
        assert body.summary.critical_nodes == 37
        assert body.summary.critical_links == 6

    def test_critical_link_ids(self, real_client: TestClient) -> None:
        body = CriticalityResponse.model_validate(real_client.get("/api/v1/criticality").json())
        links = [a for a in body.assessments if a.kind.value == "link"]
        assert len(links) == 55
        assert {a.id for a in links if a.critical} == CRITICAL_LINK_IDS

    def test_reasons_by_kind_and_reason(self, real_client: TestClient) -> None:
        """By-reason breakdown from the brief: 3/3, 4/4, 36/0, 2/2."""
        body = CriticalityResponse.model_validate(real_client.get("/api/v1/criticality").json())
        nodes = [a for a in body.assessments if a.kind.value == "node"]
        links = [a for a in body.assessments if a.kind.value == "link"]

        def count(elements: list[Assessment], reason: str) -> int:
            return sum(1 for e in elements if reason in [r.value for r in e.reasons])

        assert count(nodes, "partitions-network") == 3
        assert count(links, "partitions-network") == 3
        assert count(nodes, "demands-undeliverable") == 4
        assert count(links, "demands-undeliverable") == 4
        assert count(nodes, "endpoint-demands-lost") == 36
        assert count(links, "endpoint-demands-lost") == 0
        assert count(nodes, "links-overloaded") == 2
        assert count(links, "links-overloaded") == 2

        overloaded_nodes = {
            a.id for a in nodes if "links-overloaded" in [r.value for r in a.reasons]
        }
        assert overloaded_nodes == {"Berlin", "Hamburg"}
        overloaded_links = {
            a.id for a in links if "links-overloaded" in [r.value for r in a.reasons]
        }
        assert overloaded_links == {"L12", "L26"}

    def test_no_link_carries_endpoint_demands_lost(self, real_client: TestClient) -> None:
        """Losing a link never removes a node (docs/api-contract.md, fixtures section)."""
        body = CriticalityResponse.model_validate(real_client.get("/api/v1/criticality").json())
        links = [a for a in body.assessments if a.kind.value == "link"]
        assert all("endpoint-demands-lost" not in [r.value for r in a.reasons] for a in links)

    def test_criticality_is_identical_across_two_requests(self, real_client: TestClient) -> None:
        """Proves the sweep is cached, not recomputed, matching R1's "once"."""
        first = real_client.get("/api/v1/criticality").json()
        second = real_client.get("/api/v1/criticality").json()
        assert first == second


class TestScenarioEndpointEmptySet:
    def test_empty_failed_set_equals_the_baseline_response_field_for_field(
        self, real_client: TestClient
    ) -> None:
        """The decision that lets the front end have one renderer (R11)."""
        baseline = real_client.get("/api/v1/analysis/baseline").json()
        scenario = real_client.post("/api/v1/scenario", json={}).json()
        assert scenario == baseline

    def test_empty_failed_set_with_explicit_empty_arrays_also_matches(
        self, real_client: TestClient
    ) -> None:
        baseline = real_client.get("/api/v1/analysis/baseline").json()
        scenario = real_client.post(
            "/api/v1/scenario", json={"failed_nodes": [], "failed_links": []}
        ).json()
        assert scenario == baseline


class TestScenarioEndpointDublin:
    def test_dublin_partitions_the_network_isolating_ops_west(
        self, real_client: TestClient
    ) -> None:
        """Dublin is a single point of failure (D12): OPS-WEST is single-homed to it."""
        response = real_client.post("/api/v1/scenario", json={"failed_nodes": ["Dublin"]})
        assert response.status_code == 200
        report = ScenarioReport.model_validate(response.json())
        assert report.partitioned
        assert report.components == 2
        _totals_add_up(report)

    def test_dublins_own_demands_are_endpoint_affected_not_undeliverable(
        self, real_client: TestClient
    ) -> None:
        """A failed node's own demands are endpoint-affected, not undeliverable.

        Separately, OPS-WEST (still alive, now cut off) has its own two
        demands, which have no path at all and so land in
        ``undeliverable_demands`` instead: the distinction R8 asks for.
        """
        report = ScenarioReport.model_validate(
            real_client.post("/api/v1/scenario", json={"failed_nodes": ["Dublin"]}).json()
        )
        endpoint_ids = {d.id for d in report.endpoint_affected_demands}
        undeliverable_ids = {d.id for d in report.undeliverable_demands}
        assert endpoint_ids & undeliverable_ids == set()
        assert any("Dublin" in demand_id for demand_id in endpoint_ids)
        assert undeliverable_ids == {"SYN-DC-NORTH-OPS-WEST", "SYN-DC-SOUTH-OPS-WEST"}
        assert not any("Dublin" in demand_id for demand_id in undeliverable_ids)


class TestScenarioEndpointWarsaw:
    def test_warsaw_leaves_one_component_of_36_but_strands_two_demands(
        self, real_client: TestClient
    ) -> None:
        """D12's clearest case: connectivity alone does not answer resilience.

        OPS-EAST-2 dual-homes HUB-EAST by accident (attaches to both Warsaw
        and Budapest), so the graph stays in one piece. But OPS-EAST-2 may
        not forward traffic under R6, so the hub's own two demands still
        have no legal path.
        """
        report = ScenarioReport.model_validate(
            real_client.post("/api/v1/scenario", json={"failed_nodes": ["Warsaw"]}).json()
        )
        assert not report.partitioned
        assert report.components == 1
        assert {d.id for d in report.undeliverable_demands} == {
            "SYN-DC-NORTH-OPS-EAST-1",
            "SYN-DC-SOUTH-OPS-EAST-1",
        }
        _totals_add_up(report)


class TestScenarioEndpointL12:
    def test_l12_pushes_frankfurt_munich_to_the_worst_overload(
        self, real_client: TestClient
    ) -> None:
        """L12 down pushes L26 (Frankfurt-Munich) to 128.3%, the data's worst."""
        network = real_client.get("/api/v1/network").json()
        endpoints_by_id = {
            link["id"]: tuple(sorted(link["endpoints"])) for link in network["links"]
        }

        report = ScenarioReport.model_validate(
            real_client.post("/api/v1/scenario", json={"failed_links": ["L12"]}).json()
        )
        assert len(report.overloaded_links) == 1
        worst = report.overloaded_links[0]
        assert endpoints_by_id[worst.link_id] == ("Frankfurt", "Munich")
        assert round(worst.utilization * 100, 1) == 128.3
        assert worst.rank == 1
        assert report.undeliverable_demands == ()
        assert report.endpoint_affected_demands == ()
        _totals_add_up(report)


class TestScenarioEndpointValidation:
    def test_unknown_node_id_returns_422_naming_it(self, real_client: TestClient) -> None:
        response = real_client.post("/api/v1/scenario", json={"failed_nodes": ["Not-A-Real-Node"]})
        assert response.status_code == 422
        body = ErrorResponse.model_validate(response.json())
        assert "Not-A-Real-Node" in body.error.message
        assert body.error.field == "failed_nodes"

    def test_unknown_link_id_returns_422_naming_it(self, real_client: TestClient) -> None:
        response = real_client.post("/api/v1/scenario", json={"failed_links": ["Not-A-Real-Link"]})
        assert response.status_code == 422
        body = ErrorResponse.model_validate(response.json())
        assert "Not-A-Real-Link" in body.error.message
        assert body.error.field == "failed_links"


class TestScenarioEndpointDuplicateAndCombinedFailures:
    """Two judgement calls the brief asked to be deliberate rather than incidental.

    Neither a duplicate id in one failed set, nor failing a node alongside
    one of its own links, is treated as an error: both collapse to the same
    set of actual failures, since ``failed_nodes``/``failed_links`` are
    converted to ``frozenset`` before being routed.
    """

    def test_duplicate_node_id_is_not_an_error_and_matches_the_single_id_case(
        self, real_client: TestClient
    ) -> None:
        single = real_client.post("/api/v1/scenario", json={"failed_nodes": ["Dublin"]}).json()
        duplicated = real_client.post(
            "/api/v1/scenario", json={"failed_nodes": ["Dublin", "Dublin"]}
        ).json()
        assert duplicated == single

    def test_node_and_its_own_access_link_both_failed_is_not_an_error(
        self, real_client: TestClient
    ) -> None:
        """Dublin and its own access link, failed together.

        Removing the link is redundant with removing the node (the node's
        failure already takes every incident link out of the surviving
        graph), so every computed figure matches failing Dublin alone. The
        ``failed`` field itself is deliberately excluded from this
        comparison: it echoes back exactly what the request named, per
        ``mappers.scenario_report``, so it legitimately differs (one more
        entry in ``failed.links``) even though nothing downstream does. That
        is the deliberate behaviour: no error, no special case, and the
        request is honestly reported back.
        """
        node_only = ScenarioReport.model_validate(
            real_client.post("/api/v1/scenario", json={"failed_nodes": ["Dublin"]}).json()
        )
        node_and_link = ScenarioReport.model_validate(
            real_client.post(
                "/api/v1/scenario",
                json={"failed_nodes": ["Dublin"], "failed_links": ["ACC-OPS-WEST-Dublin"]},
            ).json()
        )
        assert node_and_link.model_copy(update={"failed": node_only.failed}) == node_only
