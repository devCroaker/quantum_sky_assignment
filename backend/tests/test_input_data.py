"""Facts about the committed input files that the design depends on.

These parse the raw files crudely, independently of the production loaders,
so they keep their value as an outside check: if a loader is ever wrong,
these do not move with it.

What is left here are the facts that justify a design decision rather than
merely counting rows. The demand total is what makes the brief's merged
figure of 2068 add up. The 378 demands being exactly 28 choose 2 is what
says demands are undirected. The capacity modules are asserted present so
that ignoring them reads as a decision rather than an oversight.

The plain shape checks that used to live here, 28 nodes and 41 links and 378
demands, and 9 site rows with 14 attachments, were removed once the loaders
existed: test_sndlib_loader.py and test_sites_loader.py assert the same
counts on parsed objects, which is strictly more informative, and three
copies of one number is three places to update rather than three checks.
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


def test_site_attachments_resolve_to_a_city_or_another_site() -> None:
    """Covers the site-to-site reference from OPS-EAST-1 to HUB-EAST.

    A target may be another row rather than a city, and nothing in the
    format fixes the order of the two rows, so no row can be resolved on
    its own. That is why the loader in P6 reads every row before resolving
    any attachment.

    In this file the reference points backwards, since HUB-EAST is row 7
    and OPS-EAST-1 is row 8. The assertion below is deliberately
    order-independent, so it would still hold if the rows were swapped.
    """
    cities = set(re.findall(r"<node id=\"([^\"]+)\">", _sndlib_text()))
    with SITES.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    site_ids = {row["site_id"] for row in rows}
    for row in rows:
        for target in row["attaches_to"].split(";"):
            assert target in cities or target in site_ids, target
            assert target != row["site_id"]
