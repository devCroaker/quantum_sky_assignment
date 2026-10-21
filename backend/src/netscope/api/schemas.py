"""The wire contract between the back end and the front end.

These models are the single source of truth for the interface. The
TypeScript types the front end uses are generated from the JSON Schema that
``scripts/export_contract.py`` writes out, so the two sides cannot drift
apart by hand.

Three shaping decisions are worth knowing before reading the models.

**Baseline and failure share one response type.** ``ScenarioReport`` describes
the network under a set of failures, and the baseline is simply the report for
an empty set. The front end therefore has one renderer for the map and one for
the panels, whether or not anything has failed, and "restore everything" needs
no special case.

**The failed set lives in the request, not on the server.** There is no
session. The front end owns the set and sends it, so every scenario is
reproducible by replaying one request body, and R11 works without a reload.

**Criticality reports every element, not only the critical ones.** All 92
nodes and links come back with their reasons and their measured impact. An
empty reason list means not critical. This answers the team's second question,
which links traffic depends on most, from the same payload that answers the
first, by sorting on impact rather than filtering on a flag.

Every model forbids unknown fields and is frozen, so a typo in a response is
an error rather than a silently dropped key.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from netscope.models import LinkKind, NodeKind

__all__ = [
    "Assessment",
    "CriticalityReason",
    "CriticalityResponse",
    "CriticalitySummary",
    "ElementKind",
    "ErrorDetail",
    "ErrorResponse",
    "FailedSet",
    "FailureImpact",
    "LinkLoad",
    "LinkWire",
    "NetworkResponse",
    "NetworkTotals",
    "NodeWire",
    "RankedLink",
    "ScenarioReport",
    "ScenarioRequest",
    "ScenarioTotals",
    "StrandedDemand",
]


class Wire(BaseModel):
    """Base for every wire model: immutable, and strict about unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Position(Wire):
    """A node's position on the map.

    SNDlib names these x and y. x is longitude and y is latitude, and the
    names are kept so the payload reads like the source data.
    """

    x: float = Field(description="Longitude in degrees")
    y: float = Field(description="Latitude in degrees")


class NodeWire(Wire):
    id: str
    kind: NodeKind
    position: Position
    can_transit: bool = Field(
        description="R6: whether this node may forward traffic for other nodes"
    )
    attaches_to: tuple[str, ...] = Field(
        default=(),
        description=(
            "For a site from sites.csv, the node ids it attaches to. Empty for a "
            "backbone city. Present so the view can show R9's 'near what it "
            "attaches to' relationship."
        ),
    )


class LinkWire(Wire):
    id: str
    kind: LinkKind
    endpoints: tuple[str, str] = Field(
        description="The two node ids, sorted. Links have no direction, per R3."
    )
    capacity: float


class NetworkTotals(Wire):
    """The R1 acceptance figures, served so the view can display them."""

    nodes: int
    links: int
    demands: int
    demand_units: float


class NetworkResponse(Wire):
    """GET /api/v1/network

    The topology and nothing derived from it. The 391 individual demands are
    deliberately not included: the view never lists them all, and the ones it
    does show arrive with full detail in a scenario report.
    """

    nodes: tuple[NodeWire, ...]
    links: tuple[LinkWire, ...]
    totals: NetworkTotals


class FailedSet(Wire):
    """Which elements are down. An empty set is the baseline."""

    nodes: tuple[str, ...] = ()
    links: tuple[str, ...] = ()


class ScenarioRequest(Wire):
    """POST /api/v1/scenario

    R7 and R8 only ask about a single failed element. This accepts a set
    because a set is a superset of that case, it costs nothing, and it lets
    the view model "fail these two and see" without a contract change.
    """

    failed_nodes: tuple[str, ...] = ()
    failed_links: tuple[str, ...] = ()


class LinkLoad(Wire):
    link_id: str
    load: float = Field(description="Demand units carried, summed over all demands")
    capacity: float
    utilization: float = Field(description="load divided by capacity. 1.0 is exactly full")


class RankedLink(LinkLoad):
    """A link load carrying its position in an ordered list.

    The rank is computed server side so that the view and any table or export
    agree on the order, including how ties were broken.
    """

    rank: int


