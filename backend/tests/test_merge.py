"""Tests for the merge, which is where R1's headline figures are proved.

Two halves, the same shape as the two loader suites. The first builds the
network from the real committed files and pins every number the brief states
for the merged model, starting with the four headline literals: 37 nodes, 55
links, 391 demands and 2068.0 units. The second is a table of synthetic
rows, one per rule the merge adds on top of the two loaders, each asserting
that the rejection names the file and the row.

Where each expected number comes from is stated next to it. The four
headline figures and the backbone's 28 / 41 / 378 / 1898 come from the
"verified facts" table in ``CLAUDE.md``. The site split, 2 data centers, 6
operations sites and 1 aggregation hub, comes from ``data/sites.csv`` and is
already pinned by the P6 suite. Everything else is arithmetic on those,
shown in the comment that carries it.

The synthetic half uses hand-written ``ParsedBackbone`` and ``ParsedSite``
values rather than fixture files. Both loaders reject most of what would be
needed to provoke these rules from a file, so the only way to reach them is
to hand the merge the parsed values directly. Those values are built to be
minimal: two cities, and no more rows than the rule under test needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from netscope.errors import InputError
from netscope.loaders.merge import (
    BACKBONE_CAPACITY,
    DATA_CENTER_PAIR_UNITS,
    OPS_TO_DATA_CENTER_UNITS,
    build_network,
)
from netscope.loaders.sites_csv import ParsedSite, load_sites
from netscope.loaders.sndlib_xml import ParsedBackbone, ParsedLink, load_backbone
from netscope.models import (
    Coordinates,
    Demand,
    Endpoints,
    LinkKind,
    Network,
    Node,
    NodeKind,
)

DATA = Path(__file__).resolve().parents[2] / "data"
SNDLIB = DATA / "nobel-eu.xml"
SITES = DATA / "sites.csv"


@pytest.fixture(scope="module")
def network() -> Network:
    return build_network(
        load_backbone(SNDLIB),
        load_sites(SITES),
        sites_file=str(SITES),
    )


# --------------------------------------------------------------------------
# The real files: R1
# --------------------------------------------------------------------------


def test_the_real_files_merge_to_the_headline_figures(network: Network) -> None:
    """R1, written as the four literals the brief gives and nothing else.

    37 / 55 / 391 / 2068.0 is the acceptance check for this task. They are
    deliberately literals rather than expressions: an expression built from
    the same pieces the code uses would agree with the code even when both
    are wrong.
    """
    assert len(network.nodes) == 37
    assert len(network.links) == 55
    assert len(network.demands) == 391
    assert network.total_demand == 2068.0


def test_nodes_split_into_28_cities_and_9_sites(network: Network) -> None:
    """28 cities from the brief's verified facts, 9 rows from sites.csv.

    Also the split within the nine, which is what R4 and R6 both key off:
    two data centers, six operations sites, one aggregation hub.
    """
    kinds = [node.kind for node in network.nodes.values()]
    assert kinds.count(NodeKind.BACKBONE_CITY) == 28
    assert kinds.count(NodeKind.DATA_CENTER) == 2
    assert kinds.count(NodeKind.OPERATIONS_SITE) == 6
    assert kinds.count(NodeKind.AGGREGATION_HUB) == 1
    # 28 + 2 + 6 + 1 = 37, the headline node count.
    assert len(kinds) == 28 + 2 + 6 + 1


def test_links_split_into_41_backbone_and_14_access(network: Network) -> None:
    """41 backbone links from the brief. 14 is the attachment count.

    sites.csv carries 14 values across its nine ``attaches_to`` cells and
    each one becomes exactly one access link, which the P6 suite pins
    independently. 41 + 14 = 55, the headline link count.
    """
    kinds = [link.kind for link in network.links.values()]
    assert kinds.count(LinkKind.BACKBONE) == 41
    assert kinds.count(LinkKind.ACCESS) == 14


def test_every_backbone_link_carries_exactly_550(network: Network) -> None:
    """R3. The flat value applies to all 41, with no exception.

    The SNDlib capacity modules cannot interfere here even in principle:
    ``ParsedLink`` has no capacity field, so the only number available to
    apply is this constant.
    """
    backbone = [link for link in network.links.values() if link.kind is LinkKind.BACKBONE]
    assert len(backbone) == 41
    assert {link.capacity for link in backbone} == {550.0}
    assert BACKBONE_CAPACITY == 550.0


def test_access_capacities_come_from_the_row(network: Network) -> None:
    """Quoted from data/sites.csv: 200 for both data centers, 80 for the
    hub, 40 for each of the six operations sites.

    Checked per link, because the capacity belongs to the row and a
    multi-homed site's links must all carry the same value: DC-NORTH has two
    links and both are 200. The one link with a site at each end,
    ACC-OPS-EAST-1-HUB-EAST, takes the capacity of the row that declared it,
    which is OPS-EAST-1's 40 rather than HUB-EAST's 80.
    """
    expected_by_site = {
        "DC-NORTH": 200.0,
        "DC-SOUTH": 200.0,
        "HUB-EAST": 80.0,
        "OPS-WEST": 40.0,
        "OPS-CENTRAL": 40.0,
        "OPS-SOUTHEAST": 40.0,
        "OPS-EAST-1": 40.0,
        "OPS-EAST-2": 40.0,
        "OPS-IBERIA": 40.0,
    }
    seen = 0
    for site in load_sites(SITES):
        for target in site.attaches_to:
            link = network.links[f"ACC-{site.site_id}-{target}"]
            assert link.kind is LinkKind.ACCESS, link.id
            assert link.capacity == expected_by_site[site.site_id], link.id
            seen += 1
    # The 14 attachment values in the file, every one of them accounted for.
    assert seen == 14


def test_the_one_access_link_between_two_sites(network: Network) -> None:
    """ACC-OPS-EAST-1-HUB-EAST, the only access link with no city on it.

    OPS-EAST-1 attaches to HUB-EAST rather than to a city, so this link is
    the evidence that the id format and the capacity both come from the
    declaring row. The id spelling is fixed by the committed contract
    fixtures under contracts/fixtures/, which already name it.
    """
    link = network.links["ACC-OPS-EAST-1-HUB-EAST"]
    assert link.kind is LinkKind.ACCESS
    assert link.capacity == 40.0
    assert link.endpoints == Endpoints("HUB-EAST", "OPS-EAST-1")


def test_access_link_ids_follow_the_contract_spelling(network: Network) -> None:
    """ACC-<site_id>-<attachment target>, as the committed fixtures use it."""
    access = {link.id for link in network.links.values() if link.kind is LinkKind.ACCESS}
    assert "ACC-DC-NORTH-Hamburg" in access
    assert "ACC-DC-NORTH-Copenhagen" in access
    assert "ACC-HUB-EAST-Warsaw" in access
    assert all(link_id.startswith("ACC-") for link_id in access)


# --------------------------------------------------------------------------
# The real files: R4
# --------------------------------------------------------------------------


def test_demands_split_into_378_from_file_a_and_13_synthetic(network: Network) -> None:
    """378 demands carrying 1898.0, plus 13 carrying 170.0, is 391 and 2068.0.

    The 13 are R4's: six operations sites times two data centers is 12 at 10
    units each, which is 120, plus the one data center pair at 50, so 170.
    1898.0 + 170.0 = 2068.0, the headline total.
    """
    synthetic = [demand for demand in network.demands if demand.id.startswith("SYN-")]
    from_file_a = [demand for demand in network.demands if not demand.id.startswith("SYN-")]

    assert len(from_file_a) == 378
    assert sum(demand.volume for demand in from_file_a) == 1898.0
    assert len(synthetic) == 13
    assert sum(demand.volume for demand in synthetic) == 170.0
    assert 1898.0 + 170.0 == 2068.0


def test_exactly_thirteen_demand_ids_are_synthetic(network: Network) -> None:
    """The SYN- prefix is the only marker, so it has to be exact.

    File A's ids are two city names run together, such as AmsterdamAthens,
    so none of them can collide with the prefix. All 391 ids are unique.
    """
    ids = [demand.id for demand in network.demands]
    assert sum(1 for demand_id in ids if demand_id.startswith("SYN-")) == 13
    assert len(set(ids)) == 391


def test_the_synthetic_demands_are_exactly_the_r4_set(network: Network) -> None:
    """Every id and volume R4 asks for, written out.

    Twelve operations-to-data-center demands at 10 units, one data center
    pair at 50. The ids are SYN-<a>-<b> with the endpoints sorted, which is
    why every one of them reads DC- before OPS-.
    """
    synthetic = {
        demand.id: demand.volume for demand in network.demands if demand.id.startswith("SYN-")
    }
    assert synthetic == {
        "SYN-DC-NORTH-OPS-WEST": 10.0,
        "SYN-DC-NORTH-OPS-CENTRAL": 10.0,
        "SYN-DC-NORTH-OPS-SOUTHEAST": 10.0,
        "SYN-DC-NORTH-OPS-EAST-1": 10.0,
        "SYN-DC-NORTH-OPS-EAST-2": 10.0,
        "SYN-DC-NORTH-OPS-IBERIA": 10.0,
        "SYN-DC-SOUTH-OPS-WEST": 10.0,
        "SYN-DC-SOUTH-OPS-CENTRAL": 10.0,
        "SYN-DC-SOUTH-OPS-SOUTHEAST": 10.0,
        "SYN-DC-SOUTH-OPS-EAST-1": 10.0,
        "SYN-DC-SOUTH-OPS-EAST-2": 10.0,
        "SYN-DC-SOUTH-OPS-IBERIA": 10.0,
        "SYN-DC-NORTH-DC-SOUTH": 50.0,
    }
    assert OPS_TO_DATA_CENTER_UNITS == 10.0
    assert DATA_CENTER_PAIR_UNITS == 50.0


def test_hub_east_is_the_endpoint_of_no_synthetic_demand(network: Network) -> None:
    """HUB-EAST is an aggregation hub, so R4 gives it nothing.

    It is the one row that looks like an operations site from the outside,
    since six of the nine rows are operations sites and it sits among them,
    and it is the trap this assertion exists to catch.
    """
    for demand in network.demands:
        if demand.id.startswith("SYN-"):
            assert "HUB-EAST" not in demand.endpoints, demand.id


# --------------------------------------------------------------------------
# The real files: R6 and placement
# --------------------------------------------------------------------------


def test_twenty_nine_nodes_may_forward_traffic(network: Network) -> None:
    """R6: the 28 backbone cities plus HUB-EAST, and nothing else.

    28 + 1 = 29. The two data centers and the six operations sites are
    endpoints only, which is the distinction the router depends on.
    """
    assert len(network.transit_nodes) == 29
    assert "HUB-EAST" in network.transit_nodes
    assert network.transit_nodes == frozenset(
        node.id
        for node in network.nodes.values()
        if node.kind in {NodeKind.BACKBONE_CITY, NodeKind.AGGREGATION_HUB}
    )


def test_dc_north_sits_at_the_midpoint_of_hamburg_and_copenhagen(
    network: Network,
) -> None:
    """Worked by hand from the two coordinates in data/nobel-eu.xml.

    Hamburg is <x>10.0</x><y>53.33</y> and Copenhagen is <x>12.32</x>
    <y>55.41</y>. With two attachments the centroid is the midpoint:
    x = (10.0 + 12.32) / 2 = 22.32 / 2 = 11.16
    y = (53.33 + 55.41) / 2 = 108.74 / 2 = 54.37
    Approximate comparison because both halves are binary floats, not
    because the arithmetic is in doubt.
    """
    assert network.nodes["Hamburg"].coordinates == Coordinates(x=10.0, y=53.33)
    assert network.nodes["Copenhagen"].coordinates == Coordinates(x=12.32, y=55.41)

    placed = network.nodes["DC-NORTH"].coordinates
    assert placed.x == pytest.approx(11.16)
    assert placed.y == pytest.approx(54.37)


def test_every_site_sits_at_the_centroid_of_its_attachments(network: Network) -> None:
    """The placement rule, checked against the rows for all nine sites.

    This covers the dependency order too: OPS-EAST-1's only attachment is
    HUB-EAST, so its position can only match if HUB-EAST was placed first,
    which is the iterative resolution working.
    """
    for site in load_sites(SITES):
        points = [network.nodes[target].coordinates for target in site.attaches_to]
        placed = network.nodes[site.site_id].coordinates
        assert placed.x == pytest.approx(sum(p.x for p in points) / len(points)), site.site_id
        assert placed.y == pytest.approx(sum(p.y for p in points) / len(points)), site.site_id

    # OPS-EAST-1 inherits HUB-EAST's position exactly, because HUB-EAST is
    # its one attachment. P8 adds the offset that pulls the two apart.
    assert network.nodes["OPS-EAST-1"].coordinates == network.nodes["HUB-EAST"].coordinates


def test_the_merge_is_deterministic() -> None:
    """Two builds from the same files agree node for node and demand for demand.

    Nothing here iterates a set, so this should hold trivially. It is cheap
    insurance against a later change that does.
    """
    first = build_network(load_backbone(SNDLIB), load_sites(SITES), sites_file=str(SITES))
    second = build_network(load_backbone(SNDLIB), load_sites(SITES), sites_file=str(SITES))
    assert first.nodes == second.nodes
    assert first.links == second.links
    assert first.demands == second.demands


# --------------------------------------------------------------------------
# Synthetic rows: the rules the merge adds, R2
# --------------------------------------------------------------------------

FIXTURE_FILE = "/fixture/sites.csv"

CITY_A = Node(id="CityA", kind=NodeKind.BACKBONE_CITY, coordinates=Coordinates(x=0.0, y=50.0))
CITY_B = Node(id="CityB", kind=NodeKind.BACKBONE_CITY, coordinates=Coordinates(x=2.0, y=52.0))


def _backbone(*, links: tuple[ParsedLink, ...] = ()) -> ParsedBackbone:
    """Two cities joined by nothing, unless the caller asks for a link.

    The merge does not care whether the backbone is connected, so the
    smallest backbone that can host an attachment is enough.
    """
    return ParsedBackbone(nodes=(CITY_A, CITY_B), links=links, demands=())


def _site(
    site_id: str,
    kind: NodeKind,
    attaches_to: tuple[str, ...],
    row: int,
    capacity: float = 40.0,
) -> ParsedSite:
    return ParsedSite(
        site_id=site_id,
        kind=kind,
        attaches_to=attaches_to,
        access_capacity=capacity,
        row=row,
    )


def _two_data_centers() -> tuple[ParsedSite, ...]:
    """The pair R4 needs, so that a test of another rule reaches that rule."""
    return (
        _site("DC-ONE", NodeKind.DATA_CENTER, ("CityA",), row=2, capacity=200.0),
        _site("DC-TWO", NodeKind.DATA_CENTER, ("CityB",), row=3, capacity=200.0),
    )


@dataclass(frozen=True)
class Rejection:
    """One malformed table, the row it should be blamed on, and a phrase."""

    name: str
    backbone: ParsedBackbone
    sites: tuple[ParsedSite, ...]
    row: int | None
    phrase: str


REJECTIONS: tuple[Rejection, ...] = (
    Rejection(
        name="site_id collides with a backbone city",
        backbone=_backbone(),
        sites=(
            *_two_data_centers(),
            _site("CityA", NodeKind.OPERATIONS_SITE, ("CityB",), row=4),
        ),
        row=4,
        phrase="already a backbone city",
    ),
    Rejection(
        name="two sites attach to each other, duplicating one access link",
        backbone=_backbone(),
        # OPS-P--OPS-Q and OPS-Q--OPS-P are the same Endpoints pair, so the
        # second row asks for a link the first row already built. The blame
        # is on row 5, the row that caused the collision.
        sites=(
            *_two_data_centers(),
            _site("OPS-P", NodeKind.OPERATIONS_SITE, ("OPS-Q",), row=4),
            _site("OPS-Q", NodeKind.OPERATIONS_SITE, ("OPS-P",), row=5),
        ),
        row=5,
        phrase="already joins",
    ),
    Rejection(
        name="an access link id is already taken by a backbone link",
        # Contrived, and that is the point: nothing in SNDlib names a link
        # this way, so the only way to prove the guard works is to hand the
        # merge a backbone link whose id is the one the row will synthesize.
        backbone=_backbone(
            links=(ParsedLink(id="ACC-DC-ONE-CityA", endpoints=Endpoints("CityA", "CityB")),)
        ),
        sites=_two_data_centers(),
        row=2,
        phrase="already taken",
    ),
    Rejection(
        name="only one data center, so the R4 pair demand has no pair",
        backbone=_backbone(),
        sites=(
            _site("DC-ONE", NodeKind.DATA_CENTER, ("CityA",), row=2, capacity=200.0),
            _site("OPS-P", NodeKind.OPERATIONS_SITE, ("CityB",), row=3),
        ),
        # No row: a missing data center is a property of the whole table,
        # not of any row that is actually present.
        row=None,
        phrase="needs at least 2",
    ),
    Rejection(
        name="three data centers, so the R4 pair is ambiguous",
        backbone=_backbone(),
        sites=(
            *_two_data_centers(),
            _site("DC-THREE", NodeKind.DATA_CENTER, ("CityA",), row=4, capacity=200.0),
        ),
        # Row 4 is the first row beyond the pair, which is the row that makes
        # the rule ambiguous.
        row=4,
        phrase="written for exactly 2",
    ),
    Rejection(
        name="three sites attach in a circle, so none can be placed",
        backbone=_backbone(),
        # OPS-P needs OPS-Q, which needs OPS-R, which needs OPS-P. No pass
        # can place any of them. Three rows rather than two, because a
        # mutual pair of two would be rejected as a duplicate link first.
        sites=(
            *_two_data_centers(),
            _site("OPS-P", NodeKind.OPERATIONS_SITE, ("OPS-Q",), row=4),
            _site("OPS-Q", NodeKind.OPERATIONS_SITE, ("OPS-R",), row=5),
            _site("OPS-R", NodeKind.OPERATIONS_SITE, ("OPS-P",), row=6),
        ),
        # The lowest row of the blocked group, so the message does not move
        # between runs.
        row=4,
        phrase="circle",
    ),
    Rejection(
        name="an attachment target that is neither a city nor a site",
        backbone=_backbone(),
        sites=(
            *_two_data_centers(),
            _site("OPS-P", NodeKind.OPERATIONS_SITE, ("Atlantis",), row=4),
        ),
        row=4,
        phrase="unknown target",
    ),
)


@pytest.mark.parametrize("case", REJECTIONS, ids=[case.name for case in REJECTIONS])
def test_rejection_names_the_file_and_the_row(case: Rejection) -> None:
    """Every merge rule rejects, names ``sites_file``, and blames one row."""
    with pytest.raises(InputError) as raised:
        build_network(case.backbone, case.sites, sites_file=FIXTURE_FILE)

    error = raised.value
    assert error.file == FIXTURE_FILE
    assert error.row == case.row
    assert case.phrase in error.message
    assert FIXTURE_FILE in str(error)
    if case.row is not None:
        assert f"row {case.row}" in str(error)


def test_a_table_with_no_operations_sites_still_merges() -> None:
    """R4's first clause is a loop, so zero operations sites means zero demands.

    Nothing in the code assumes six, which this proves: the only synthetic
    demand left is the data center pair.
    """
    merged = build_network(_backbone(), _two_data_centers(), sites_file=FIXTURE_FILE)
    assert [(demand.id, demand.volume) for demand in merged.demands] == [
        ("SYN-DC-ONE-DC-TWO", 50.0)
    ]


def test_synthetic_demand_ids_do_not_depend_on_row_order() -> None:
    """The same two rows in either order give the same ids and volumes.

    The ids come off the sorted ``Endpoints`` pair rather than off the
    argument order, so reversing the table cannot rename a demand.
    """
    sites = (
        *_two_data_centers(),
        _site("OPS-P", NodeKind.OPERATIONS_SITE, ("CityA",), row=4),
    )
    forward = build_network(_backbone(), sites, sites_file=FIXTURE_FILE)
    reversed_rows = build_network(_backbone(), tuple(reversed(sites)), sites_file=FIXTURE_FILE)

    def summary(network: Network) -> dict[str, float]:
        return {demand.id: demand.volume for demand in network.demands}

    assert summary(forward) == summary(reversed_rows)
    assert summary(forward) == {
        "SYN-DC-ONE-OPS-P": 10.0,
        "SYN-DC-TWO-OPS-P": 10.0,
        "SYN-DC-ONE-DC-TWO": 50.0,
    }


def test_a_site_attached_to_another_site_is_placed_after_it() -> None:
    """The dependency order, on rows small enough to check the arithmetic.

    DC-ONE attaches to CityA at (0.0, 50.0) and CityB at (2.0, 52.0), so it
    lands at (1.0, 51.0). OPS-P attaches only to DC-ONE, so it inherits that
    exact position, which it can only do if DC-ONE was placed first.
    """
    sites = (
        _site("DC-ONE", NodeKind.DATA_CENTER, ("CityA", "CityB"), row=2, capacity=200.0),
        _site("DC-TWO", NodeKind.DATA_CENTER, ("CityB",), row=3, capacity=200.0),
        _site("OPS-P", NodeKind.OPERATIONS_SITE, ("DC-ONE",), row=4),
    )
    merged = build_network(_backbone(), sites, sites_file=FIXTURE_FILE)

    assert merged.nodes["DC-ONE"].coordinates == Coordinates(x=1.0, y=51.0)
    assert merged.nodes["OPS-P"].coordinates == Coordinates(x=1.0, y=51.0)


def test_a_forward_reference_between_rows_places_just_as_well() -> None:
    """The dependent row first, since nothing in the format fixes row order.

    OPS-P is row 2 and the DC-ONE it attaches to is row 3. The first pass
    places DC-ONE and DC-TWO, the second places OPS-P.
    """
    sites = (
        _site("OPS-P", NodeKind.OPERATIONS_SITE, ("DC-ONE",), row=2),
        _site("DC-ONE", NodeKind.DATA_CENTER, ("CityA", "CityB"), row=3, capacity=200.0),
        _site("DC-TWO", NodeKind.DATA_CENTER, ("CityB",), row=4, capacity=200.0),
    )
    merged = build_network(_backbone(), sites, sites_file=FIXTURE_FILE)
    assert merged.nodes["OPS-P"].coordinates == Coordinates(x=1.0, y=51.0)


def test_demands_from_file_a_survive_the_merge_unchanged() -> None:
    """The merge adds to file A's demands and never rewrites one.

    A demand whose volume or endpoints changed in transit would still leave
    the counts right, so the pass-through is asserted on its own.
    """
    original = Demand(id="CityACityB", endpoints=Endpoints("CityA", "CityB"), volume=7.5)
    backbone = ParsedBackbone(nodes=(CITY_A, CITY_B), links=(), demands=(original,))
    merged = build_network(backbone, _two_data_centers(), sites_file=FIXTURE_FILE)

    assert merged.demands[0] is original
    # 7.5 from the demand above plus the one 50 unit data center pair.
    assert merged.total_demand == 57.5
