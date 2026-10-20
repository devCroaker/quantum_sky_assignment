"""The FastAPI application.

Nothing here reads a file at import time. The committed inputs are only
touched inside the lifespan context, which runs when a server actually
starts (or when a test's ``TestClient`` is used as a context manager), so
importing this module to build an app for testing against a hand-built
network never has to see ``data/nobel-eu.xml`` or ``data/sites.csv``.

Request logging and failure logging both go through the standard library's
``logging`` module, per the P13 brief's "keep it simple and standard-library
based".
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from netscope.api.routes import router
from netscope.api.schemas import ErrorDetail, ErrorResponse
from netscope.api.state import AppState, build_state
from netscope.config import Settings
from netscope.errors import InputError

__all__ = ["create_app", "main"]

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, state: AppState | None = None) -> FastAPI:
    """Build the application.

    Args:
        settings: file paths and bind address. Defaults to
            :meth:`Settings.from_env`, which is what a real process wants.
        state: a pre-built :class:`AppState`, so a test can skip loading
            entirely, or load once itself (for example to assert on a bad
            input file) and hand the result straight in rather than paying
            for a second load inside the lifespan.
    """
    effective_settings = settings if settings is not None else Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.netscope = state if state is not None else build_state(effective_settings)
        yield

    app = FastAPI(title="netscope", version="v1", lifespan=lifespan)
    app.include_router(router)

    @app.middleware("http")
    async def log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Structured logging of every request: method, path, status, timing."""
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "request",
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
                "http_status": response.status_code,
                "duration_ms": round(elapsed_ms, 2),
            },
        )
        return response

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """Any failure the route handlers did not anticipate.

        Logged with a traceback server-side via ``logger.exception``, and
        answered with the same ``ErrorResponse`` shape a rejected request
        uses, so the front end has exactly one error shape to parse.
        """
        logger.exception(
            "unhandled error",
            extra={"http_method": request.method, "http_path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(error=ErrorDetail(message=str(exc))).model_dump(mode="json"),
        )

    return app


def main() -> None:
    """Process entry point: load first, then serve.

    R2's "one clear line, not a traceback" is what this function exists to
    guarantee. ``build_state`` runs here, before ``uvicorn.run`` and outside
    of its lifespan machinery, specifically so a malformed input file is
    caught by this ``except`` clause and logged as the one ``InputError``
    line it is, rather than surfacing as uvicorn's own startup-failure
    traceback. The successfully built state is then handed straight to
    :func:`create_app`, so the lifespan does not load everything a second
    time.
    """
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = Settings.from_env()
    try:
        state = build_state(settings)
    except InputError as exc:
        logging.getLogger(__name__).error(str(exc))
        raise SystemExit(1) from None

    import uvicorn

    uvicorn.run(create_app(settings, state=state), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
