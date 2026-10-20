"""Tests for the two P13 endpoints: ``/network`` and ``/analysis/baseline``.

Three things are checked against the real committed input files, not a
fixture, because the acceptance criterion in ``docs/IMPLEMENTATION_PLAN.md``
is explicitly "endpoint tests against the real data": the R1 totals, the
five most utilized links (verified by hand against the brief, see
``CLAUDE.md``'s "Verified facts" table), and that ``attaches_to`` is threaded
through for a real site.

A fourth app, built over a small hand-made network with no file on disk at
all, exercises the same endpoint shape at a size a test can read end to end.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from netscope.analysis import ScenarioAnalysis
from netscope.analysis import analyse as real_analyse
from netscope.api.app import create_app, main
from netscope.api.schemas import NetworkResponse, ScenarioReport
from netscope.api.state import build_state
from netscope.config import Settings
from netscope.errors import InputError
from netscope.models import Coordinates, Demand, Endpoints, Link, LinkKind, Network, Node, NodeKind

ROOT = Path(__file__).resolve().parents[2]
REAL_SETTINGS = Settings(
    sndlib_path=str(ROOT / "data" / "nobel-eu.xml"),
    sites_path=str(ROOT / "data" / "sites.csv"),
)

#: The five most utilized links at baseline, verified by hand against the
#: real input files and pinned in ``CLAUDE.md``'s "Verified facts" table and
#: the P13 task brief. ``endpoints`` is the sorted pair rather than a link id
#: spelling, because the id is an SNDlib implementation detail and the
#: endpoints are the fact a reviewer can check against the brief. Utilization
#: is rounded to one decimal place only for this comparison; the raw load is
#: asserted separately, unrounded, below.
EXPECTED_MOST_UTILIZED = [
    (1, ("Berlin", "Hamburg"), 71.0),
    (2, ("Amsterdam", "Hamburg"), 68.4),
    (3, ("Frankfurt", "Munich"), 62.1),
    (4, ("Milan", "Munich"), 58.8),
    (5, ("Berlin", "Munich"), 50.6),
]

#: The peak link's raw load, to the full float precision routing produces.
#: CLAUDE.md is explicit that the rounded 390.5 "has already caused one error
#: in this project", so this is asserted exactly rather than with
#: ``pytest.approx``.
PEAK_LINK_RAW_LOAD = 390.5468671679198
PEAK_LINK_CAPACITY = 550.0


@pytest.fixture(scope="module")
def real_client() -> Generator[TestClient, None, None]:
    """One app, built once for the whole module, over the real input files.

    Both endpoints are served from a cache built at startup (R1), so sharing
    one ``TestClient`` across every real-data test is not just an
    optimisation: a second module-scoped fixture rebuilding the same app
    would be redundant proof of the same cache, not a different test.
    """
    app = create_app(REAL_SETTINGS)
    with TestClient(app) as client:
        yield client


class TestNetworkEndpoint:
    def test_returns_200_and_validates_against_the_schema(self, real_client: TestClient) -> None:
        response = real_client.get("/api/v1/network")
        assert response.status_code == 200
        # model_validate raises on an unknown field or a type mismatch, so a
        # bare parse is itself the schema check (extra="forbid", per the
        # wire contract's conventions).
        NetworkResponse.model_validate(response.json())

    def test_r1_totals(self, real_client: TestClient) -> None:
        body = NetworkResponse.model_validate(real_client.get("/api/v1/network").json())
        assert (
            body.totals.nodes,
            body.totals.links,
            body.totals.demands,
            body.totals.demand_units,
        ) == (37, 55, 391, 2068.0)
        assert len(body.nodes) == 37
        assert len(body.links) == 55

    def test_dc_north_attaches_to_hamburg_and_copenhagen(self, real_client: TestClient) -> None:
        """data/sites.csv: ``DC-NORTH,data-center,Hamburg;Copenhagen,200``."""
        body = NetworkResponse.model_validate(real_client.get("/api/v1/network").json())
        by_id = {node.id: node for node in body.nodes}
        assert set(by_id["DC-NORTH"].attaches_to) == {"Hamburg", "Copenhagen"}

    def test_a_backbone_city_has_no_attaches_to(self, real_client: TestClient) -> None:
        body = NetworkResponse.model_validate(real_client.get("/api/v1/network").json())
        by_id = {node.id: node for node in body.nodes}
        assert by_id["Hamburg"].attaches_to == ()


class TestBaselineEndpoint:
    def test_returns_200_and_validates_against_the_schema(self, real_client: TestClient) -> None:
        response = real_client.get("/api/v1/analysis/baseline")
        assert response.status_code == 200
        ScenarioReport.model_validate(response.json())

    def test_no_undeliverable_demands_no_overload_one_component(
        self, real_client: TestClient
    ) -> None:
        body = ScenarioReport.model_validate(real_client.get("/api/v1/analysis/baseline").json())
        assert body.undeliverable_demands == ()
        assert body.endpoint_affected_demands == ()
        assert body.overloaded_links == ()
        assert not body.partitioned
        assert body.components == 1

    def test_the_five_most_utilized_links_ranked_one_to_five(self, real_client: TestClient) -> None:
        body = ScenarioReport.model_validate(real_client.get("/api/v1/analysis/baseline").json())
        assert [entry.rank for entry in body.most_utilized] == [1, 2, 3, 4, 5]
        network = NetworkResponse.model_validate(real_client.get("/api/v1/network").json())
        endpoints_by_id = {link.id: tuple(sorted(link.endpoints)) for link in network.links}
        for entry, (expected_rank, expected_endpoints, expected_percent) in zip(
            body.most_utilized, EXPECTED_MOST_UTILIZED, strict=True
        ):
            assert entry.rank == expected_rank
            assert endpoints_by_id[entry.link_id] == tuple(sorted(expected_endpoints))
            assert round(entry.utilization * 100, 1) == expected_percent

    def test_the_peak_links_raw_load_is_not_rounded(self, real_client: TestClient) -> None:
        """L12, Berlin to Hamburg: 390.5468671679198 of 550, not 390.5.

        A rounded 390.5 has already caused one error in this project
        (CLAUDE.md), so this is pinned to the full float rather than to a
        value a careless read of a percentage would reconstruct.
        """
        body = ScenarioReport.model_validate(real_client.get("/api/v1/analysis/baseline").json())
        peak = body.most_utilized[0]
        assert peak.load == PEAK_LINK_RAW_LOAD
        assert peak.capacity == PEAK_LINK_CAPACITY

    def test_baseline_is_identical_across_two_requests(self, real_client: TestClient) -> None:
        """Proves the response is cached, not recomputed, per R1's "once".

        If this were recomputed per request, it would still be numerically
        equal every time, since routing is deterministic; what distinguishes
        a cache from a correct-but-wasteful recomputation is not visible from
        one client's two requests. That distinction is instead covered by
        ``TestStartupRunsAnalysisOnce`` below, which counts how many times
        ``analysis.analyse`` actually runs.
        """
        first = real_client.get("/api/v1/analysis/baseline").json()
        second = real_client.get("/api/v1/analysis/baseline").json()
        assert first == second


class TestStartupRunsAnalysisOnce:
    """The cache is only worth having if startup truly analyses once.

    Patches ``netscope.api.state.analyse`` to count calls, which is the
    direct way to show "once at startup" rather than inferring it from two
    requests returning the same numbers (which a recompute would also do).
    """

    def test_analyse_runs_exactly_once_for_two_requests(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import netscope.api.state as state_module

        calls: list[int] = []

        def counting_analyse(
            network: Network,
            *,
            failed_nodes: frozenset[str] = frozenset(),
            failed_links: frozenset[str] = frozenset(),
        ) -> ScenarioAnalysis:
            calls.append(1)
            return real_analyse(network, failed_nodes=failed_nodes, failed_links=failed_links)

        # Referenced through the public module rather than through
        # ``state_module.analyse``, which mypy's strict re-export check
        # (``netscope.api.state`` does not list ``analyse`` in ``__all__``,
        # because it is an implementation detail of that module, not part of
        # its interface) would otherwise reject.
        monkeypatch.setattr(state_module, "analyse", counting_analyse)
        app = create_app(REAL_SETTINGS)
        with TestClient(app) as client:
            client.get("/api/v1/analysis/baseline")
            client.get("/api/v1/analysis/baseline")
        assert len(calls) == 1


class TestSmallHandBuiltNetwork:
    """The endpoint shape, exercised on a network small enough to read whole.

    Built directly from ``models.Node``/``Link``/``Demand``, with no file on
    disk, which is the fixture-scale exercise the P13 brief asks for "if your
    lifespan design allows it": ``create_app`` accepts an already-built
    ``AppState``, so this never touches ``build_network`` or either loader.

    Two backbone cities and one site. ``Small`` attaches to ``A`` only, so it
    is the one node with a non-empty ``attaches_to``, and the one demand
    between ``A`` and ``B`` has a single one-hop path and so carries all 10
    units on the one link, giving ``utilization = 10 / 100 = 0.1``.
    """

    @staticmethod
    def _tiny_network() -> Network:
        a = Node(id="A", kind=NodeKind.BACKBONE_CITY, coordinates=Coordinates(x=0.0, y=0.0))
        b = Node(id="B", kind=NodeKind.BACKBONE_CITY, coordinates=Coordinates(x=1.0, y=1.0))
        small = Node(
            id="Small", kind=NodeKind.OPERATIONS_SITE, coordinates=Coordinates(x=0.5, y=0.5)
        )
        link_ab = Link(
            id="L-A-B", endpoints=Endpoints("A", "B"), capacity=100.0, kind=LinkKind.BACKBONE
        )
        link_small = Link(
            id="ACC-Small-A", endpoints=Endpoints("Small", "A"), capacity=50.0, kind=LinkKind.ACCESS
        )
        demand = Demand(id="D1", endpoints=Endpoints("A", "B"), volume=10.0)
        return Network(
            nodes={"A": a, "B": b, "Small": small},
            links={"L-A-B": link_ab, "ACC-Small-A": link_small},
            demands=(demand,),
        )

    def test_network_and_baseline_shape_on_a_three_node_graph(self) -> None:
        state = build_state(
            REAL_SETTINGS, network=self._tiny_network(), attaches_to={"Small": ("A",)}
        )
        app = create_app(REAL_SETTINGS, state=state)
        with TestClient(app) as client:
            network = NetworkResponse.model_validate(client.get("/api/v1/network").json())
            baseline = ScenarioReport.model_validate(client.get("/api/v1/analysis/baseline").json())

        assert (network.totals.nodes, network.totals.links, network.totals.demands) == (3, 2, 1)
        by_id = {node.id: node for node in network.nodes}
        assert by_id["Small"].attaches_to == ("A",)
        assert by_id["A"].attaches_to == ()

        assert not baseline.partitioned
        assert baseline.components == 1
        loads = {entry.link_id: entry for entry in baseline.link_loads}
        assert loads["L-A-B"].load == 10.0
        assert loads["L-A-B"].utilization == pytest.approx(0.1)
        assert loads["ACC-Small-A"].load == 0.0


class TestMalformedInputAtStartup:
    """R2: a startup failure names the file and the row, not a traceback."""

    def test_build_state_raises_inputerror_naming_file_and_row(self, tmp_path: Path) -> None:
        bad_sites = tmp_path / "sites.csv"
        bad_sites.write_text(
            "site_id,site_type,attaches_to,access_capacity\n"
            "DC-NORTH,data-center,Hamburg;Copenhagen,not-a-number\n",
            encoding="utf-8",
        )
        bad_settings = Settings(
            sndlib_path=REAL_SETTINGS.sndlib_path,
            sites_path=str(bad_sites),
        )
        with pytest.raises(InputError) as excinfo:
            build_state(bad_settings)
        message = str(excinfo.value)
        assert str(bad_sites) in message
        assert "row 2" in message
        assert "access_capacity" in message

    def test_main_logs_one_line_and_exits_without_a_traceback(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Exercises ``app.main``'s own catch, not just ``build_state``.

        Points ``NETSCOPE_SITES_PATH`` at a file that does not exist, which
        is the simplest malformed input to construct without duplicating
        every validation rule the real loaders already cover in
        ``test_sites_loader.py`` and ``test_sndlib_loader.py``.
        """
        missing = tmp_path / "does-not-exist.csv"
        monkeypatch.setenv("NETSCOPE_SNDLIB_PATH", REAL_SETTINGS.sndlib_path)
        monkeypatch.setenv("NETSCOPE_SITES_PATH", str(missing))

        with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 1
        messages = [record.getMessage() for record in caplog.records]
        assert any(str(missing) in message for message in messages)
        assert not any("Traceback" in message for message in messages)
        for record in caplog.records:
            assert record.exc_info is None


def test_the_documented_backbone_capacity_setting_actually_reaches_the_merge(
    tmp_path: Path,
) -> None:
    """NETSCOPE_BACKBONE_CAPACITY was documented but inert until now.

    R3 fixes the backbone at 550 and that stays the default, so nothing about
    the shipped behaviour changes. The point of the test is the failure mode
    it prevents: a setting listed in .env.example that silently does nothing
    is worse than no setting, because a reader believes it works and a
    reviewer has no way to tell from the outside.
    """
    settings = Settings(
        sndlib_path=str(ROOT / "data" / "nobel-eu.xml"),
        sites_path=str(ROOT / "data" / "sites.csv"),
        backbone_capacity=800.0,
    )
    with TestClient(create_app(settings=settings)) as client:
        payload = client.get("/api/v1/network").json()

    backbone = [link for link in payload["links"] if link["kind"] == "backbone"]
    access = [link for link in payload["links"] if link["kind"] == "access"]
    assert len(backbone) == 41
    assert {link["capacity"] for link in backbone} == {800.0}
    # Access links take their capacity from the site row, so the setting must
    # not touch them. 200 for the data centers, 80 for the hub, 40 per site.
    assert {link["capacity"] for link in access} == {200.0, 80.0, 40.0}
