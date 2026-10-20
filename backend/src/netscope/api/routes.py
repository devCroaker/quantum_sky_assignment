"""``GET /api/v1/network`` and ``GET /api/v1/analysis/baseline`` (P13).

P14 adds ``GET /api/v1/criticality`` and ``POST /api/v1/scenario`` to this
same router. Nothing here is written specifically for these two endpoints
beyond the paths themselves: both bodies come straight from
:class:`~netscope.api.state.AppState`, which :func:`~netscope.api.state.build_state`
computed once at startup, so a request never touches the routing or analysis
code at all.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from netscope.api.schemas import NetworkResponse, ScenarioReport
from netscope.api.state import get_state

__all__ = ["router"]

router = APIRouter(prefix="/api/v1")


@router.get("/network", response_model=NetworkResponse)
async def get_network(request: Request) -> NetworkResponse:
    """The topology and the R1 totals, served from the startup cache."""
    return get_state(request).network_response


@router.get("/analysis/baseline", response_model=ScenarioReport)
async def get_baseline(request: Request) -> ScenarioReport:
    """The baseline scenario report: the empty failed set, from the cache.

    Per ``docs/api-contract.md``'s first shaping decision, this is exactly
    the report ``POST /api/v1/scenario`` (P14) would return for an empty
    request body, just served without recomputing it.
    """
    return get_state(request).baseline_report
