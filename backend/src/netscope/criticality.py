"""The full R7 sweep: every node and every link, assessed, not only the critical ones.

D12 and the R7b discussion in ``docs/DECISIONS.md`` settled what "critical"
means here. R7 names three reasons an element can be critical: it partitions
the surviving graph (R7a), it leaves a demand between two surviving nodes
undeliverable (R7b, read on the graph alone), or it overloads a surviving
link (R7c). The panel then confirmed the literal reading of R7b: a demand
lost only because its own endpoint failed also counts, which is why
``docs/api-contract.md`` reports a fourth reason, ``ENDPOINT_DEMANDS_LOST``,
kept apart from ``DEMANDS_UNDELIVERABLE`` so the genuine structural finding
is not buried under the 36 of 37 nodes that become "critical" simply by
originating traffic.

**This module owns none of the routing or connectivity logic.** Every number
below comes from one call to ``analysis.analyse`` per element, failing that
element's node or its link in turn. ``sweep`` only decides which reasons
fire from the already-computed ``ScenarioAnalysis`` and shapes the result.

**The reason enum lives here, not in ``api.schemas``.** The layering rule in
``CLAUDE.md`` forbids anything below ``api`` from importing it, and this
module sits in the domain. ``test_criticality.py`` asserts, from outside the
layering rule, that this enum and ``api.schemas.CriticalityReason`` carry
identical members and wire values, so the two definitions cannot drift apart
silently.

**No caching here.** P14, the API layer, owns the decision to compute the
sweep once at startup and serve it from memory. This module is called once
per request in tests and is cheap enough, a few hundred ``analyse`` calls
over a few dozen nodes and links, that it does not need to manage its own
cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from netscope.analysis import ScenarioAnalysis, analyse
from netscope.models import Network

__all__ = [
    "Assessment",
    "CriticalityReason",
    "CriticalitySweep",
    "CriticalitySweepSummary",
    "ElementKind",
    "FailureImpact",
    "sweep",
]


class CriticalityReason(StrEnum):
    """Why an element is critical. R7 gives three reasons; we report four.

    See the module docstring and ``docs/api-contract.md`` section 3b for why
    ``ENDPOINT_DEMANDS_LOST`` exists as its own reason rather than being
    folded into ``DEMANDS_UNDELIVERABLE``. The wire values match
    ``netscope.api.schemas.CriticalityReason`` exactly, which
    ``test_criticality.py`` asserts directly so the two cannot drift apart.
    """

    PARTITIONS_NETWORK = "partitions-network"
    DEMANDS_UNDELIVERABLE = "demands-undeliverable"
    ENDPOINT_DEMANDS_LOST = "endpoint-demands-lost"
    LINKS_OVERLOADED = "links-overloaded"


class ElementKind(StrEnum):
    """Whether an assessed element is a node or a link."""

    NODE = "node"
    LINK = "link"


#: Declaration order of ``CriticalityReason``, fixed once here so that every
#: assessment's reasons come out in the same order regardless of which fired
#: first during the sweep.
_REASON_ORDER: tuple[CriticalityReason, ...] = tuple(CriticalityReason)


@dataclass(frozen=True, slots=True)
class FailureImpact:
    """What measurably happens when one element is lost.

    Carried for every element, critical or not, so a caller can rank by
    impact without recomputing anything. Mirrors
    ``netscope.api.schemas.FailureImpact`` field for field; the API layer
    maps one to the other.
    """

    components: int
    undeliverable_demands: int
    undeliverable_units: float
    endpoint_affected_demands: int
    endpoint_affected_units: float
    overloaded_links: int
    max_utilization: float


@dataclass(frozen=True, slots=True)
class Assessment:
    """One element's verdict: whether it is critical, why, and its impact."""

    kind: ElementKind
    id: str
    reasons: tuple[CriticalityReason, ...]
    impact: FailureImpact

    @property
    def critical(self) -> bool:
        return bool(self.reasons)


@dataclass(frozen=True, slots=True)
class CriticalitySweepSummary:
    nodes_evaluated: int
    links_evaluated: int
    critical_nodes: int
    critical_links: int


@dataclass(frozen=True, slots=True)
class CriticalitySweep:
    assessments: tuple[Assessment, ...]
    summary: CriticalitySweepSummary


def sweep(network: Network) -> CriticalitySweep:
    """Assess every node and every link in ``network`` against R7.

    Runs one single-element failure scenario per node and per link, which is
    every scenario the plan's P12 acceptance check calls for: "all 92
    single-element scenarios" on the real 37-node, 55-link network.
    """
    assessments = [_assess_node(network, node_id) for node_id in network.nodes] + [
        _assess_link(network, link_id) for link_id in network.links
    ]
    assessments.sort(key=lambda assessment: (assessment.kind.value, assessment.id))

    nodes = [a for a in assessments if a.kind is ElementKind.NODE]
    links = [a for a in assessments if a.kind is ElementKind.LINK]
    return CriticalitySweep(
        assessments=tuple(assessments),
        summary=CriticalitySweepSummary(
            nodes_evaluated=len(nodes),
            links_evaluated=len(links),
            critical_nodes=sum(1 for a in nodes if a.critical),
            critical_links=sum(1 for a in links if a.critical),
        ),
    )


def _assess_node(network: Network, node_id: str) -> Assessment:
    result = analyse(network, failed_nodes=frozenset({node_id}))
    return _assessment(ElementKind.NODE, node_id, result)


def _assess_link(network: Network, link_id: str) -> Assessment:
    result = analyse(network, failed_links=frozenset({link_id}))
    return _assessment(ElementKind.LINK, link_id, result)


def _assessment(kind: ElementKind, element_id: str, result: ScenarioAnalysis) -> Assessment:
    reasons = _reasons(result)
    max_utilization = (
        max(entry.utilization for entry in result.link_utilizations)
        if result.link_utilizations
        else 0.0
    )
    impact = FailureImpact(
        components=result.components,
        undeliverable_demands=len(result.undeliverable),
        undeliverable_units=result.units_undeliverable,
        endpoint_affected_demands=len(result.endpoint_affected),
        endpoint_affected_units=result.units_endpoint_affected,
        overloaded_links=len(result.overloaded),
        max_utilization=max_utilization,
    )
    return Assessment(kind=kind, id=element_id, reasons=reasons, impact=impact)


def _reasons(result: ScenarioAnalysis) -> tuple[CriticalityReason, ...]:
    fired: set[CriticalityReason] = set()
    if result.partitioned:
        fired.add(CriticalityReason.PARTITIONS_NETWORK)
    if result.undeliverable:
        fired.add(CriticalityReason.DEMANDS_UNDELIVERABLE)
    if result.endpoint_affected:
        fired.add(CriticalityReason.ENDPOINT_DEMANDS_LOST)
    if result.overloaded:
        fired.add(CriticalityReason.LINKS_OVERLOADED)
    # Declaration order, not fire order, so output is stable regardless of
    # which checks ran first.
    return tuple(reason for reason in _REASON_ORDER if reason in fired)
