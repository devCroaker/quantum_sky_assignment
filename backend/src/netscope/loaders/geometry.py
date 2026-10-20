"""Where every site sits on the map (R9, D9).

``Node`` requires coordinates and the site table has none, so a site's
position is derived from the positions of the nodes it attaches to. P7 put
each site at the plain centroid of those points. That is correct and it is
also unusable: a site with one attachment lands exactly on top of it, so
``HUB-EAST`` fell on Warsaw, ``OPS-EAST-1`` fell on ``HUB-EAST`` and all
three shared one pixel. Three markers at one pixel cannot be clicked, which
breaks R11, and a site drawn on a city is not legible as a separate node,
which is what R9 asks for. This module keeps the centroid and adds a small
deterministic offset.

**Dependency order.** A site can only be placed once every node it attaches
to has a position, and a site may attach to another site: ``OPS-EAST-1``
attaches to ``HUB-EAST``, whose own position is derived from Warsaw. So this
places whatever it can, repeatedly, and a pass that places nothing while
sites remain means those sites depend on one another in a circle, which has
no answer and is reported rather than approximated. That behaviour comes
from P7 unchanged.

**Direction.** The offset is never a fixed compass bearing, because a fixed
bearing would push some site onto the far side of its own city or on top of
a neighbour. Instead:

- With two or more attachment points that are not all in the same place,
  the site moves perpendicular to the line through them, which keeps it
  equidistant from the two ends and so keeps it reading as sitting between
  them. Of the two perpendiculars, the one pointing away from the nearest
  node that is not one of its attachments is taken, so the site moves into
  the emptier side.
- With a single attachment there is no "away" from one point, so the
  direction comes from the surroundings instead: the site moves directly
  away from the nearest node that is not one of its attachments. This is
  what spreads the eastern chain out in a line, since ``HUB-EAST`` moves
  away from the node nearest Warsaw and ``OPS-EAST-1`` then moves away from
  Warsaw itself, rather than doubling back on top of it.

**Distinctness.** The rules above are what makes the result legible. They
are not what makes it correct, because two sites can attach to the same set
of nodes and so share a centroid and a direction. A candidate position that
coincides with a position already taken is therefore rotated by the golden
angle until it is free. Every node ending up somewhere different is a
guarantee of the construction and not a property of this particular input.

**Determinism.** Rows are processed in ``row`` order and the reference node
is chosen by distance with the node id as the tie-break, so nothing here
depends on dictionary insertion, set iteration or hashing. The same input
gives byte-identical output in any process.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from netscope.errors import InputError
from netscope.loaders.sites_csv import ParsedSite
from netscope.models import Coordinates

__all__ = ["SITE_OFFSET_DEGREES", "place_sites"]

#: How far a site is pushed from the centroid of its attachments, in
#: degrees. Coordinates are degrees of longitude (x) and latitude (y), and
#: the real network spans 29.57 degrees of longitude, -6.15 to 23.42, and
#: 21.96 of latitude, 37.58 to 59.54. The two closest backbone cities,
#: Strasbourg and Zurich, are 1.4261 degrees apart. 0.35 is just under a
#: quarter of that gap, so even the doubled offset of a chained site,
#: ``OPS-EAST-1`` behind ``HUB-EAST`` behind Warsaw, stays at half the
#: distance between the two closest cities and can never reach one. It is
#: also about 1.2% of the longitude span, which is a visible gap at any
#: zoom level that shows the whole network. Both figures are asserted
#: against the real data in ``tests/test_geometry.py`` rather than trusted.
SITE_OFFSET_DEGREES = 0.35

#: Used only to break a tie, when two sites attach to the same nodes and so
#: want the same spot. The golden angle, about 137.5 degrees, is the
#: standard choice for spreading points around a circle without any two
#: landing close together, whatever the count turns out to be.
_TIE_BREAK_ROTATION_RADIANS = math.pi * (3.0 - math.sqrt(5.0))

#: Two positions this close together are the same pixel on any map, and
#: well below the precision of the input coordinates, which carry two
#: decimal places.
_COINCIDENT_TOLERANCE_DEGREES = 1e-9

#: Used only when a site has nothing at all to take a bearing from, which
#: needs an input with a single attachment and no other node anywhere. Due
#: east, so the fallback at least reads as deliberate.
_FALLBACK_DIRECTION = (1.0, 0.0)

_Vector = tuple[float, float]


def place_sites(
    sites: tuple[ParsedSite, ...],
    known: Mapping[str, Coordinates],
    *,
    sites_file: str,
) -> dict[str, Coordinates]:
    """Position every site, and return every node's position.

    Args:
        sites: the site rows, in any order. Placement follows ``row``, not
            the order they arrive in.
        known: the positions already fixed by the input file, which is the
            backbone cities. A site may attach to one of these or to
            another site.
        sites_file: the path the rows came from, named in a rejection.

    Returns:
        ``known`` plus one entry per site. No two entries share a position.

    Raises:
        InputError: if a group of sites attach to one another in a circle,
            so that no member of the group has anything to derive a
            position from.
    """
    placed: dict[str, Coordinates] = dict(known)
    # Row order, so that the sequence of placements, and therefore every
    # tie-break that depends on what is already placed, is a property of
    # the file and not of the order a caller happened to build the tuple.
    pending: list[ParsedSite] = sorted(sites, key=lambda site: site.row)

    while pending:
        ready = [site for site in pending if all(target in placed for target in site.attaches_to)]
        if not ready:
            # The lowest row of the blocked group, so the message is the same
            # on every run whatever order the rows arrived in.
            blocked = min(pending, key=lambda site: site.row)
            raise InputError(
                sites_file,
                f"site {blocked.site_id!r} cannot be placed because its attachments "
                "lead in a circle back to itself, so no site in that circle has a "
                "position to derive from",
                row=blocked.row,
                field="attaches_to",
            )
        for site in ready:
            placed[site.site_id] = _place_one(site, placed, sites_file)
        pending = [site for site in pending if site.site_id not in placed]

    return placed


def _place_one(
    site: ParsedSite,
    placed: Mapping[str, Coordinates],
    sites_file: str,
) -> Coordinates:
    """One site's position: the centroid of its attachments, then offset."""
    points = tuple(placed[target] for target in site.attaches_to)
    if not points:
        # The loader rejects an empty attaches_to, so reaching this needs a
        # hand-built ParsedSite. Saying so beats a ZeroDivisionError.
        raise InputError(
            sites_file,
            f"site {site.site_id!r} has no attachment, so there is nothing to "
            "derive a position from",
            row=site.row,
            field="attaches_to",
        )

    anchor = _centroid(points)
    reference = _nearest_other(anchor, placed, frozenset(site.attaches_to) | {site.site_id})
    return _free_position(anchor, _offset_direction(points, anchor, reference), placed)


