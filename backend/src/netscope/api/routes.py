"""``GET /api/v1/network`` and ``GET /api/v1/analysis/baseline`` (P13).

P14 adds ``GET /api/v1/criticality`` and ``POST /api/v1/scenario`` to this
same router. ``get_criticality`` is written the same way as the P13
endpoints: the body comes straight from :class:`~netscope.api.state.AppState`,
computed once at startup, so a request never touches the sweep at all.

``post_scenario`` is the one endpoint here that does real work per request,
since the contract requires it be a pure function of the request body (R11,
D5). It calls ``netscope.analysis.analyse`` directly rather than through the
cache, and turns the ``ValueError`` that ``netscope.routing.route`` already
raises for an unknown id (R2) into a 422 ``ErrorResponse`` instead of letting
it become the generic 500 ``app.py`` otherwise gives an unanticipated
exception.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from netscope.analysis import analyse
from netscope.api import mappers
from netscope.api.schemas import (
    CriticalityResponse,
    ErrorDetail,
    ErrorResponse,
    NetworkResponse,
    ScenarioReport,
    ScenarioRequest,
)
from netscope.api.state import AppState, get_state

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
    the report ``POST /api/v1/scenario`` would return for an empty request
    body, just served without recomputing it.
    """
    return get_state(request).baseline_report


@router.get("/criticality", response_model=CriticalityResponse)
async def get_criticality(request: Request) -> CriticalityResponse:
    """Every node and link, assessed once at startup, from the cache."""
    return get_state(request).criticality_response


@router.post(
    "/scenario",
    response_model=ScenarioReport,
    responses={422: {"model": ErrorResponse}},
)
async def post_scenario(
    payload: ScenarioRequest, request: Request
) -> ScenarioReport | JSONResponse:
    """R8: the report for an arbitrary failed set, computed fresh per request.

    An empty ``payload`` reproduces ``GET /api/v1/analysis/baseline`` field
    for field, because both call the same ``analyse`` with both failed sets
    empty; there is no branch here for that case, matching ``analyse``'s own
    "one function, not two".

    A duplicate id within ``failed_nodes`` or ``failed_links`` is not an
    error: both are converted to a ``frozenset`` before being handed to
    ``analyse``, so "Dublin" twice means exactly what "Dublin" once means. A
    node and one of its own links both failed is likewise not an error, and
    needs no special handling: ``analyse`` already accepts the two failed
    sets independently, so failing a node and its access link together is
    just two independent failures applied at once.
    """
    state = get_state(request)
    failed_nodes = frozenset(payload.failed_nodes)
    failed_links = frozenset(payload.failed_links)

    rejection = _reject_unknown_ids(state, failed_nodes, failed_links)
    if rejection is not None:
        return rejection

    # Any ValueError from here is a bug in our own code, not a bad request, so
    # it is deliberately not caught: it must surface as a 500 rather than be
    # dressed up as a client error.
    analysis = analyse(state.network, failed_nodes=failed_nodes, failed_links=failed_links)
    return mappers.scenario_report(analysis)


def _reject_unknown_ids(
    state: AppState,
    failed_nodes: frozenset[str],
    failed_links: frozenset[str],
) -> JSONResponse | None:
    """Check the requested ids against the network, or return ``None``.

    Validation happens here rather than by catching the ``ValueError`` that
    ``routing.route`` raises for the same thing, for two reasons.

    A caught exception has to be told apart from every other ``ValueError``,
    and the only handle on it is the wording of its message. Matching on that
    makes a response depend on a private helper's prose: reword the message
    and this quietly labels a bad node id as a link problem, with no test
    failing, because the fallback branch is still a plausible answer.

    It also conflates two different things. An unknown id in a request is a
    client mistake and a 422. A ``ValueError`` from the routing code is a bug
    in ours and should be a 500. Catching the second to serve the first hides
    real faults behind a tidy error body.

    Nodes are checked before links, matching the fail-fast convention in D14:
    one precise message beats a list whose later entries may be noise.
    """
    for field, requested, known in (
        ("failed_nodes", failed_nodes, state.network.nodes.keys()),
        ("failed_links", failed_links, state.network.links.keys()),
    ):
        unknown = sorted(requested - set(known))
        if unknown:
            noun = "node" if field == "failed_nodes" else "link"
            plural = "s" if len(unknown) > 1 else ""
            return JSONResponse(
                status_code=422,
                content=ErrorResponse(
                    error=ErrorDetail(
                        message=(
                            f"unknown {noun} id{plural} in the failed set: {', '.join(unknown)}"
                        ),
                        field=field,
                    )
                ).model_dump(mode="json"),
            )
    return None
