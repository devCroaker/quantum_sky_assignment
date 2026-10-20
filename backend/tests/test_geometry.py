"""Tests for site placement (R9).

The headline test is that no two nodes in the real merged network share a
position. Before the offset, five nodes sat on two points: ``HUB-EAST`` on
Warsaw and ``OPS-EAST-1`` on both, ``OPS-WEST`` on Dublin and
``OPS-SOUTHEAST`` on Athens. Three markers at one pixel cannot be clicked,
which breaks R11, and a site under a city is not legible as a separate
node, which is what R9 asks for.

Every number here is either a model constant, a coordinate quoted from
``data/nobel-eu.xml``, or computed from the input files inside the test.
The three fractions below are the only judgement calls, and each one states
which site makes it binding and what that site's measured value is.

"Unrelated" needs a definition, because the obvious one does not survive
the eastern chain. ``HUB-EAST``'s nearest node is ``OPS-EAST-1``, which is
only there because it attaches to ``HUB-EAST``, and ``OPS-EAST-2``'s
nearest node is Warsaw, which is where ``HUB-EAST`` and therefore
``OPS-EAST-2`` derive from. Neither is an unrelated city by any reading. So
a node is unrelated to a site when it is none of: the site itself, one of
its attachments, a node its position transitively derives from, or a node
that attaches to it.
"""

from __future__ import annotations

import itertools
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from netscope.errors import InputError
from netscope.loaders.geometry import SITE_OFFSET_DEGREES, place_sites
from netscope.loaders.merge import build_network
from netscope.loaders.sites_csv import ParsedSite, load_sites
from netscope.loaders.sndlib_xml import ParsedBackbone, load_backbone
from netscope.models import Coordinates, Network, Node, NodeKind

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SNDLIB = DATA / "nobel-eu.xml"
SITES = DATA / "sites.csv"

#: How far apart two positions must be to count as two positions. Well
#: below the two decimal places the input coordinates carry, so this
#: tolerance can only forgive floating point noise and never a real gap.
SAME_POINT_DEGREES = 1e-9

#: A site may sit this fraction of the way from its own attachments to the
#: nearest unrelated node, and no further. R9 asks for each site to be
#: shown near what it attaches to, and anything under 1.0 says it is
#: nearer to its attachments than to anything unrelated. The binding case
#: is OPS-EAST-2 at 0.888: it attaches to HUB-EAST and Budapest, which are
#: 5.45 degrees apart, so its centroid is 2.75 from each while OPS-EAST-1
#: happens to be 3.09 away. That spread comes from the centroid rule and
#: not from the offset, which is why this fraction is loose and the next
#: one is not.
MAX_ATTACHMENT_FRACTION = 0.9

#: The offset itself may move a site this fraction of the way to the
#: nearest unrelated node. This is the test of "small": the displacement is
#: SITE_OFFSET_DEGREES for every site, so the fraction is set by whichever
#: site has the closest unrelated neighbour. That is DC-SOUTH, 2.53 degrees
#: from Strasbourg, giving 0.35 / 2.53 = 0.138.
MAX_OFFSET_FRACTION = 0.2

#: The offset may be this fraction of the distance between the two closest
#: backbone cities, which the test measures from the file rather than
#: quoting. Those are Strasbourg and Zurich at 1.4261 degrees, so the
#: measured value is 0.35 / 1.4261 = 0.245. A site therefore cannot travel
#: far enough to reach a neighbouring city even when its own anchor is a
#: site that has already been offset.
MAX_CITY_GAP_FRACTION = 0.25


@pytest.fixture(scope="module")
def network() -> Network:
    return build_network(load_backbone(SNDLIB), load_sites(SITES), sites_file=str(SITES))


@pytest.fixture(scope="module")
def sites() -> tuple[ParsedSite, ...]:
    return load_sites(SITES)


def separation(one: Node, other: Node) -> float:
    """The distance between two nodes, in degrees."""
    return math.dist(
        (one.coordinates.x, one.coordinates.y),
        (other.coordinates.x, other.coordinates.y),
    )


