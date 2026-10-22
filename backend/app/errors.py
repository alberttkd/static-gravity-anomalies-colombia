"""Problem Details (RFC 9457) error responses with stable codes (MASTER_GUIDE §6.8)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from gravanom.analysis.profiles import ProfileOutsideSupportError
from gravanom.density import InsufficientDataError
from gravanom.gridding import GridTooLargeError, TooFewPointsError, VariogramFitError
from gravanom.pipeline import PrivateDataUnavailableError

log = logging.getLogger("app.errors")
PROBLEM = "application/problem+json"


class ProblemError(Exception):
    """An error rendered as ``application/problem+json``."""

    def __init__(self, status: int, code: str, title: str, detail: str = "") -> None:
        super().__init__(detail or title)
        self.status, self.code, self.title, self.detail = status, code, title, detail


def not_found(what: str) -> ProblemError:
    return ProblemError(404, "NOT_FOUND", "Not found", f"{what} not found")


def _problem(
    status: int, code: str, title: str, detail: str, request: Request, extra: dict[str, Any] | None = None
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://gravanom.local/problems/{code.lower()}",
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
        "instance": request.url.path,
    }
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


DOMAIN_ERRORS: dict[type[Exception], tuple[int, str, str]] = {
    PrivateDataUnavailableError: (503, "PRIVATE_DATA_UNAVAILABLE", "Private data unavailable"),
    GridTooLargeError: (413, "GRID_TOO_LARGE", "Grid too large"),
    TooFewPointsError: (409, "INSUFFICIENT_DATA", "Insufficient data"),
    InsufficientDataError: (409, "INSUFFICIENT_DATA", "Insufficient data"),
    VariogramFitError: (409, "VARIOGRAM_FIT_FAILED", "Variogram fit failed"),
    ProfileOutsideSupportError: (409, "INSUFFICIENT_DATA", "Profile outside the data support"),
}


def install_error_handlers(app: FastAPI) -> None:
    """Map domain exceptions, validation errors and HTTP errors to problem+json."""

    @app.exception_handler(ProblemError)
    async def _problem_error(request: Request, exc: ProblemError) -> JSONResponse:
        return _problem(exc.status, exc.code, exc.title, exc.detail, request)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e.get("loc", [])), "msg": str(e.get("msg", ""))} for e in exc.errors()]
        return _problem(
            422, "VALIDATION_ERROR", "Validation error", "request failed validation", request, {"errors": errors}
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 413: "PAYLOAD_TOO_LARGE"}.get(exc.status_code, "HTTP_ERROR")
        return _problem(exc.status_code, code, str(exc.detail), str(exc.detail), request)

    for exc_type, (status, code, title) in DOMAIN_ERRORS.items():

        async def _domain(
            request: Request, exc: Exception, status: int = status, code: str = code, title: str = title
        ) -> JSONResponse:
            # Domain messages never contain filesystem paths.
            return _problem(status, code, title, str(exc), request)

        app.add_exception_handler(exc_type, _domain)  # type: ignore[arg-type]

    @app.exception_handler(Exception)
    async def _internal(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s", request.url.path)
        return _problem(500, "INTERNAL", "Internal error", "an internal error occurred", request)
