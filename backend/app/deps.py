"""Shared route helpers for resolving the authenticated user session.

Centralizes the auth preamble that every protected endpoint repeated:
load the request's session and reject with 401 when no user is logged in.
"""

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from .services.spotify_service import load_request_user_session


def require_user_session(db: Session, request: Request) -> dict:
    """Return the current user's session dict, or raise 401 if not logged in.

    Use this when the endpoint also needs the Spotify token (``session["token"]``);
    otherwise prefer ``require_user_id``.
    """
    session = load_request_user_session(db, request)
    if not session.get("user_id"):
        raise HTTPException(status_code=401, detail="User not logged in")
    return session


def require_user_id(db: Session, request: Request) -> str:
    """Return the current user's id, or raise 401 if not logged in."""
    return require_user_session(db, request)["user_id"]
