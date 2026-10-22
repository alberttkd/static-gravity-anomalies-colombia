"""FastAPI application: ``uvicorn app.main:app --app-dir backend``."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import gravanom
from app.api.v1.routes import router
from app.errors import install_error_handlers
from app.services import build_services
from app.settings import REPO_ROOT, Settings, get_settings

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; worker-src 'self' blob:; connect-src 'self' data: blob:"
    ),
}


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app (a fresh service layer per app, so tests can use their own settings)."""
    cfg = settings or get_settings()
    logging.basicConfig(
        level=cfg.log_level.upper(),
        format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    )
    app = FastAPI(
        title="grav-anomaly-explorer API",
        version=gravanom.__version__,
        description="Static gravity anomalies: reduction, QC, gridding with calibrated uncertainty. Units: mGal.",
    )
    app.state.services = build_services(cfg)
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["X-Bounds", "X-Render-Meta"],
    )

    @app.middleware("http")
    async def limits_and_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        length = request.headers.get("content-length")
        if length is not None and int(length) > cfg.max_body_bytes:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                {
                    "title": "Payload too large",
                    "status": 413,
                    "code": "PAYLOAD_TOO_LARGE",
                    "detail": "request body exceeds the limit",
                },
                status_code=413,
                media_type="application/problem+json",
            )
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response

    app.include_router(router)
    dist = REPO_ROOT / "frontend" / "dist"
    if Path(dist / "index.html").exists():  # local full mode: serve the built UI
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return app


app = create_app()
