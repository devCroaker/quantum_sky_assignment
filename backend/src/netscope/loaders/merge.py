"""Merge the two parsed inputs into one ``Network`` (R1, R3, R4).

This is the only place that sees both files at once, which is why three
things that cannot be decided by either loader alone are decided here.

**Capacities (R3).** Every backbone link is set to ``BACKBONE_CAPACITY``,
550 units. There is nothing to ignore while doing it: ``ParsedLink`` has no
capacity field, so the SNDlib capacity modules never reach this module. Each
value in a row's ``attaches_to`` becomes one access link carrying that row's
``access_capacity``.

**The synthetic demands (R4).** Each operations site sends
``OPS_TO_DATA_CENTER_UNITS`` to each data center, and the two data centers
exchange ``DATA_CENTER_PAIR_UNITS``. Both site lists are derived from
``ParsedSite.kind`` and never from a list of names, so ``HUB-EAST`` is left
out by being an aggregation hub rather than by being spelled out. Nothing
here assumes how many sites of either kind there are, except in the one
place R4 itself does: the data center pair demand needs exactly two data
centers, and anything else is rejected rather than guessed at.

**Site coordinates.** ``Node`` requires a position and the site table has
none, so every site is positioned by ``geometry.place_sites``, which
resolves the attachments in dependency order and rejects a circular chain.
The rule itself lives there and not here, because it is geometry rather
than merging. See D9 and D22.

**Validation (R2).** Attachment targets are checked by
``sites_csv.resolve``. Beyond that this module rejects a ``site_id`` that
redefines a backbone city, an access link that duplicates a link the network
already has, and the data center count problems above. Every rejection is an
``InputError`` naming ``sites_file`` and, where a single row is responsible,
that row.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from netscope.errors import InputError
from netscope.loaders import geometry, sites_csv
from netscope.loaders.sites_csv import ParsedSite
from netscope.loaders.sndlib_xml import ParsedBackbone
from netscope.models import (
    Demand,
    Endpoints,
    Link,
    LinkKind,
    Network,
    Node,
    NodeKind,
)

__all__ = [
    "BACKBONE_CAPACITY",
    "DATA_CENTER_PAIR_UNITS",
    "OPS_TO_DATA_CENTER_UNITS",
    "build_network",
]

#: R3: every backbone link carries this, whatever the file's modules say.
BACKBONE_CAPACITY = 550.0

#: R4: what one operations site sends to one data center.
OPS_TO_DATA_CENTER_UNITS = 10.0

#: R4: what the two data centers exchange with each other.
DATA_CENTER_PAIR_UNITS = 50.0

#: Access link ids are synthesized as ``ACC-<site_id>-<target>``, for
#: example ``ACC-DC-NORTH-Hamburg``. The committed contract fixtures under
#: ``contracts/fixtures/`` already use that spelling, so it is fixed.
ACCESS_LINK_PREFIX = "ACC"

#: Synthetic demand ids are ``SYN-<a>-<b>`` with the endpoints in sorted
#: order, for example ``SYN-DC-NORTH-OPS-WEST``. The prefix keeps them clear
#: of file A's ids, which are a concatenation of two city names such as
#: ``AmsterdamAthens`` and so can never begin with ``SYN-``.
SYNTHETIC_DEMAND_PREFIX = "SYN"

#: R4 describes the data center pair demand for a pair, so exactly two.
DATA_CENTERS_REQUIRED = 2


def build_network(
    backbone: ParsedBackbone,
    sites: tuple[ParsedSite, ...],
    *,
    sites_file: str,
    backbone_capacity: float = BACKBONE_CAPACITY,
) -> Network:
    """Build the one merged ``Network`` the rest of the application reads.

    Args:
        backbone: file A as parsed by ``sndlib_xml.load_backbone``.
        sites: file B as parsed by ``sites_csv.load_sites``.
        sites_file: the path the rows came from, named in every rejection a
            row is responsible for. It is passed in rather than inferred for
            the reason ``sites_csv.resolve`` gives: an error about a test
            fixture must not claim to be about the real input.
        backbone_capacity: units on every backbone link. Defaults to the 550
            that R3 fixes, and exists as a parameter so that the documented
            NETSCOPE_BACKBONE_CAPACITY setting actually reaches the merge.
            A configuration value that silently does nothing is worse than no
            setting at all, because a reader believes it works.

    Raises:
        InputError: if the two files cannot be combined, naming
            ``sites_file`` and the offending row.
    """
    city_ids = frozenset(node.id for node in backbone.nodes)

    # Before anything else, because every later check works with a single id
    # space. A site sharing a city's id would make "Hamburg" name two nodes,
    # and resolve() could not tell the two apart: it would happily accept an
    # attachment to the city while the merge quietly redefined it.
    _reject_city_id_collisions(sites, city_ids, sites_file)
    sites_csv.resolve(sites, city_ids, sites_file)

    data_centers = _sites_of_kind(sites, NodeKind.DATA_CENTER)
    _check_data_center_count(data_centers, sites_file)

    # Links before placement: both can fail, and a duplicated access link is
    # a fact about the rows themselves, so reporting it is more use than
    # reporting whatever the geometry pass happens to trip over first.
    links = _build_links(backbone, sites, sites_file, backbone_capacity)
    positions = geometry.place_sites(
        sites,
        {node.id: node.coordinates for node in backbone.nodes},
        sites_file=sites_file,
    )

    nodes: dict[str, Node] = {node.id: node for node in backbone.nodes}
    for site in sites:
        nodes[site.site_id] = Node(
            id=site.site_id,
            kind=site.kind,
            coordinates=positions[site.site_id],
        )

    return Network(
        nodes=nodes,
        links=links,
        demands=_build_demands(backbone, sites, data_centers),
    )


# --------------------------------------------------------------------------
# Validation that needs both files
# --------------------------------------------------------------------------


def _reject_city_id_collisions(
    sites: Sequence[ParsedSite], city_ids: frozenset[str], sites_file: str
) -> None:
    for site in sites:
        if site.site_id in city_ids:
            raise InputError(
                sites_file,
                f"site_id {site.site_id!r} is already a backbone city, "
                "which this row would silently redefine",
                row=site.row,
                field="site_id",
            )


def _check_data_center_count(data_centers: Sequence[ParsedSite], sites_file: str) -> None:
    """R4's pair demand is only defined for exactly two data centers."""
    if len(data_centers) < DATA_CENTERS_REQUIRED:
        # No row to point at: the shortage is a property of the table as a
        # whole, not of any one row that is present.
        raise InputError(
            sites_file,
            f"declares {len(data_centers)} data centers, but R4 gives the two data "
            "centers a demand with each other, which needs at least "
            f"{DATA_CENTERS_REQUIRED}",
        )
    if len(data_centers) > DATA_CENTERS_REQUIRED:
        # Point at the first row beyond the pair, which is the row that makes
        # the rule ambiguous.
        surplus = data_centers[DATA_CENTERS_REQUIRED]
        raise InputError(
            sites_file,
            f"declares {len(data_centers)} data centers, but the R4 rule is written "
            f"for exactly {DATA_CENTERS_REQUIRED}, so the pair that exchanges "
            f"{DATA_CENTER_PAIR_UNITS:g} units is undefined",
            row=surplus.row,
            field="site_type",
        )


