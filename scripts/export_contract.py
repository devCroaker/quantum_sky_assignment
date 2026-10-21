"""Write the wire contract to contracts/schema.json.

The JSON Schema written here is what the front end generates its TypeScript
types from, so the two sides of the interface cannot drift by hand. Output is
sorted and indented, which makes a contract change show up as a readable diff
in review rather than as a reshuffled blob.

Run with: python scripts/export_contract.py
Check in CI with: python scripts/export_contract.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from netscope.api.schemas import (
    CriticalityResponse,
    ErrorResponse,
    NetworkResponse,
    ScenarioReport,
    ScenarioRequest,
)
from pydantic.json_schema import models_json_schema

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "contracts" / "schema.json"
API_VERSION = "v1"

# The five models that appear directly in a request or response body. Anything
# else reachable from them lands in $defs automatically.
TOP_LEVEL = (
    NetworkResponse,
    ScenarioRequest,
    ScenarioReport,
    CriticalityResponse,
    ErrorResponse,
)

ENDPOINTS = {
    "GET /api/v1/network": NetworkResponse.__name__,
    "GET /api/v1/analysis/baseline": ScenarioReport.__name__,
    "GET /api/v1/criticality": CriticalityResponse.__name__,
    "POST /api/v1/scenario": ScenarioRequest.__name__,
}


def build() -> dict[str, object]:
    _, defs = models_json_schema(
        [(model, "validation") for model in TOP_LEVEL],
        ref_template="#/$defs/{model}",
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "netscope API contract",
        "apiVersion": API_VERSION,
        "endpoints": ENDPOINTS,
        "responseBodies": {
            "GET /api/v1/network": f"#/$defs/{NetworkResponse.__name__}",
            "GET /api/v1/analysis/baseline": f"#/$defs/{ScenarioReport.__name__}",
            "GET /api/v1/criticality": f"#/$defs/{CriticalityResponse.__name__}",
            "POST /api/v1/scenario": f"#/$defs/{ScenarioReport.__name__}",
        },
        "errorBody": f"#/$defs/{ErrorResponse.__name__}",
        "$defs": defs["$defs"],
    }


def render() -> str:
    return json.dumps(build(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed file is out of date",
    )
    args = parser.parse_args()

    rendered = render()
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != rendered:
            print(
                f"{TARGET.relative_to(ROOT)} is out of date. "
                "Run: python scripts/export_contract.py",
                file=sys.stderr,
            )
            return 1
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(rendered, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
