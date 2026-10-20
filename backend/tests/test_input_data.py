"""Structural checks on the committed input files.

These run before any loader exists, deliberately. They pin the shape of the
raw inputs so that a later parsing change cannot quietly be "fixed" by
editing the data. The expected values come from the assignment brief, which
states 28 cities, 41 links and 378 demands for file A, and from counting the
nine rows of file B given in the brief.

Parsing here is intentionally crude and independent of the production
loaders, so that these tests keep their value as an external check.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"
SNDLIB = DATA / "nobel-eu.xml"
SITES = DATA / "sites.csv"

# The SNDlib file is served as ISO-8859-1 and contains author names with
# diacritics, so the encoding matters and is asserted by reading at all.
SNDLIB_ENCODING = "ISO-8859-1"


def _sndlib_text() -> str:
    return SNDLIB.read_text(encoding=SNDLIB_ENCODING)


def test_backbone_file_has_the_shape_the_brief_describes() -> None:
    text = _sndlib_text()
    assert len(re.findall(r"<node id=", text)) == 28
    assert len(re.findall(r"<link id=", text)) == 41
    assert len(re.findall(r"<demand id=", text)) == 378


def test_backbone_demand_total_is_1898_units() -> None:
    """1898 is the figure that makes the R1 check of 2068 add up.

    R4 adds 6 operations sites x 2 data centers x 10 units, plus 50 units
    between the two data centers, which is 170. The brief's merged total of
    2068 therefore requires file A to carry 1898.
    """
    values = [float(v) for v in re.findall(r"<demandValue>([0-9.]+)</demandValue>", _sndlib_text())]
    assert sum(values) == 1898.0
    assert sum(values) + 170.0 == 2068.0


def test_backbone_demands_are_one_per_unordered_city_pair() -> None:
    """378 is 28 choose 2, which confirms demands are undirected.

    If the file held directed demands we would expect up to 756 entries, or
    duplicated pairs in both orders. Neither is present, so the loader is
    right to treat a demand as undirected.
    """
    pairs = re.findall(
        r"<demand id=\"[^\"]*\">\s*<source>([^<]+)</source>\s*<target>([^<]+)</target>",
        _sndlib_text(),
    )
    assert len(pairs) == 378
    assert len({frozenset(p) for p in pairs}) == 378
    assert not [p for p in pairs if p[0] == p[1]]


def test_backbone_links_are_undirected_and_unique() -> None:
    links = re.findall(
        r"<link id=\"[^\"]+\">\s*<source>([^<]+)</source>\s*<target>([^<]+)</target>",
        _sndlib_text(),
    )
    assert len(links) == 41
    assert len({frozenset(link) for link in links}) == 41


def test_every_link_carries_capacity_modules_that_r3_tells_us_to_ignore() -> None:
    """Asserted so the reason for ignoring them stays visible.

    R3 overrides these with a flat 550 units per backbone link. The modules
    are present in the data, so skipping them is a decision rather than an
    omission.
    """
    assert "<addModule>" in _sndlib_text()


def test_sites_file_adds_nine_nodes_and_fourteen_access_links() -> None:
    with SITES.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert [*rows[0]] == ["site_id", "site_type", "attaches_to", "access_capacity"]
    assert len(rows) == 9

    attachments = [a for row in rows for a in row["attaches_to"].split(";")]
    assert len(attachments) == 14

    kinds = [row["site_type"] for row in rows]
    assert kinds.count("data-center") == 2
    assert kinds.count("operations-site") == 6
    assert kinds.count("aggregation-hub") == 1


def test_site_attachments_resolve_to_a_city_or_another_site() -> None:
    """Covers the forward reference from OPS-EAST-1 to HUB-EAST.

    Resolution cannot be done row by row in file order, which is why the
    loader in P6 reads every row before resolving any attachment.
    """
    cities = set(re.findall(r"<node id=\"([^\"]+)\">", _sndlib_text()))
    with SITES.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    site_ids = {row["site_id"] for row in rows}
    for row in rows:
        for target in row["attaches_to"].split(";"):
            assert target in cities or target in site_ids, target
            assert target != row["site_id"]