def unrelated_to(site: ParsedSite, sites: tuple[ParsedSite, ...], network: Network) -> list[Node]:
    """Every node that says nothing about where ``site`` should be.

    See the module docstring for why this is not simply "not one of its
    attachments".
    """
    by_id = {other.site_id: other for other in sites}
    related = {site.site_id}

    anchors = list(site.attaches_to)
    while anchors:
        target = anchors.pop()
        if target in related:
            continue
        related.add(target)
        if target in by_id:
            anchors.extend(by_id[target].attaches_to)

    related.update(other.site_id for other in sites if site.site_id in other.attaches_to)
    return [node for node_id, node in network.nodes.items() if node_id not in related]


# --------------------------------------------------------------------------
# The real network
# --------------------------------------------------------------------------


def test_no_two_nodes_in_the_real_network_share_a_position(network: Network) -> None:
    """The headline test, over all 37 nodes and all 666 pairs.

    37 * 36 / 2 = 666. The closest pair in the whole network is one offset
    apart, which is also asserted: nothing is nearer to anything than the
    gap the offset deliberately opens.
    """
    pairs = list(itertools.combinations(sorted(network.nodes), 2))
    assert len(pairs) == 666

    closest = min(
        (separation(network.nodes[one], network.nodes[other]), one, other) for one, other in pairs
    )
    distance, one, other = closest
    assert distance > SAME_POINT_DEGREES, f"{one} and {other} share a position"
    assert distance == pytest.approx(SITE_OFFSET_DEGREES)


def test_warsaw_hub_east_and_ops_east_1_are_three_separate_points(
    network: Network,
) -> None:
    """The three nodes that used to share one coordinate.

    HUB-EAST attaches to Warsaw and OPS-EAST-1 attaches to HUB-EAST, so the
    plain centroid put all three on Warsaw's coordinate. Each step now
    moves away from the nearest node that is not its own attachment, which
    for HUB-EAST is Budapest and for OPS-EAST-1 is Warsaw itself. The result
    is a straight chain out of Warsaw: one offset to HUB-EAST and two to
    OPS-EAST-1, so each site is nearer to its own attachment than to
    anything behind it.
    """
    warsaw = network.nodes["Warsaw"]
    hub = network.nodes["HUB-EAST"]
    ops = network.nodes["OPS-EAST-1"]

    assert len({(node.coordinates.x, node.coordinates.y) for node in (warsaw, hub, ops)}) == 3
    assert separation(warsaw, hub) == pytest.approx(SITE_OFFSET_DEGREES)
    assert separation(hub, ops) == pytest.approx(SITE_OFFSET_DEGREES)
    assert separation(warsaw, ops) == pytest.approx(2 * SITE_OFFSET_DEGREES)
    # OPS-EAST-1 attaches to HUB-EAST, so it has to be the closer of the two.
    assert separation(hub, ops) < separation(warsaw, ops)


@pytest.mark.parametrize(
    ("site_id", "city"),
    [("OPS-WEST", "Dublin"), ("OPS-SOUTHEAST", "Athens")],
)
def test_a_single_homed_site_has_left_its_city(network: Network, site_id: str, city: str) -> None:
    """The other two sites that used to sit exactly on a city."""
    site = network.nodes[site_id]
    anchor = network.nodes[city]
    assert site.coordinates != anchor.coordinates
    assert separation(site, anchor) == pytest.approx(SITE_OFFSET_DEGREES)


def test_every_site_is_exactly_one_offset_from_its_centroid(
    network: Network, sites: tuple[ParsedSite, ...]
) -> None:
    """The centroid rule survives: placement is centroid plus one offset.

    Checked for all nine rows, which also covers the dependency order,
    since OPS-EAST-1's centroid is HUB-EAST's position and that only exists
    if HUB-EAST was placed first.
    """
    for site in sites:
        points = [network.nodes[target].coordinates for target in site.attaches_to]
        centroid = Coordinates(
            x=sum(point.x for point in points) / len(points),
            y=sum(point.y for point in points) / len(points),
        )
        placed = network.nodes[site.site_id].coordinates
        displacement = math.dist((placed.x, placed.y), (centroid.x, centroid.y))
        assert displacement == pytest.approx(SITE_OFFSET_DEGREES), site.site_id


