"""Application error types + FastAPI handlers."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse


class MAAHAFError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFound(MAAHAFError):
    status_code = 404
    code = "not_found"


class Unauthorized(MAAHAFError):
    status_code = 401
    code = "unauthorized"


class Forbidden(MAAHAFError):
    status_code = 403
    code = "forbidden"


class BadRequest(MAAHAFError):
    status_code = 400
    code = "bad_request"


class UpstreamError(MAAHAFError):
    status_code = 502
    code = "upstream_error"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(MAAHAFError)
    async def _handle(_: Request, exc: MAAHAFError) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
