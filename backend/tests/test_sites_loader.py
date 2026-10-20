"""Tests for the ``sites.csv`` loader.

Two halves. The first parses the real committed file and pins the figures
the brief states: nine rows, fourteen attachment values, and a type split of
two data centers, six operations sites and one aggregation hub. The second is
a table of malformed one-off fixtures written under ``tmp_path``, one per
validation rule, each asserting that the message names the file, the row and
the column where a single column is at fault.

Row numbering is asserted explicitly, because every message in the second
half is only useful if the header is row 1 and the first site is row 2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from netscope.errors import InputError
from netscope.loaders.sites_csv import HEADER, ParsedSite, load_sites, resolve
from netscope.models import NodeKind

DATA = Path(__file__).resolve().parents[2] / "data"
SITES = DATA / "sites.csv"
SNDLIB = DATA / "nobel-eu.xml"

# The SNDlib file is served as ISO-8859-1, as test_input_data.py records.
SNDLIB_ENCODING = "ISO-8859-1"


def _backbone_node_ids() -> frozenset[str]:
    """City ids scraped from the XML, independently of the P5 loader.

    Reading the file with a regular expression here keeps this test suite
    from depending on the other loader, which is being written in parallel.
    """
    text = SNDLIB.read_text(encoding=SNDLIB_ENCODING)
    return frozenset(re.findall(r'<node id="([^"]+)">', text))


# --------------------------------------------------------------------------
# The real file
# --------------------------------------------------------------------------


def test_real_file_yields_nine_sites_and_fourteen_attachments() -> None:
    """9 and 14 are the figures in the brief and in data/PROVENANCE.md.

    Each attachment value becomes one access link, so 14 is also the access
    link count P7 has to produce.
    """
    sites = load_sites(SITES)
    assert len(sites) == 9
    assert sum(len(site.attaches_to) for site in sites) == 14


def test_real_file_has_the_type_split_the_brief_states() -> None:
    """Two data centers, six operations sites, one aggregation hub."""
    kinds = [site.kind for site in load_sites(SITES)]
    assert kinds.count(NodeKind.DATA_CENTER) == 2
    assert kinds.count(NodeKind.OPERATIONS_SITE) == 6
    assert kinds.count(NodeKind.AGGREGATION_HUB) == 1


def test_first_row_parses_whole_and_is_row_two() -> None:
    """The full parse of the first data row, copied from the file.

    Row 2 is the point of this test as much as the values are. The header is
    row 1 the way a spreadsheet counts, so an error on DC-NORTH must say row
    2, and the attachment order must be the file's order because P8 derives
    placement from it.
    """
    first = load_sites(SITES)[0]
    assert first == ParsedSite(
        site_id="DC-NORTH",
        kind=NodeKind.DATA_CENTER,
        attaches_to=("Hamburg", "Copenhagen"),
        access_capacity=200.0,
        row=2,
    )


def test_rows_are_numbered_from_two_consecutively() -> None:
    """Nine data rows occupy spreadsheet rows 2 through 10."""
    assert [site.row for site in load_sites(SITES)] == list(range(2, 11))


def test_hub_east_is_the_only_transit_capable_site() -> None:
    """R6 hangs on this distinction and HUB-EAST is the only hub.

    An operations site that could forward traffic would let OPS-EAST-2 carry
    transit between HUB-EAST and Budapest, which R6 forbids.
    """
    by_id = {site.site_id: site for site in load_sites(SITES)}
    assert by_id["HUB-EAST"].kind is NodeKind.AGGREGATION_HUB
    assert NodeKind.AGGREGATION_HUB.can_transit
    assert not NodeKind.OPERATIONS_SITE.can_transit


def test_resolve_accepts_the_real_file_against_the_real_backbone() -> None:
    resolve(load_sites(SITES), _backbone_node_ids())


def test_resolve_accepts_the_reference_from_ops_east_1_to_hub_east() -> None:
    """OPS-EAST-1 attaches to HUB-EAST, another row rather than a city.

    In the committed file HUB-EAST is row 7 and OPS-EAST-1 is row 8, so that
    reference happens to point backwards. Nothing in the format guarantees
    the order, which is why resolution runs over the whole table once every
    row is read: the same two rows handed over in the opposite order, a
    genuine forward reference, must resolve just as well. The only backbone
    id supplied is Warsaw, the city HUB-EAST itself attaches to, so nothing
    but the other row can satisfy the HUB-EAST target.
    """
    sites = load_sites(SITES)
    ops_east_1 = next(site for site in sites if site.site_id == "OPS-EAST-1")
    hub_east = next(site for site in sites if site.site_id == "HUB-EAST")
    assert ops_east_1.attaches_to == ("HUB-EAST",)
    assert hub_east.attaches_to == ("Warsaw",)
    assert (hub_east.row, ops_east_1.row) == (7, 8)
    resolve((hub_east, ops_east_1), frozenset({"Warsaw"}))
    resolve((ops_east_1, hub_east), frozenset({"Warsaw"}))


def test_resolve_rejects_an_unknown_target_naming_the_row() -> None:
    sites = (
        ParsedSite(
            site_id="OPS-NOWHERE",
            kind=NodeKind.OPERATIONS_SITE,
            attaches_to=("Atlantis",),
            access_capacity=40.0,
            row=4,
        ),
    )
    with pytest.raises(InputError) as caught:
        resolve(sites, _backbone_node_ids())
    assert caught.value.row == 4
    assert caught.value.field == "attaches_to"
    assert "sites.csv" in str(caught.value)
    assert "Atlantis" in str(caught.value)


# --------------------------------------------------------------------------
# Malformed input, one fixture per rule
# --------------------------------------------------------------------------

GOOD_HEADER = ",".join(HEADER)
GOOD_ROW = "DC-NORTH,data-center,Hamburg;Copenhagen,200"


@dataclass(frozen=True)
class Case:
    """One malformed fixture and what the error must say about it."""

    name: str
    content: str
    row: int | None
    field: str | None
    fragment: str


CASES: tuple[Case, ...] = (
    Case(
        name="empty_file",
        content="",
        # The header belongs on row 1, so that is where it is missing from.
        row=1,
        field=None,
        fragment="empty",
    ),
    Case(
        name="header_only",
        content=f"{GOOD_HEADER}\n",
        row=1,
        field=None,
        fragment="no data rows",
    ),
    Case(
        name="header_misspelled",
        content=f"site_id,site_types,attaches_to,access_capacity\n{GOOD_ROW}\n",
        row=1,
        field=None,
        fragment="header",
    ),
    Case(
        name="header_reordered",
        content=f"site_type,site_id,attaches_to,access_capacity\n{GOOD_ROW}\n",
        row=1,
        field=None,
        fragment="header",
    ),
    Case(
        name="header_extra_column",
        content=f"{GOOD_HEADER},notes\n{GOOD_ROW},x\n",
        row=1,
        field=None,
        fragment="header",
    ),
    Case(
        name="header_missing_column",
        content="site_id,site_type,attaches_to\nDC-NORTH,data-center,Hamburg\n",
        row=1,
        field=None,
        fragment="header",
    ),
    Case(
        name="too_few_fields",
        content=f"{GOOD_HEADER}\nDC-NORTH,data-center,Hamburg\n",
        row=2,
        field=None,
        fragment="expected 4 fields",
    ),
    Case(
        name="too_many_fields",
        content=f"{GOOD_HEADER}\n{GOOD_ROW},extra\n",
        row=2,
        field=None,
        fragment="expected 4 fields",
    ),
    Case(
        name="blank_row_between_rows",
        # csv yields a zero-field record here, so it cannot be reported as a
        # field count problem without a misleading message.
        content=f"{GOOD_HEADER}\n{GOOD_ROW}\n\nDC-SOUTH,data-center,Milan,200\n",
        row=3,
        field=None,
        fragment="blank row",
    ),
    Case(
        name="blank_site_id",
        content=f"{GOOD_HEADER}\n,data-center,Hamburg,200\n",
        row=2,
        field="site_id",
        fragment="site_id",
    ),
    Case(
        name="duplicate_site_id",
        # The duplicate is reported on row 3, where it is found, and the
        # message points back at row 2 where the id was first used.
        content=f"{GOOD_HEADER}\n{GOOD_ROW}\nDC-NORTH,data-center,Milan,200\n",
        row=3,
        field="site_id",
        fragment="duplicate site_id",
    ),
    Case(
        name="unknown_site_type",
        content=f"{GOOD_HEADER}\nDC-NORTH,warehouse,Hamburg,200\n",
        row=2,
        field="site_type",
        fragment="warehouse",
    ),
    Case(
        name="backbone_city_site_type",
        # backbone-city is a valid NodeKind but not valid here: cities come
        # from the SNDlib file, never from this one.
        content=f"{GOOD_HEADER}\nDC-NORTH,backbone-city,Hamburg,200\n",
        row=2,
        field="site_type",
        fragment="backbone-city",
    ),
    Case(
        name="blank_capacity",
        content=f"{GOOD_HEADER}\nDC-NORTH,data-center,Hamburg,\n",
        row=2,
        field="access_capacity",
        fragment="access_capacity",
    ),
    Case(
        name="non_numeric_capacity",
        content=f"{GOOD_HEADER}\nDC-NORTH,data-center,Hamburg,lots\n",
        row=2,
        field="access_capacity",
        fragment="not a number",
    ),
    Case(
        name="zero_capacity",
        content=f"{GOOD_HEADER}\nDC-NORTH,data-center,Hamburg,0\n",
        row=2,
        field="access_capacity",
        fragment="positive",
    ),
    Case(
        name="negative_capacity",
        content=f"{GOOD_HEADER}\nDC-NORTH,data-center,Hamburg,-40\n",
        row=2,
        field="access_capacity",
        fragment="positive",
    ),
    Case(
        name="empty_attaches_to",
        content=f"{GOOD_HEADER}\nDC-NORTH,data-center,,200\n",
        row=2,
        field="attaches_to",
        fragment="attaches_to",
    ),
    Case(
        name="blank_attachment_entry",
        content=f"{GOOD_HEADER}\nDC-NORTH,data-center,Hamburg;,200\n",
        row=2,
        field="attaches_to",
        fragment="blank entry",
    ),
    Case(
        name="self_attachment",
        content=f"{GOOD_HEADER}\nDC-NORTH,data-center,Hamburg;DC-NORTH,200\n",
        row=2,
        field="attaches_to",
        fragment="attaches to itself",
    ),
    Case(
        name="duplicate_attachment",
        # Two identical targets would ask P7 for the same access link twice.
        content=f"{GOOD_HEADER}\nDC-NORTH,data-center,Hamburg;Hamburg,200\n",
        row=2,
        field="attaches_to",
        fragment="twice",
    ),
)


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_malformed_input_is_rejected_with_file_row_and_column(case: Case, tmp_path: Path) -> None:
    path = tmp_path / "sites.csv"
    path.write_text(case.content, encoding="utf-8")

    with pytest.raises(InputError) as caught:
        load_sites(path)

    error = caught.value
    rendered = str(error)
    assert path.name in rendered
    assert error.row == case.row
    assert f"row {case.row}" in rendered
    assert error.field == case.field
    if case.field is not None:
        assert f"column {case.field!r}" in rendered
    assert case.fragment in rendered


def test_missing_file_is_rejected_naming_the_file(tmp_path: Path) -> None:
    """A file that is not there has no row to name, so none is given."""
    missing = tmp_path / "sites.csv"
    with pytest.raises(InputError) as caught:
        load_sites(missing)
    assert caught.value.row is None
    assert "sites.csv" in str(caught.value)


def test_fields_are_stripped_of_surrounding_whitespace(tmp_path: Path) -> None:
    """Whitespace around a value is formatting, not content.

    Accepting it keeps a hand-edited file working, and the blank checks run
    after stripping, so a field of only spaces is still rejected.
    """
    path = tmp_path / "sites.csv"
    path.write_text(
        f"{GOOD_HEADER}\n  DC-NORTH , data-center , Hamburg ; Copenhagen , 200 \n",
        encoding="utf-8",
    )
    (site,) = load_sites(path)
    assert site.site_id == "DC-NORTH"
    assert site.attaches_to == ("Hamburg", "Copenhagen")
    assert site.access_capacity == 200.0
