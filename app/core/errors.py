"""One error envelope for every API surface: {"ok": false, "error": {...}}."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("romka.errors")


class ROMKAError(Exception):
    status_code = 400
    code = "romka_error"

    def __init__(self, message: str, *, details: dict | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code


class NotFound(ROMKAError):
    status_code = 404
    code = "not_found"


class PermissionDenied(ROMKAError):
    status_code = 403
    code = "permission_denied"


class Unauthorized(ROMKAError):
    status_code = 401
    code = "unauthorized"


class Conflict(ROMKAError):
    status_code = 409
    code = "conflict"


class ValidationFailed(ROMKAError):
    status_code = 422
    code = "validation_failed"


class BudgetExceeded(ROMKAError):
    status_code = 429
    code = "budget_exceeded"


class ProviderUnavailable(ROMKAError):
    status_code = 503
    code = "provider_unavailable"


def envelope(code: str, message: str, details: dict | None = None) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ROMKAError)
    async def _romka(_: Request, exc: ROMKAError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=envelope("validation_failed", "ورودی نامعتبر است.", {"errors": str(exc.errors())[:2000]}),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope("http_error", str(exc.detail), {}),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Log server-side, never leak internals to the client.
        log.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content=envelope("internal_error", "خطای داخلی. جزئیات در لاگ سرور ثبت شد.", {}),
        )
