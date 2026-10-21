"""Convert domain objects to the wire models in ``api.schemas``.

Kept general rather than endpoint-specific, per the P13 brief, because P14's
``GET /api/v1/criticality`` and ``POST /api/v1/scenario`` reuse
:func:`scenario_report` and :func:`ranked_links` for ``ScenarioAnalysis``
values computed over a different failed set. Nothing here knows which
endpoint is calling it.

**Where ``rank`` comes from.** ``analysis.analyse`` already orders
``most_utilized`` and ``overloaded`` highest utilization first, ties broken
on link id ascending (see its docstring). The domain layer deliberately does
not store that position, because a rank is a wire concept and not a fact
about a link. :func:`ranked_links` assigns it here, from the tuple's own
order, so it is computed in exactly one place for every endpoint that needs
it.

**Where ``attaches_to`` comes from.** ``Network`` does not carry it: R9's
"near what it attaches to" relationship is a fact about ``sites.csv``, not
about the merged graph, so it would have no home on the domain ``Node``
without duplicating the site table into the model layer for one field only
the API needs. :func:`attaches_to_map` reads it off the parsed site rows
before they are discarded, and :func:`node_wire` looks a node up in that map,
which is empty for a backbone city because the map is only ever built from
site rows.
"""

from __future__ import annotations

from collections.abc import Mapping

from netscope import criticality
from netscope.analysis import LinkUtilization, ScenarioAnalysis
from netscope.api.schemas import (
    Assessment,
    CriticalityReason,
    CriticalityResponse,
    CriticalitySummary,
    ElementKind,
    FailedSet,
    FailureImpact,
    LinkLoad,
    LinkWire,
    NetworkResponse,
    NetworkTotals,
    NodeWire,
    Position,
    RankedLink,
    ScenarioReport,
    ScenarioTotals,
    StrandedDemand,
)
from netscope.loaders.sites_csv import ParsedSite
from netscope.models import Demand, Link, Network, Node

__all__ = [
    "attaches_to_map",
    "criticality_response",
    "link_load",
    "link_wire",
    "network_response",
    "node_wire",
    "ranked_links",
    "scenario_report",
    "stranded_demand",
]

#: Domain reason to wire reason, spelled out rather than coerced through a
#: shared string value, so a mismatch between the two enums (guarded against
#: directly in ``test_criticality.py``) fails here with a ``KeyError`` rather
#: than silently passing a value through.
_REASON_MAP: Mapping[criticality.CriticalityReason, CriticalityReason] = {
    criticality.CriticalityReason.PARTITIONS_NETWORK: CriticalityReason.PARTITIONS_NETWORK,
    criticality.CriticalityReason.DEMANDS_UNDELIVERABLE: CriticalityReason.DEMANDS_UNDELIVERABLE,
    criticality.CriticalityReason.ENDPOINT_DEMANDS_LOST: CriticalityReason.ENDPOINT_DEMANDS_LOST,
    criticality.CriticalityReason.LINKS_OVERLOADED: CriticalityReason.LINKS_OVERLOADED,
}

#: Domain element kind to wire element kind. Both enums exist for the same
#: layering reason the reasons do: ``netscope.criticality`` sits below
#: ``api`` and may not import it.
_KIND_MAP: Mapping[criticality.ElementKind, ElementKind] = {
    criticality.ElementKind.NODE: ElementKind.NODE,
    criticality.ElementKind.LINK: ElementKind.LINK,
}


def attaches_to_map(sites: tuple[ParsedSite, ...]) -> Mapping[str, tuple[str, ...]]:
    """Site id to its attachment targets, exactly as the CSV declared them.

    Built once, straight after ``load_sites``, because that is the only
    point in the application that still has ``ParsedSite`` values in hand.
    ``build_network`` consumes them into a plain ``Network`` and does not
    keep this relationship, by design (see this module's docstring).
    """
    return {site.site_id: site.attaches_to for site in sites}


def node_wire(node: Node, attaches_to: Mapping[str, tuple[str, ...]]) -> NodeWire:
    """One node's wire form.

    A backbone city has no entry in ``attaches_to``, so the lookup's default
    of ``()`` is what gives it an empty tuple, matching the NodeWire field's
    own documented meaning.
    """
    return NodeWire(
        id=node.id,
        kind=node.kind,
        position=Position(x=node.coordinates.x, y=node.coordinates.y),
        can_transit=node.can_transit,
        attaches_to=attaches_to.get(node.id, ()),
    )