class StrandedDemand(Wire):
    """A demand that cannot be delivered in this scenario."""

    id: str
    endpoints: tuple[str, str]
    volume: float


class ScenarioTotals(Wire):
    demands: int
    units: float
    units_delivered: float
    units_undeliverable: float
    units_endpoint_affected: float


class ScenarioReport(Wire):
    """The R8 answer: what breaks when these elements are down.

    Also the baseline response, with an empty ``failed`` set.
    """

    failed: FailedSet
    partitioned: bool = Field(
        description="R7a: whether the surviving graph is in more than one piece"
    )
    components: int = Field(description="Number of connected components among surviving nodes")
    link_loads: tuple[LinkLoad, ...] = Field(
        description="Every surviving link, so the view can shade the whole map"
    )
    most_utilized: tuple[RankedLink, ...] = Field(
        description="R10: the five most utilized links, ranked"
    )
    overloaded_links: tuple[RankedLink, ...] = Field(
        description="R8: every link above 100% utilization, worst first"
    )
    undeliverable_demands: tuple[StrandedDemand, ...] = Field(
        description="R8: demands with no remaining path, excluding the bucket below"
    )
    endpoint_affected_demands: tuple[StrandedDemand, ...] = Field(
        description=(
            "R8 requires these be reported separately: demands that start or end at "
            "a failed node, which are lost because their own endpoint is gone rather "
            "than because the network could not carry them."
        )
    )
    totals: ScenarioTotals


class CriticalityReason(StrEnum):
    """Why an element is critical: the three ways losing it hurts someone else.

    R7 gives three reasons and these are they. An element is critical when its
    loss partitions the network, strands a demand between two nodes that both
    survive, or drives a surviving link over capacity.

    What is deliberately **not** here is a demand lost because its own endpoint
    failed. That is reported, in ``FailureImpact.endpoint_affected_demands``
    and as its own bucket in ``ScenarioReport``, because R8 requires it to be
    reported separately. It just does not make an element critical.

    The project ran for a while with the opposite reading, under which a node
    was critical if losing it stranded any demand at all, including its own.
    That is the literal text of R7b, and it was tried. It marked 37 of the
    real network's 37 nodes critical, because 36 of them originate traffic and
    the thirty-seventh partitions the graph, so the flag could not be lower
    whatever the network looked like and said nothing about its shape. The
    panel reverted it. Criticality now means "losing this hurts somebody
    else", which is the question an operations team was actually asking.

    """

    PARTITIONS_NETWORK = "partitions-network"
    DEMANDS_UNDELIVERABLE = "demands-undeliverable"
    LINKS_OVERLOADED = "links-overloaded"


class ElementKind(StrEnum):
    NODE = "node"
    LINK = "link"


class FailureImpact(Wire):
    """What measurably happens when one element is lost.

    Reported for every element, critical or not, so that the view can rank
    links by how much traffic depends on them.
    """

    components: int
    undeliverable_demands: int
    undeliverable_units: float
    endpoint_affected_demands: int
    endpoint_affected_units: float
    overloaded_links: int
    max_utilization: float = Field(
        description="Highest utilization on any surviving link after this failure"
    )


class Assessment(Wire):
    kind: ElementKind
    id: str
    critical: bool = Field(description="True when at least one R7 reason applies")
    reasons: tuple[CriticalityReason, ...] = Field(
        default=(), description="Empty when the element is not critical"
    )
    impact: FailureImpact


class CriticalitySummary(Wire):
    nodes_evaluated: int
    links_evaluated: int
    critical_nodes: int
    critical_links: int


class CriticalityResponse(Wire):
    """GET /api/v1/criticality

    Every node and every link, each with its reasons and its impact. The
    critical ones are those with a non-empty reason list.
    """

    assessments: tuple[Assessment, ...]
    summary: CriticalitySummary


class ErrorDetail(Wire):
    """A rejected input or request, located the way R2 requires.

    The parts stay separate rather than being pre-formatted into a sentence,
    so the view can show the file and row as its own field and link to them.
    """

    message: str
    file: str | None = None
    row: int | None = None
    line: int | None = None
    field: str | None = None


class ErrorResponse(Wire):
    error: ErrorDetail
