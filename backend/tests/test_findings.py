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
