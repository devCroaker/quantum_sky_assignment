"""Reader for ``sites.csv``, the invented site table.

The file has one row per site and a semicolon separated ``attaches_to``
column. Every value in that column becomes one access link at the row's
``access_capacity``, which is why nine rows yield fourteen access links.

This module parses and validates. It builds no ``Node`` and no ``Link``,
because an access link also names a backbone city and the set of backbone
city ids is not available here. P7 owns that merge, and keeping the merge out
of this module is what lets it depend on nothing but ``models`` and
``errors`` (the layering rule in CLAUDE.md).

Attachment targets are resolved by :func:`resolve`, separately and after the
whole file is read. ``OPS-EAST-1`` attaches to ``HUB-EAST``, which is a row
of this file rather than a backbone city, and nothing in the format fixes
the order of the two, so a target may be defined on a later row and no row
can be resolved in isolation. :func:`resolve` takes the known node ids as an
argument rather than importing the backbone loader, for the same layering
reason.

Every rejection is an :class:`~netscope.errors.InputError` naming the file
and the row, per R2. A broken model invariant is a ``ValueError`` from the
model layer instead, because that is a programming mistake and not a bad
input file. That split is D15.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from netscope.errors import InputError
from netscope.models import NodeKind

__all__ = ["HEADER", "ParsedSite", "load_sites", "resolve"]

#: The header this file must carry, in this order.
HEADER: tuple[str, ...] = ("site_id", "site_type", "attaches_to", "access_capacity")

#: Rows are numbered the way a spreadsheet numbers them: the header is row 1
#: and the first site, ``DC-NORTH``, is row 2. Error messages are read next
#: to the file in an editor, so an off-by-one here points every message at
#: the wrong line.
HEADER_ROW = 1
FIRST_DATA_ROW = 2

#: The three kinds a row of this file may declare. ``NodeKind`` also has
#: ``BACKBONE_CITY``, which is deliberately absent: cities come from the
#: SNDlib file, so naming one in the ``site_type`` column is an error rather
#: than a way to add a city.
SITE_KINDS: frozenset[NodeKind] = frozenset(
    {NodeKind.DATA_CENTER, NodeKind.OPERATIONS_SITE, NodeKind.AGGREGATION_HUB}
)

#: The file name used by :func:`resolve`, which is handed parsed rows rather
#: than a path and so cannot recover the one they came from. This loader
#: reads exactly one file, so naming it is honest, and it keeps the signature
#: free of a path that the caller would have to carry around.
RESOLVE_FILE_LABEL = "sites.csv"

ATTACHMENT_SEPARATOR = ";"


@dataclass(frozen=True, slots=True)
class ParsedSite:
    """One validated row, not yet a ``Node``.

    ``attaches_to`` keeps file order because the deterministic placement in
    P8 derives a site's position from its attachment points, and a stable
    order is what makes that placement reproducible.
    """

    site_id: str
    kind: NodeKind
    attaches_to: tuple[str, ...]
    access_capacity: float
    row: int


def load_sites(path: Path) -> tuple[ParsedSite, ...]:
    """Parse and validate every row of ``path``.

    Raises :class:`InputError` on the first problem found, naming the file
    and the row, and the column when one column is at fault.
    """
    label = str(path)
    if not path.is_file():
        raise InputError(label, "file does not exist")

    with path.open(newline="", encoding="utf-8") as handle:
        records = list(csv.reader(handle))

    if not records:
        raise InputError(label, "file is empty, expected a header row", row=HEADER_ROW)

    _check_header(label, records[0])

    sites: list[ParsedSite] = []
    seen: dict[str, int] = {}
    for offset, record in enumerate(records[1:]):
        row = FIRST_DATA_ROW + offset
        site = _parse_row(label, row, record)
        if site.site_id in seen:
            raise InputError(
                label,
                f"duplicate site_id {site.site_id!r}, already used on row {seen[site.site_id]}",
                row=row,
                field="site_id",
            )
        seen[site.site_id] = row
        sites.append(site)

    if not sites:
        raise InputError(label, "no data rows, only a header", row=HEADER_ROW)

    return tuple(sites)


def resolve(sites: tuple[ParsedSite, ...], known_node_ids: frozenset[str]) -> None:
    """Check that every attachment target exists.

    A target is either a backbone city id, supplied in ``known_node_ids``, or
    another row's ``site_id``. Forward references are legal, so this runs
    once over the whole table rather than row by row.
    """
    site_ids = {site.site_id for site in sites}
    for site in sites:
        for target in site.attaches_to:
            if target not in known_node_ids and target not in site_ids:
                raise InputError(
                    RESOLVE_FILE_LABEL,
                    f"site {site.site_id!r} attaches to unknown target {target!r}, "
                    "which is neither a backbone node nor another site",
                    row=site.row,
                    field="attaches_to",
                )


def _check_header(label: str, record: list[str]) -> None:
    found = tuple(cell.strip() for cell in record)
    if found != HEADER:
        raise InputError(
            label,
            f"header must be exactly {','.join(HEADER)}, found {','.join(found)}",
            row=HEADER_ROW,
        )


def _parse_row(label: str, row: int, record: list[str]) -> ParsedSite:
    if not record or not any(cell.strip() for cell in record):
        raise InputError(label, "blank row", row=row)
    if len(record) != len(HEADER):
        raise InputError(
            label,
            f"expected {len(HEADER)} fields, found {len(record)}",
            row=row,
        )

    site_id, site_type, attaches_to, access_capacity = (cell.strip() for cell in record)
    return ParsedSite(
        site_id=_parse_site_id(label, row, site_id),
        kind=_parse_kind(label, row, site_type),
        attaches_to=_parse_attachments(label, row, site_id, attaches_to),
        access_capacity=_parse_capacity(label, row, access_capacity),
        row=row,
    )


def _parse_site_id(label: str, row: int, value: str) -> str:
    if not value:
        raise InputError(label, "site_id is missing or blank", row=row, field="site_id")
    return value


def _parse_kind(label: str, row: int, value: str) -> NodeKind:
    if not value:
        raise InputError(label, "site_type is missing or blank", row=row, field="site_type")
    # The column's vocabulary matches the enum values exactly, so NodeKind
    # does the parsing. Matching against SITE_KINDS rather than the whole
    # enum is what rejects "backbone-city": it is a real NodeKind, but
    # cities come from the backbone file and this column may not declare one.
    permitted = {kind.value: kind for kind in SITE_KINDS}
    if value not in permitted:
        raise InputError(
            label,
            f"site_type {value!r} is not one of {', '.join(sorted(permitted))}",
            row=row,
            field="site_type",
        )
    return permitted[value]


def _parse_capacity(label: str, row: int, value: str) -> float:
    if not value:
        raise InputError(
            label,
            "access_capacity is missing or blank",
            row=row,
            field="access_capacity",
        )
    try:
        capacity = float(value)
    except ValueError:
        raise InputError(
            label,
            f"access_capacity {value!r} is not a number",
            row=row,
            field="access_capacity",
        ) from None
    if not math.isfinite(capacity) or capacity <= 0:
        raise InputError(
            label,
            f"access_capacity must be positive, found {value!r}",
            row=row,
            field="access_capacity",
        )
    return capacity


def _parse_attachments(label: str, row: int, site_id: str, value: str) -> tuple[str, ...]:
    if not value:
        raise InputError(
            label,
            "attaches_to is empty, every site needs at least one attachment",
            row=row,
            field="attaches_to",
        )

    targets = [part.strip() for part in value.split(ATTACHMENT_SEPARATOR)]
    if not all(targets):
        raise InputError(
            label,
            f"attaches_to {value!r} has a blank entry",
            row=row,
            field="attaches_to",
        )

    seen: set[str] = set()
    for target in targets:
        if target == site_id:
            raise InputError(
                label,
                f"site {site_id!r} attaches to itself",
                row=row,
                field="attaches_to",
            )
        if target in seen:
            # Two identical targets in one row would ask P7 for the same
            # access link twice.
            raise InputError(
                label,
                f"attaches_to names {target!r} twice",
                row=row,
                field="attaches_to",
            )
        seen.add(target)

    return tuple(targets)