def _centroid(points: Sequence[Coordinates]) -> Coordinates:
    """The plain mean of the points a site attaches to, with no offset."""
    count = len(points)
    return Coordinates(
        x=sum(point.x for point in points) / count,
        y=sum(point.y for point in points) / count,
    )


def _nearest_other(
    anchor: Coordinates,
    placed: Mapping[str, Coordinates],
    exclude: frozenset[str],
) -> Coordinates | None:
    """The closest already-placed node that is not one of ``exclude``.

    This is what the offset moves away from, so it decides the direction.
    Candidates are walked in id order and compared with a strict ``<``, so
    two nodes at the same distance resolve to the one with the lower id
    rather than to whichever the mapping yields first.
    """
    best: Coordinates | None = None
    best_distance = math.inf
    for node_id in sorted(placed):
        if node_id in exclude:
            continue
        point = placed[node_id]
        distance = math.dist((anchor.x, anchor.y), (point.x, point.y))
        if distance < best_distance:
            best = point
            best_distance = distance
    return best


def _offset_direction(
    points: Sequence[Coordinates],
    anchor: Coordinates,
    reference: Coordinates | None,
) -> _Vector:
    """The unit vector the site is pushed along. See the module docstring."""
    axis = _attachment_axis(points)
    if axis is not None:
        # Perpendicular to the line through the attachments, so the site
        # stays equidistant from the two ends of that line.
        perpendicular = (-axis[1], axis[0])
        if reference is not None and _dot(perpendicular, _towards(reference, anchor)) < 0.0:
            return (-perpendicular[0], -perpendicular[1])
        return perpendicular

    # One attachment point, so the attachments themselves offer no
    # direction. Move away from whatever else is nearest instead.
    if reference is not None:
        away = _unit(_towards(reference, anchor))
        if away is not None:
            return away
    return _FALLBACK_DIRECTION


def _attachment_axis(points: Sequence[Coordinates]) -> _Vector | None:
    """The unit vector along the attachments, or ``None`` if they coincide.

    Taken from the first attachment to the first one that sits somewhere
    else, in file order. ``ParsedSite.attaches_to`` keeps file order for
    exactly this reason, so the axis does not depend on how the row was
    read.
    """
    for point in points[1:]:
        axis = _unit(_towards(points[0], point))
        if axis is not None:
            return axis
    return None


def _free_position(
    anchor: Coordinates,
    direction: _Vector,
    placed: Mapping[str, Coordinates],
) -> Coordinates:
    """``anchor`` offset along ``direction``, rotated until the spot is free.

    Each rotation is the golden angle, so the candidates are distinct
    directions at one radius and therefore distinct points. There are more
    candidates tried than there are nodes already placed, so one of them
    has to be free.
    """
    for attempt in range(len(placed) + 1):
        turned = _rotate(direction, attempt * _TIE_BREAK_ROTATION_RADIANS)
        candidate = Coordinates(
            x=anchor.x + SITE_OFFSET_DEGREES * turned[0],
            y=anchor.y + SITE_OFFSET_DEGREES * turned[1],
        )
        if not any(_is_coincident(candidate, taken) for taken in placed.values()):
            return candidate
    raise AssertionError("more candidate positions were tried than there are nodes to block them")


def _is_coincident(one: Coordinates, other: Coordinates) -> bool:
    return math.dist((one.x, one.y), (other.x, other.y)) <= _COINCIDENT_TOLERANCE_DEGREES


def _towards(origin: Coordinates, target: Coordinates) -> _Vector:
    return (target.x - origin.x, target.y - origin.y)


def _unit(vector: _Vector) -> _Vector | None:
    """``vector`` scaled to length one, or ``None`` if it has no length."""
    length = math.hypot(vector[0], vector[1])
    if length <= _COINCIDENT_TOLERANCE_DEGREES:
        return None
    return (vector[0] / length, vector[1] / length)


def _dot(one: _Vector, other: _Vector) -> float:
    return one[0] * other[0] + one[1] * other[1]


def _rotate(vector: _Vector, radians: float) -> _Vector:
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return (
        vector[0] * cosine - vector[1] * sine,
        vector[0] * sine + vector[1] * cosine,
    )
