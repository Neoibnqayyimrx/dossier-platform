"""A single error shape for every failure mode, so API clients only ever
parse one envelope: {"error": {"code": <http status>, "message": <str>}}.

WHY register handlers instead of shaping errors per-route: FastAPI's default
404/422 bodies ({"detail": ...}) already differ in shape from each other
(422's `detail` is a list of dicts, not a string). Normalizing here means
every router just raises a plain HTTPException and gets consistent JSON back.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _envelope(code: int, message: str, **extra) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"error": {"code": code, "message": message, **extra}},
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        # P18: a route may raise a DICT detail carrying `message` plus extra
        # keys -- the export gate uses it to say WHICH leaves are blocking,
        # so the UI can link to each instead of printing a paragraph. The
        # envelope's shape is unchanged for every other caller: `code` and
        # `message` are always there, and clients that ignore the rest keep
        # working exactly as before.
        if isinstance(exc.detail, dict):
            detail = dict(exc.detail)
            message = str(detail.pop("message", ""))
            response = _envelope(exc.status_code, message, **detail)
        else:
            response = _envelope(exc.status_code, str(exc.detail))
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # exc.errors() is pydantic's list of {loc, msg, type, ...}; flatten to
        # one readable message rather than leaking the raw structure.
        first = exc.errors()[0]
        loc = ".".join(str(part) for part in first["loc"] if part != "body")
        message = f"{loc}: {first['msg']}" if loc else first["msg"]
        return _envelope(status.HTTP_422_UNPROCESSABLE_ENTITY, message)