def test_every_site_stays_nearer_its_attachments_than_anything_unrelated(
    network: Network, sites: tuple[ParsedSite, ...]
) -> None:
    """R9, for all nine rows: each site is shown near what it attaches to."""
    for site in sites:
        placed = network.nodes[site.site_id]
        furthest_attachment = max(
            separation(placed, network.nodes[target]) for target in site.attaches_to
        )
        nearest_unrelated = min(
            separation(placed, other) for other in unrelated_to(site, sites, network)
        )
        assert furthest_attachment / nearest_unrelated < MAX_ATTACHMENT_FRACTION, site.site_id


def test_a_multi_attachment_site_sits_between_its_attachments(
    network: Network, sites: tuple[ParsedSite, ...]
) -> None:
    """DC-NORTH and OPS-IBERIA, the two-attachment cases.

    The offset is perpendicular to the line through the attachments, so the
    site stays exactly equidistant from the two of them, and that distance
    is nearer than any unrelated city. Equidistance is what makes "between"
    mean something: a site that had drifted along the line towards one end
    would still pass a nearest-neighbour check.
    """
    for site_id in ("DC-NORTH", "OPS-IBERIA"):
        site = next(row for row in sites if row.site_id == site_id)
        placed = network.nodes[site_id]
        distances = [separation(placed, network.nodes[target]) for target in site.attaches_to]
        assert len(distances) == 2
        assert distances[0] == pytest.approx(distances[1])
        for other in unrelated_to(site, sites, network):
            assert max(distances) < separation(placed, other), f"{site_id} vs {other.id}"


def test_the_offset_is_small_against_the_distances_on_the_map(
    network: Network, sites: tuple[ParsedSite, ...]
) -> None:
    """Two readings of "small", both measured from the real data.

    First, against each site's own surroundings: the offset moves a site a
    small fraction of the way to the nearest node that says nothing about
    where it belongs. Second, against the map as a whole: the offset is
    under a quarter of the gap between the two closest backbone cities, so
    no site can be pushed into one.
    """
    for site in sites:
        placed = network.nodes[site.site_id]
        nearest_unrelated = min(
            separation(placed, other) for other in unrelated_to(site, sites, network)
        )
        assert SITE_OFFSET_DEGREES / nearest_unrelated < MAX_OFFSET_FRACTION, site.site_id

    cities = [node for node in network.nodes.values() if node.kind is NodeKind.BACKBONE_CITY]
    assert len(cities) == 28
    closest_gap = min(separation(one, other) for one, other in itertools.combinations(cities, 2))
    assert SITE_OFFSET_DEGREES / closest_gap < MAX_CITY_GAP_FRACTION


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_placing_twice_gives_identical_coordinates() -> None:
    """Exact equality, not approximate: the same input, the same floats."""
    backbone = load_backbone(SNDLIB)
    known = {node.id: node.coordinates for node in backbone.nodes}
    first = place_sites(load_sites(SITES), known, sites_file=str(SITES))
    second = place_sites(load_sites(SITES), known, sites_file=str(SITES))
    assert first == second
    # Dataclass equality compares floats, so spell out that the bits match.
    assert [(key, first[key].x.hex(), first[key].y.hex()) for key in sorted(first)] == [
        (key, second[key].x.hex(), second[key].y.hex()) for key in sorted(second)
    ]


#: Prints every placed coordinate at full precision, for the subprocess
#: comparison below. ``float.hex`` rather than ``repr`` so the comparison is
#: over the bits and not over a rounded rendering.
_PLACEMENT_SCRIPT = """
import sys
from pathlib import Path

from netscope.loaders.geometry import place_sites
from netscope.loaders.sites_csv import load_sites
from netscope.loaders.sndlib_xml import load_backbone

data = Path(sys.argv[1])
backbone = load_backbone(data / "nobel-eu.xml")
placed = place_sites(
    load_sites(data / "sites.csv"),
    {node.id: node.coordinates for node in backbone.nodes},
    sites_file="sites.csv",
)
for node_id in sorted(placed):
    print(node_id, placed[node_id].x.hex(), placed[node_id].y.hex())
"""


