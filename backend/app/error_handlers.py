import logging
import time
import uuid

import requests
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from spotipy.exceptions import SpotifyException

from .config import settings


logger = logging.getLogger(__name__)


def _request_id(request: Request):
    request_id = getattr(request.state, "request_id", None)
    if not request_id:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
    return request_id


def _json_error(request: Request, status_code: int, code: str, message: str, *, detail: str | None = None):
    payload = {
        "error": code,
        "message": message,
        "request_id": _request_id(request),
    }
    if detail and settings.APP_ENV != "production":
        payload["detail"] = detail
    return JSONResponse(status_code=status_code, content=payload)


def install_error_handlers(app):
    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
        logger.info(
            "request_completed method=%s path=%s status=%s duration_ms=%s request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request.state.request_id,
        )
        return response

    @app.exception_handler(SpotifyException)
    async def spotify_exception_handler(request: Request, exc: SpotifyException):
        status = int(getattr(exc, "http_status", None) or 502)
        if status == 401:
            message = "Spotify authorization expired. Log in again."
        elif status == 403:
            message = "Spotify refused the requested action. Log in again and approve the required scopes."
        elif status == 429:
            message = "Spotify rate limit reached. Try again later."
        else:
            message = "Spotify request failed."
        logger.warning("spotify_error status=%s request_id=%s error=%s", status, _request_id(request), exc)
        return _json_error(request, status, "spotify_error", message, detail=str(exc))

    @app.exception_handler(requests.RequestException)
    async def requests_exception_handler(request: Request, exc: requests.RequestException):
        logger.warning("external_request_error request_id=%s error=%s", _request_id(request), exc)
        return _json_error(request, 502, "external_request_error", "External service request failed.", detail=str(exc))

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        logger.exception("database_error request_id=%s", _request_id(request))
        return _json_error(request, 500, "database_error", "Database operation failed.", detail=str(exc))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled_error request_id=%s", _request_id(request))
        return _json_error(request, 500, "internal_error", "Internal server error.", detail=str(exc))