def link_wire(link: Link) -> LinkWire:
    return LinkWire(
        id=link.id,
        kind=link.kind,
        endpoints=(link.endpoints.a, link.endpoints.b),
        capacity=link.capacity,
    )


def network_response(
    network: Network, attaches_to: Mapping[str, tuple[str, ...]]
) -> NetworkResponse:
    """``GET /api/v1/network``: the topology plus the R1 totals."""
    nodes = tuple(node_wire(node, attaches_to) for node in network.nodes.values())
    links = tuple(link_wire(link) for link in network.links.values())
    return NetworkResponse(
        nodes=nodes,
        links=links,
        totals=NetworkTotals(
            nodes=len(nodes),
            links=len(links),
            demands=len(network.demands),
            demand_units=network.total_demand,
        ),
    )


def link_load(entry: LinkUtilization) -> LinkLoad:
    return LinkLoad(
        link_id=entry.link_id,
        load=entry.load,
        capacity=entry.capacity,
        utilization=entry.utilization,
    )


def ranked_links(entries: tuple[LinkUtilization, ...]) -> tuple[RankedLink, ...]:
    """Attach a 1-based ``rank`` to an already-ordered tuple.

    ``entries`` must already be in the order the rank should read, which
    ``ScenarioAnalysis.most_utilized`` and ``.overloaded`` both are. Nothing
    here re-sorts, so a caller handing in the wrong order gets that order
    back with numbers stuck on it rather than a silently corrected one.
    """
    return tuple(
        RankedLink(
            link_id=entry.link_id,
            load=entry.load,
            capacity=entry.capacity,
            utilization=entry.utilization,
            rank=rank,
        )
        for rank, entry in enumerate(entries, start=1)
    )


def stranded_demand(demand: Demand) -> StrandedDemand:
    return StrandedDemand(
        id=demand.id,
        endpoints=(demand.endpoints.a, demand.endpoints.b),
        volume=demand.volume,
    )


def scenario_report(analysis: ScenarioAnalysis) -> ScenarioReport:
    """``ScenarioReport`` for one failed set, baseline or otherwise.

    The baseline is simply this, called with an ``analysis`` whose two failed
    sets are empty; there is no branch here for that case, matching
    ``analysis.analyse``'s own "one function, not two".
    """
    return ScenarioReport(
        failed=FailedSet(
            nodes=tuple(sorted(analysis.failed_nodes)),
            links=tuple(sorted(analysis.failed_links)),
        ),
        partitioned=analysis.partitioned,
        components=analysis.components,
        link_loads=tuple(link_load(entry) for entry in analysis.link_utilizations),
        most_utilized=ranked_links(analysis.most_utilized),
        overloaded_links=ranked_links(analysis.overloaded),
        undeliverable_demands=tuple(stranded_demand(d) for d in analysis.undeliverable),
        endpoint_affected_demands=tuple(stranded_demand(d) for d in analysis.endpoint_affected),
        totals=ScenarioTotals(
            demands=analysis.demands_total,
            units=analysis.units_total,
            units_delivered=analysis.units_delivered,
            units_undeliverable=analysis.units_undeliverable,
            units_endpoint_affected=analysis.units_endpoint_affected,
        ),
    )


def failure_impact(impact: criticality.FailureImpact) -> FailureImpact:
    return FailureImpact(
        components=impact.components,
        undeliverable_demands=impact.undeliverable_demands,
        undeliverable_units=impact.undeliverable_units,
        endpoint_affected_demands=impact.endpoint_affected_demands,
        endpoint_affected_units=impact.endpoint_affected_units,
        overloaded_links=impact.overloaded_links,
        max_utilization=impact.max_utilization,
    )


def assessment(entry: criticality.Assessment) -> Assessment:
    return Assessment(
        kind=_KIND_MAP[entry.kind],
        id=entry.id,
        critical=entry.critical,
        reasons=tuple(_REASON_MAP[reason] for reason in entry.reasons),
        impact=failure_impact(entry.impact),
    )


def criticality_response(sweep: criticality.CriticalitySweep) -> CriticalityResponse:
    """``GET /api/v1/criticality``: every assessment from one startup sweep."""
    return CriticalityResponse(
        assessments=tuple(assessment(entry) for entry in sweep.assessments),
        summary=CriticalitySummary(
            nodes_evaluated=sweep.summary.nodes_evaluated,
            links_evaluated=sweep.summary.links_evaluated,
            critical_nodes=sweep.summary.critical_nodes,
            critical_links=sweep.summary.critical_links,
        ),
    )
