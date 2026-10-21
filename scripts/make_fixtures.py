"""Write the contract fixtures to contracts/fixtures/.

These unblock the front end lane, which builds its whole view against them
before any back end endpoint exists. They are also the first worked example
of the routing rule, so the numbers in them are derived by hand here and not
produced by the code they will later be used to check.

The fixture network is a seven-node cut-down of the real one, using the real
SNDlib coordinates for its four cities so the map looks right.

    OPS-EAST-1 --40-- HUB-EAST --80-- Warsaw
                                        |
                                       550
                                        |
    DC-NORTH --200-- Hamburg --550-- Berlin
         |              |              |
        200            550            550
         |              |              |
         +--------- Copenhagen --------+

Two demands:

    D1  OPS-EAST-1 to DC-NORTH    10 units
    D2  Hamburg    to Warsaw     100 units

Baseline routing, worked by hand under R5 and R6.

D2, Hamburg to Warsaw. Hamburg, Berlin, Warsaw is two hops. The route through
Copenhagen is three. So there is one minimum-hop path and it takes all 100
units: Hamburg-Berlin and Berlin-Warsaw each carry 100.

D1, OPS-EAST-1 to DC-NORTH. OPS-EAST-1 is an operations site and DC-NORTH is a
data center, so under R6 neither may forward, but both are endpoints here and
that is allowed. HUB-EAST is an aggregation hub and may forward. The route is
OPS-EAST-1, HUB-EAST, Warsaw, Berlin, then either Hamburg or Copenhagen, then
DC-NORTH. Both are five hops, so under R5 the 10 units split equally and each
path carries 5.

Adding the two demands gives these loads, which are the literals below:

    ACC-OPS-EAST-1-HUB-EAST     10   both D1 paths share this link
    ACC-HUB-EAST-Warsaw         10   likewise
    Berlin-Warsaw              110   100 from D2 plus 10 from D1
    Hamburg-Berlin             105   100 from D2 plus 5 from D1's Hamburg path
    Copenhagen-Berlin            5   D1's Copenhagen path only
    ACC-DC-NORTH-Hamburg         5
    ACC-DC-NORTH-Copenhagen      5
    Hamburg-Copenhagen           0   on no minimum-hop path

Failing Berlin, worked by hand. Berlin carries every path between the eastern
and western halves, so the survivors fall into two pieces: Hamburg,
Copenhagen and DC-NORTH on one side, Warsaw, HUB-EAST and OPS-EAST-1 on the
other. Both demands cross the break and neither has an endpoint at Berlin, so
both are undeliverable rather than endpoint-affected, and every surviving
link drops to zero.

Criticality, worked out independently.

The fifteen assessments in CRITICALITY below (seven nodes, eight links) were
produced by a separate brute-force implementation written before netscope had
any routing code at all, so it shares nothing with the module it will later be
used to check. That implementation enumerates every minimum-hop path and
divides, which is the naive reading of R5.

Its credential is the baseline above: run over this same network with nothing
failed, it reproduces all eight hand-derived link loads exactly, including the
105 over 550 that is the only value here that is not round. Eight of the
fifteen scenarios were then checked by hand against it, including every case
that partitions the network.

Two things the fixture network cannot show, stated so nobody mistakes their
absence for a result. No single failure here overloads any link, because the
backbone links are 550 and the largest demand is 100, so R7c never fires and
every max_utilization below is well under 1.0. R7c is exercised against the
real network instead, where the baseline peak is 71 percent and single
failures do push links over. And because links never remove nodes, no link
scenario has an endpoint-affected demand.

Run with: python scripts/make_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

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
from netscope.models import LinkKind, NodeKind

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "contracts" / "fixtures"

BACKBONE_CAPACITY = 550.0

# Real SNDlib coordinates, so the fixture plots where these cities actually are.
CITIES = {
    "Hamburg": Position(x=10.0, y=53.33),
    "Copenhagen": Position(x=12.32, y=55.41),
    "Berlin": Position(x=13.21, y=52.31),
    "Warsaw": Position(x=20.59, y=52.14),
}

# Site positions are the centroid of their attachments nudged clear of the
# city, which is the rule P8 will implement for real.
SITES = {
    "DC-NORTH": (
        NodeKind.DATA_CENTER,
        ("Hamburg", "Copenhagen"),
        Position(x=10.41, y=53.87),
    ),
    "HUB-EAST": (NodeKind.AGGREGATION_HUB, ("Warsaw",), Position(x=21.39, y=51.74)),
    "OPS-EAST-1": (NodeKind.OPERATIONS_SITE, ("HUB-EAST",), Position(x=22.19, y=51.34)),
}

LINKS = {
    "ACC-DC-NORTH-Copenhagen": (("Copenhagen", "DC-NORTH"), 200.0, LinkKind.ACCESS),
    "ACC-DC-NORTH-Hamburg": (("DC-NORTH", "Hamburg"), 200.0, LinkKind.ACCESS),
    "ACC-HUB-EAST-Warsaw": (("HUB-EAST", "Warsaw"), 80.0, LinkKind.ACCESS),
    "ACC-OPS-EAST-1-HUB-EAST": (("HUB-EAST", "OPS-EAST-1"), 40.0, LinkKind.ACCESS),
    "L1": (("Copenhagen", "Hamburg"), BACKBONE_CAPACITY, LinkKind.BACKBONE),
    "L2": (("Berlin", "Hamburg"), BACKBONE_CAPACITY, LinkKind.BACKBONE),
    "L3": (("Berlin", "Copenhagen"), BACKBONE_CAPACITY, LinkKind.BACKBONE),
    "L4": (("Berlin", "Warsaw"), BACKBONE_CAPACITY, LinkKind.BACKBONE),
}

DEMANDS = (
    StrandedDemand(id="D1", endpoints=("DC-NORTH", "OPS-EAST-1"), volume=10.0),
    StrandedDemand(id="D2", endpoints=("Hamburg", "Warsaw"), volume=100.0),
)

# Hand-derived in the module docstring. Do not regenerate these from the code
# under test: they exist to disagree with it when it is wrong.
BASELINE_LOADS = {
    "ACC-DC-NORTH-Copenhagen": 5.0,
    "ACC-DC-NORTH-Hamburg": 5.0,
    "ACC-HUB-EAST-Warsaw": 10.0,
    "ACC-OPS-EAST-1-HUB-EAST": 10.0,
    "L1": 0.0,
    "L2": 105.0,
    "L3": 5.0,
    "L4": 110.0,
}


def network() -> NetworkResponse:
    nodes = [
        NodeWire(
            id=city, kind=NodeKind.BACKBONE_CITY, position=position, can_transit=True
        )
        for city, position in CITIES.items()
    ]
    nodes += [
        NodeWire(
            id=site,
            kind=kind,
            position=position,
            can_transit=kind.can_transit,
            attaches_to=attaches_to,
        )
        for site, (kind, attaches_to, position) in SITES.items()
    ]
    links = [
        LinkWire(id=link_id, kind=kind, endpoints=endpoints, capacity=capacity)
        for link_id, (endpoints, capacity, kind) in LINKS.items()
    ]
    return NetworkResponse(
        nodes=tuple(sorted(nodes, key=lambda n: n.id)),
        links=tuple(sorted(links, key=lambda link: link.id)),
        totals=NetworkTotals(
            nodes=len(nodes),
            links=len(links),
            demands=len(DEMANDS),
            demand_units=sum(d.volume for d in DEMANDS),
        ),
    )


def _loads(loads: dict[str, float]) -> tuple[LinkLoad, ...]:
    return tuple(
        LinkLoad(
            link_id=link_id,
            load=load,
            capacity=LINKS[link_id][1],
            utilization=load / LINKS[link_id][1],
        )
        for link_id, load in sorted(loads.items())
    )


def _ranked(loads: tuple[LinkLoad, ...], limit: int | None) -> tuple[RankedLink, ...]:
    """Rank by utilization, breaking ties on link id so the order is stable."""
    ordered = sorted(loads, key=lambda entry: (-entry.utilization, entry.link_id))
    if limit is not None:
        ordered = ordered[:limit]
    return tuple(
        RankedLink(**entry.model_dump(), rank=rank)
        for rank, entry in enumerate(ordered, start=1)
    )


def baseline() -> ScenarioReport:
    loads = _loads(BASELINE_LOADS)
    units = sum(d.volume for d in DEMANDS)
    return ScenarioReport(
        failed=FailedSet(),
        partitioned=False,
        components=1,
        link_loads=loads,
        most_utilized=_ranked(loads, limit=5),
        overloaded_links=(),
        undeliverable_demands=(),
        endpoint_affected_demands=(),
        totals=ScenarioTotals(
            demands=len(DEMANDS),
            units=units,
            units_delivered=units,
            units_undeliverable=0.0,
            units_endpoint_affected=0.0,
        ),
    )


def berlin_down() -> ScenarioReport:
    """Berlin carries every east-west path, so losing it strands both demands."""
    surviving = {
        link_id: 0.0
        for link_id, (endpoints, _, _) in LINKS.items()
        if "Berlin" not in endpoints
    }
    loads = _loads(surviving)
    units = sum(d.volume for d in DEMANDS)
    return ScenarioReport(
        failed=FailedSet(nodes=("Berlin",)),
        partitioned=True,
        components=2,
        link_loads=loads,
        most_utilized=_ranked(loads, limit=5),
        overloaded_links=(),
        undeliverable_demands=DEMANDS,
        endpoint_affected_demands=(),
        totals=ScenarioTotals(
            demands=len(DEMANDS),
            units=units,
            units_delivered=0.0,
            units_undeliverable=units,
            units_endpoint_affected=0.0,
        ),
    )


#: Fifteen assessments, derived by the independent implementation described in
#: the module docstring and spot-checked by hand. Tuple order is:
#: reasons, components, undeliverable demands and units, endpoint-affected
#: demands and units, overloaded links, highest surviving utilization.
#:
#: Six of the seven nodes are critical and only Copenhagen is not, which is
#: the fixture-scale version of what R7b's literal reading does to the real
#: network. Three of the eight links are critical.
CRITICALITY: dict[
    tuple[str, str], tuple[tuple[str, ...], int, int, float, int, float, int, float]
] = {
    # Berlin carries every path between the two halves of this network.
    ("node", "Berlin"): (
        ("partitions-network", "demands-undeliverable"),
        2,
        2,
        110.0,
        0,
        0.0,
        0,
        0.0,
    ),
    # The only element of either kind that is not critical. Losing it leaves
    # both demands deliverable over their remaining minimum-hop paths.
    ("node", "Copenhagen"): ((), 1, 0, 0.0, 0, 0.0, 0, 0.25),
    # Critical only because it is an endpoint of D1, per R7b as written.
    ("node", "DC-NORTH"): (
        ("endpoint-demands-lost",),
        1,
        0,
        0.0,
        1,
        10.0,
        0,
        100.0 / 550.0,
    ),
    ("node", "HUB-EAST"): (
        ("partitions-network", "demands-undeliverable"),
        2,
        1,
        10.0,
        0,
        0.0,
        0,
        100.0 / 550.0,
    ),
    ("node", "Hamburg"): (("endpoint-demands-lost",), 1, 0, 0.0, 1, 100.0, 0, 0.25),
    ("node", "OPS-EAST-1"): (
        ("endpoint-demands-lost",),
        1,
        0,
        0.0,
        1,
        10.0,
        0,
        100.0 / 550.0,
    ),
    # The only element that fires three reasons at once: it partitions the
    # network, strands D1 between two survivors, and is itself an endpoint
    # of D2.
    ("node", "Warsaw"): (
        ("partitions-network", "demands-undeliverable", "endpoint-demands-lost"),
        2,
        1,
        10.0,
        1,
        100.0,
        0,
        0.0,
    ),
    # DC-NORTH is dual-homed, so losing either access link costs nothing.
    ("link", "ACC-DC-NORTH-Copenhagen"): ((), 1, 0, 0.0, 0, 0.0, 0, 0.25),
    ("link", "ACC-DC-NORTH-Hamburg"): ((), 1, 0, 0.0, 0, 0.0, 0, 0.25),
    # The two single-homed access links. Each one isolates a site.
    ("link", "ACC-HUB-EAST-Warsaw"): (
        ("partitions-network", "demands-undeliverable"),
        2,
        1,
        10.0,
        0,
        0.0,
        0,
        100.0 / 550.0,
    ),
    ("link", "ACC-OPS-EAST-1-HUB-EAST"): (
        ("partitions-network", "demands-undeliverable"),
        2,
        1,
        10.0,
        0,
        0.0,
        0,
        100.0 / 550.0,
    ),
    # The three backbone links in the western triangle all have an
    # alternative, so none is critical.
    ("link", "L1"): ((), 1, 0, 0.0, 0, 0.0, 0, 0.25),
    ("link", "L2"): ((), 1, 0, 0.0, 0, 0.0, 0, 0.25),
    ("link", "L3"): ((), 1, 0, 0.0, 0, 0.0, 0, 0.25),
    # The one backbone link with no alternative: it is the only path east.
    ("link", "L4"): (
        ("partitions-network", "demands-undeliverable"),
        2,
        2,
        110.0,
        0,
        0.0,
        0,
        0.0,
    ),
}


def criticality() -> CriticalityResponse:
    """Every node and every link, critical or not, per the contract."""
    assessments = []
    for (kind, element_id), row in CRITICALITY.items():
        reasons, components, und_n, und_u, ep_n, ep_u, over_n, max_util = row
        assessments.append(
            Assessment(
                kind=ElementKind(kind),
                id=element_id,
                critical=bool(reasons),
                reasons=tuple(CriticalityReason(r) for r in reasons),
                impact=FailureImpact(
                    components=components,
                    undeliverable_demands=und_n,
                    undeliverable_units=und_u,
                    endpoint_affected_demands=ep_n,
                    endpoint_affected_units=ep_u,
                    overloaded_links=over_n,
                    max_utilization=max_util,
                ),
            )
        )
    assessments.sort(key=lambda a: (a.kind.value, a.id))
    nodes = [a for a in assessments if a.kind is ElementKind.NODE]
    links = [a for a in assessments if a.kind is ElementKind.LINK]
    return CriticalityResponse(
        assessments=tuple(assessments),
        summary=CriticalitySummary(
            nodes_evaluated=len(nodes),
            links_evaluated=len(links),
            critical_nodes=sum(1 for a in nodes if a.critical),
            critical_links=sum(1 for a in links if a.critical),
        ),
    )


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    written: dict[str, BaseModel] = {
        "network.json": network(),
        "baseline.json": baseline(),
        "scenario-berlin-down.json": berlin_down(),
        "criticality.json": criticality(),
    }
    for name, model in written.items():
        payload = (
            json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        )
        (TARGET / name).write_text(payload, encoding="utf-8")
        print(f"wrote contracts/fixtures/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