def _placement_in_a_fresh_process(hash_seed: str) -> str:
    environment = dict(os.environ)
    environment["PYTHONHASHSEED"] = hash_seed
    completed = subprocess.run(
        [sys.executable, "-c", _PLACEMENT_SCRIPT, str(DATA)],
        capture_output=True,
        check=True,
        text=True,
        env=environment,
    )
    return completed.stdout


def test_placement_does_not_depend_on_the_hash_seed() -> None:
    """Two fresh interpreters with different hash seeds agree byte for byte.

    String hashing is salted per process, so anything that iterated a set
    or relied on dictionary order built from unordered input would differ
    between these two runs. Running the placement in-process twice cannot
    catch that, because both runs would share the one salt.
    """
    first = _placement_in_a_fresh_process("0")
    second = _placement_in_a_fresh_process("12345")
    assert first == second
    # 28 cities and 9 sites, one line each, so the comparison is not of two
    # empty strings.
    assert len(first.splitlines()) == 37


# --------------------------------------------------------------------------
# Synthetic rows
# --------------------------------------------------------------------------

FIXTURE_FILE = "/fixture/sites.csv"

CITY_A = Node(id="CityA", kind=NodeKind.BACKBONE_CITY, coordinates=Coordinates(x=0.0, y=50.0))
CITY_B = Node(id="CityB", kind=NodeKind.BACKBONE_CITY, coordinates=Coordinates(x=2.0, y=52.0))


def _site(site_id: str, attaches_to: tuple[str, ...], row: int) -> ParsedSite:
    return ParsedSite(
        site_id=site_id,
        kind=NodeKind.OPERATIONS_SITE,
        attaches_to=attaches_to,
        access_capacity=40.0,
        row=row,
    )


def _known() -> dict[str, Coordinates]:
    return {CITY_A.id: CITY_A.coordinates, CITY_B.id: CITY_B.coordinates}


def test_sites_with_identical_attachments_still_get_distinct_positions() -> None:
    """Three sites, one attachment list, so one centroid and one direction.

    This is the case the direction rules cannot solve on their own: the
    rows are indistinguishable from each other geometrically. Each
    candidate that is already taken is rotated by the golden angle, so all
    three land one offset from the shared centroid on three different
    bearings.
    """
    rows = (
        _site("OPS-P", ("CityA", "CityB"), row=2),
        _site("OPS-Q", ("CityA", "CityB"), row=3),
        _site("OPS-R", ("CityA", "CityB"), row=4),
    )
    placed = place_sites(rows, _known(), sites_file=FIXTURE_FILE)

    centroid = (1.0, 51.0)
    positions = [(placed[row.site_id].x, placed[row.site_id].y) for row in rows]
    assert len(set(positions)) == 3
    for site_id, position in zip([row.site_id for row in rows], positions, strict=True):
        assert math.dist(position, centroid) == pytest.approx(SITE_OFFSET_DEGREES), site_id
    for one, other in itertools.combinations(positions, 2):
        assert math.dist(one, other) > SAME_POINT_DEGREES


def test_row_order_does_not_change_where_a_site_lands() -> None:
    """The same rows shuffled give the same coordinates.

    Placement walks the rows in ``row`` order rather than in the order the
    caller built the tuple, which is what makes a tie-break between two
    identical rows a property of the file.
    """
    rows = (
        _site("OPS-P", ("CityA", "CityB"), row=2),
        _site("OPS-Q", ("CityA", "CityB"), row=3),
        _site("OPS-R", ("CityA",), row=4),
    )
    forward = place_sites(rows, _known(), sites_file=FIXTURE_FILE)
    backward = place_sites(tuple(reversed(rows)), _known(), sites_file=FIXTURE_FILE)
    assert forward == backward