def _sites_of_kind(sites: Sequence[ParsedSite], kind: NodeKind) -> tuple[ParsedSite, ...]:
    """The rows of one kind, in file order.

    Derived from ``kind`` rather than from any list of names, so R4 follows
    the site table and not a constant that could drift away from it.
    """
    return tuple(site for site in sites if site.kind is kind)


# --------------------------------------------------------------------------
# Links (R3)
# --------------------------------------------------------------------------


def _build_links(
    backbone: ParsedBackbone,
    sites: Sequence[ParsedSite],
    sites_file: str,
    backbone_capacity: float,
) -> Mapping[str, Link]:
    links: dict[str, Link] = {}
    # Endpoints sorts its own pair, so a reversed duplicate lands on the same
    # key and one mapping catches every repeat.
    owner_of_pair: dict[Endpoints, str] = {}

    for parsed in backbone.links:
        links[parsed.id] = Link(
            id=parsed.id,
            endpoints=parsed.endpoints,
            capacity=backbone_capacity,
            kind=LinkKind.BACKBONE,
        )
        owner_of_pair[parsed.endpoints] = parsed.id

    for site in sites:
        for target in site.attaches_to:
            endpoints = Endpoints(site.site_id, target)
            link_id = f"{ACCESS_LINK_PREFIX}-{site.site_id}-{target}"
            existing_pair = owner_of_pair.get(endpoints)
            if existing_pair is not None:
                raise InputError(
                    sites_file,
                    f"access link {link_id!r} joins {endpoints}, which link "
                    f"{existing_pair!r} already joins",
                    row=site.row,
                    field="attaches_to",
                )
            if link_id in links:
                raise InputError(
                    sites_file,
                    f"access link id {link_id!r} is already taken by another link",
                    row=site.row,
                    field="attaches_to",
                )
            links[link_id] = Link(
                id=link_id,
                endpoints=endpoints,
                capacity=site.access_capacity,
                kind=LinkKind.ACCESS,
            )
            owner_of_pair[endpoints] = link_id

    return links


# --------------------------------------------------------------------------
# Demands (R4)
# --------------------------------------------------------------------------


def _build_demands(
    backbone: ParsedBackbone,
    sites: Sequence[ParsedSite],
    data_centers: Sequence[ParsedSite],
) -> tuple[Demand, ...]:
    demands: list[Demand] = list(backbone.demands)

    for operations in _sites_of_kind(sites, NodeKind.OPERATIONS_SITE):
        for data_center in data_centers:
            demands.append(
                _synthetic_demand(operations.site_id, data_center.site_id, OPS_TO_DATA_CENTER_UNITS)
            )

    # The count was checked above, so there is a pair here and not a guess.
    demands.append(
        _synthetic_demand(data_centers[0].site_id, data_centers[1].site_id, DATA_CENTER_PAIR_UNITS)
    )
    return tuple(demands)


def _synthetic_demand(one_end: str, other_end: str, volume: float) -> Demand:
    """One R4 demand, with an id that does not depend on argument order.

    ``Endpoints`` has already sorted the pair, so reading the id off it is
    what makes ``SYN-DC-NORTH-OPS-WEST`` the id whichever way round the two
    site lists are walked.
    """
    endpoints = Endpoints(one_end, other_end)
    return Demand(
        id=f"{SYNTHETIC_DEMAND_PREFIX}-{endpoints.a}-{endpoints.b}",
        endpoints=endpoints,
        volume=volume,
    )
