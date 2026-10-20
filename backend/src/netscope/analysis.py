"""Turn a failed set into the baseline and single-failure report R7, R8 and R10 need.

D4, D7 and D12 settled how a demand is routed and what counts as a partition;
this module adds nothing to that, it only shapes what ``routing.route`` and
``routing.connected_components`` already compute into the numbers the API
layer (P13, P14) will serialise.

**One function, not two.** ``docs/api-contract.md`` records the decision that
the baseline is the report for an empty failed set, so there is exactly one
entry point, ``analyse``, and no branch anywhere for "nothing has failed".
Calling it with both sets empty *is* the baseline.

**R7c is strict.** A link at exactly 100% utilization is full, not
overloaded. ``overloaded`` only ever holds links with ``utilization > 1.0``.

**Ranking is fixed, not invented here.** Highest utilization first, ties
broken on link id ascending. That order is pinned by the committed fixtures
(see ``contracts/fixtures/baseline.json``, where the two ``DC-NORTH`` access
links tie at 0.025 and ``ACC-DC-NORTH-Copenhagen`` takes rank 5 on its id).

**No dependency on ``api``.** This module returns domain objects
(``LinkUtilization`` and ``ScenarioAnalysis``), not the Pydantic wire models
in ``netscope.api.schemas``. Mapping one to the other is the API layer's job,
per the layering rule in ``CLAUDE.md``: ``analysis`` may import ``models``
but nothing may import ``api``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from netscope.models import Demand, Network
from netscope.routing import connected_components, route

__all__ = [
    "LinkUtilization",
    "ScenarioAnalysis",
    "analyse",
]

#: How many entries ``most_utilized`` carries, per R10. Fewer if the
#: surviving network has fewer links than this.
_MOST_UTILIZED_COUNT = 5


@dataclass(frozen=True, slots=True)
class LinkUtilization:
    """One surviving link's load against its capacity.

    ``utilization`` is a fraction, matching the wire convention: ``1.0`` is
    exactly full, and R7c's overload test is strictly greater than that.
    """

    link_id: str
    load: float
    capacity: float
    utilization: float


@dataclass(frozen=True, slots=True)
class ScenarioAnalysis:
    """Everything derived from one failed set.

    ``link_utilizations`` is sorted by link id, which is the stable order the
    full per-link map (R10's "shade the whole map") needs. ``most_utilized``
    and ``overloaded`` are ranked separately: highest utilization first, ties
    broken on link id ascending. The rank itself is not stored here, it is
    the tuple's own position, because a domain object has no reason to carry
    a wire concept; ``RankedLink.rank`` is assigned when the API layer maps
    this.

    The two demand buckets, ``undeliverable`` and ``endpoint_affected``, stay
    apart per R8. ``routing.route`` already guarantees no demand is in both,
    so nothing here has to re-check that.

    The four totals are what ``ScenarioTotals`` needs: how many demands there
    are in total, how many units that is, and how that total splits across
    delivered, undeliverable and endpoint-affected. Every demand is in
    exactly one of those three buckets, so the three unit figures sum to the
    total.
    """

    failed_nodes: frozenset[str]
    failed_links: frozenset[str]
    partitioned: bool
    components: int
    link_utilizations: tuple[LinkUtilization, ...]
    most_utilized: tuple[LinkUtilization, ...]
    overloaded: tuple[LinkUtilization, ...]
    undeliverable: tuple[Demand, ...]
    endpoint_affected: tuple[Demand, ...]
    demands_total: int
    units_total: float
    units_delivered: float
    units_undeliverable: float
    units_endpoint_affected: float


def analyse(
    network: Network,
    *,
    failed_nodes: frozenset[str] = frozenset(),
    failed_links: frozenset[str] = frozenset(),
) -> ScenarioAnalysis:
    """Route the network under this failed set and shape the result.

    An empty failed set is the baseline, per the contract decision this
    module exists to satisfy. There is no special case for it: routing an
    empty failure is routing, the same as any other.

    Raises:
        ValueError: If either failed set names an id the network does not
            have. ``routing.route`` already rejects this; it is not
            re-checked here, so the same message reaches the caller.
    """
    result = route(network, failed_nodes=failed_nodes, failed_links=failed_links)
    components = connected_components(network, failed_nodes=failed_nodes, failed_links=failed_links)

    utilizations = tuple(
        sorted(
            (
                LinkUtilization(
                    link_id=link_id,
                    load=load,
                    capacity=network.links[link_id].capacity,
                    utilization=load / network.links[link_id].capacity,
                )
                for link_id, load in result.link_loads.items()
            ),
            key=lambda entry: entry.link_id,
        )
    )
    # Highest utilization first, ties on link id ascending. Stated once here
    # and reused for both ranked views, so "most utilized" and "overloaded,
    # worst first" cannot disagree about tie-breaking.
    ranked = sorted(utilizations, key=lambda entry: (-entry.utilization, entry.link_id))

    # fsum rather than a running sum, for the same reason routing.py sums
    # per-link contributions that way: a list of floats summed once carries
    # less rounding error than accumulating with +=.
    undeliverable_units = math.fsum(demand.volume for demand in result.undeliverable)
    endpoint_affected_units = math.fsum(demand.volume for demand in result.endpoint_affected)
    units_total = network.total_demand

    return ScenarioAnalysis(
        failed_nodes=frozenset(failed_nodes),
        failed_links=frozenset(failed_links),
        partitioned=len(components) > 1,
        components=len(components),
        link_utilizations=utilizations,
        most_utilized=tuple(ranked[:_MOST_UTILIZED_COUNT]),
        overloaded=tuple(entry for entry in ranked if entry.utilization > 1.0),
        undeliverable=result.undeliverable,
        endpoint_affected=result.endpoint_affected,
        demands_total=len(network.demands),
        units_total=units_total,
        units_delivered=units_total - undeliverable_units - endpoint_affected_units,
        units_undeliverable=undeliverable_units,
        units_endpoint_affected=endpoint_affected_units,
    )