def test_a_chain_of_attachments_is_resolved_in_order() -> None:
    """A site attached to a site attached to a city, as the east is.

    OPS-Q cannot be placed until OPS-P is, whatever order the rows arrive
    in, and each link of the chain is exactly one offset long.
    """
    rows = (
        _site("OPS-Q", ("OPS-P",), row=2),
        _site("OPS-P", ("CityA",), row=3),
    )
    placed = place_sites(rows, _known(), sites_file=FIXTURE_FILE)

    city = (CITY_A.coordinates.x, CITY_A.coordinates.y)
    first = (placed["OPS-P"].x, placed["OPS-P"].y)
    second = (placed["OPS-Q"].x, placed["OPS-Q"].y)
    assert math.dist(city, first) == pytest.approx(SITE_OFFSET_DEGREES)
    assert math.dist(first, second) == pytest.approx(SITE_OFFSET_DEGREES)
    # Away from the nearest other node rather than back onto it: CityA is
    # the far end of a straight line, not the midpoint of one.
    assert math.dist(city, second) == pytest.approx(2 * SITE_OFFSET_DEGREES)


def test_a_circle_of_attachments_is_rejected_with_a_located_error() -> None:
    """P7's rejection, unchanged: the file, the lowest blocked row, the column.

    OPS-P needs OPS-Q, which needs OPS-R, which needs OPS-P, so no pass can
    place any of them. Row 2 is the lowest row of the blocked group, so the
    message does not move between runs.
    """
    rows = (
        _site("OPS-P", ("OPS-Q",), row=2),
        _site("OPS-Q", ("OPS-R",), row=3),
        _site("OPS-R", ("OPS-P",), row=4),
    )
    with pytest.raises(InputError) as raised:
        place_sites(rows, _known(), sites_file=FIXTURE_FILE)

    error = raised.value
    assert error.file == FIXTURE_FILE
    assert error.row == 2
    assert error.field == "attaches_to"
    assert "circle" in error.message
    assert FIXTURE_FILE in str(error)
    assert "row 2" in str(error)


def test_a_site_with_nothing_to_derive_from_is_rejected() -> None:
    """A hand-built row with no attachments, which the loader cannot produce.

    The guard exists so that such a row is reported with its row number
    rather than dividing by zero inside the centroid.
    """
    with pytest.raises(InputError) as raised:
        place_sites((_site("OPS-P", (), row=2),), _known(), sites_file=FIXTURE_FILE)
    assert raised.value.row == 2
    assert "no attachment" in raised.value.message


def test_the_only_node_in_the_input_still_yields_a_placement() -> None:
    """One city and one site, so there is nothing to take a bearing from.

    The documented fallback direction applies, and the point of the test is
    that the site is still somewhere other than on top of the city.
    """
    known = {CITY_A.id: CITY_A.coordinates}
    placed = place_sites((_site("OPS-P", ("CityA",), row=2),), known, sites_file=FIXTURE_FILE)
    assert placed["OPS-P"] != CITY_A.coordinates
    assert math.dist(
        (placed["OPS-P"].x, placed["OPS-P"].y),
        (CITY_A.coordinates.x, CITY_A.coordinates.y),
    ) == pytest.approx(SITE_OFFSET_DEGREES)


def test_placement_returns_the_cities_it_was_given_untouched() -> None:
    """The return value is every node's position, and only sites move."""
    placed = place_sites((_site("OPS-P", ("CityA",), row=2),), _known(), sites_file=FIXTURE_FILE)
    assert placed["CityA"] == CITY_A.coordinates
    assert placed["CityB"] == CITY_B.coordinates
    assert sorted(placed) == ["CityA", "CityB", "OPS-P"]


def test_the_real_backbone_has_no_two_cities_on_one_point() -> None:
    """The input's own coordinates, so that the headline test means what it says.

    If two cities in file A shared a coordinate, no placement rule could
    fix it, and the non-overlap test would be asserting something it has no
    control over.
    """
    backbone: ParsedBackbone = load_backbone(SNDLIB)
    points = {(node.coordinates.x, node.coordinates.y) for node in backbone.nodes}
    assert len(points) == len(backbone.nodes) == 28
