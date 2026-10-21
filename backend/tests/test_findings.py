"""Guards against editing the findings generator and forgetting to regenerate.

Mirrors ``test_committed_schema_is_up_to_date`` in ``test_api_contract.py``:
the committed ``docs/findings.md`` is generated output, not hand-written
prose, so the only thing worth asserting here is that it is still exactly
what ``scripts/findings.py`` would produce from the committed input files
today.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_committed_findings_report_is_up_to_date() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "findings.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_warsaw_paragraph_names_the_site_that_actually_loses_traffic() -> None:
    """Regression test for a misattribution caught by an independent review.

    An earlier version of this paragraph said "the hub's own demands have no
    legal path," attributing the two stranded demands to HUB-EAST. That is
    wrong: HUB-EAST is an aggregation hub, and R4 gives synthetic demands
    only to operations sites and data centers, so HUB-EAST originates none
    of its own. The two demands that actually die when Warsaw fails are
    OPS-EAST-1's, to each data center.

    This asserts the identity of the stranded demands directly against the
    router, not just their count, which is what the previous version of this
    test would not have caught: the count and the unit total were both
    already correct, only the attribution in the prose was wrong.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from findings import _warsaw_paragraph

    from netscope.analysis import analyse
    from netscope.criticality import sweep
    from netscope.loaders.merge import build_network
    from netscope.loaders.sites_csv import load_sites
    from netscope.loaders.sndlib_xml import load_backbone

    network = build_network(
        load_backbone(ROOT / "data" / "nobel-eu.xml"),
        load_sites(ROOT / "data" / "sites.csv"),
        sites_file=str(ROOT / "data" / "sites.csv"),
    )
    scenario = analyse(network, failed_nodes=frozenset({"Warsaw"}))

    # The real assertion: OPS-EAST-1 is a party to every stranded demand,
    # and HUB-EAST is a party to none, which is the exact fact the original
    # wording got backwards.
    stranded_sites = {
        site
        for demand in scenario.undeliverable
        for site in (demand.endpoints.a, demand.endpoints.b)
    } - {"Warsaw"}
    assert all("OPS-EAST-1" in (d.endpoints.a, d.endpoints.b) for d in scenario.undeliverable)
    assert "HUB-EAST" not in stranded_sites

    report = _warsaw_paragraph(sweep(network).assessments, network)
    assert "OPS-EAST-1" in report
    assert "the hub's own" not in report
