"""Startup-built state shared by the P13 endpoints.

``app.py``'s lifespan calls :func:`build_state` once, not at import time, so
a test can build an app without ever reading the committed input files: it
hands :func:`build_state` an already-built ``Network`` instead of a pair of
paths. Both wire responses are computed once here and handed back verbatim
on every request, which is what makes the two endpoints cheap and what makes
``GET /api/v1/analysis/baseline`` return the identical payload on a second
call rather than recomputing it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from netscope.analysis import analyse
from netscope.api import mappers
from netscope.api.schemas import NetworkResponse, ScenarioReport
from netscope.config import Settings
from netscope.loaders.merge import build_network
from netscope.loaders.sites_csv import load_sites
from netscope.loaders.sndlib_xml import load_backbone
from netscope.models import Network

__all__ = ["AppState", "build_state", "get_state"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AppState:
    """Everything the two endpoints serve from memory."""

    network: Network
    network_response: NetworkResponse
    baseline_report: ScenarioReport


def build_state(
    settings: Settings,
    *,
    network: Network | None = None,
    attaches_to: Mapping[str, tuple[str, ...]] | None = None,
) -> AppState:
    """Load, merge and analyse once, per R1.

    Args:
        settings: file paths, used unless ``network`` is given directly.
        network: an already-built network, so a test can exercise the two
            endpoints' shape on a small, hand-built or fixture network
            without reading any file. ``attaches_to`` should then be given
            too, or every node reports no attachments.
        attaches_to: site id to attachment targets, ignored when ``network``
            is ``None`` because loading from ``settings`` derives this from
            the real ``sites.csv`` rows instead.

    Raises:
        InputError: if a committed input file is malformed, naming the file
            and the row (R2). Propagated as-is: turning this into a clean
            process exit instead of a stack trace is ``app.main``'s job, not
            this function's, so that a test can still assert on the
            exception itself.
    """
    if network is None:
        sites = load_sites(Path(settings.sites_path))
        resolved_attaches_to: Mapping[str, tuple[str, ...]] = mappers.attaches_to_map(sites)
        built_network = build_network(
            load_backbone(Path(settings.sndlib_path)),
            sites,
            sites_file=settings.sites_path,
        )
    else:
        built_network = network
        resolved_attaches_to = attaches_to if attaches_to is not None else {}

    baseline = analyse(built_network)
    logger.info(
        "startup: merged network has %d nodes, %d links, %d demands (%.1f units)",
        len(built_network.nodes),
        len(built_network.links),
        len(built_network.demands),
        built_network.total_demand,
    )
    return AppState(
        network=built_network,
        network_response=mappers.network_response(built_network, resolved_attaches_to),
        baseline_report=mappers.scenario_report(baseline),
    )


def get_state(request: Request) -> AppState:
    """The state the lifespan attached to this app, typed back from Starlette.

    Starlette's ``app.state`` is a plain namespace with no declared type, so
    the attribute read is narrowed with ``isinstance`` rather than annotated
    straight through, which is what keeps this function free of an explicit
    ``Any`` under ``disallow_any_explicit``.
    """
    state = request.app.state.netscope
    if not isinstance(state, AppState):
        raise RuntimeError("application state was not initialised: the lifespan has not run yet")
    return state
