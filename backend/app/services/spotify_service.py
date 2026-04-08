import json
import logging
from datetime import datetime, timedelta, timezone

import spotipy
from fastapi import Request
from cryptography.fernet import Fernet, InvalidToken
from spotipy.oauth2 import SpotifyOAuth
from sqlalchemy.orm import Session

from ..config import settings
from ..models.user_session import UserSession

logger = logging.getLogger(__name__)

SCOPES = (
    "user-read-recently-played "
    "user-top-read "
    "playlist-modify-private "
    "playlist-modify-public"
)


def _get_cipher():
    key = (settings.SESSION_ENCRYPTION_KEY or "").strip()
    if not key:
        return None
    try:
        return Fernet(key.encode("utf-8"))
    except Exception:
        logger.warning("SESSION_ENCRYPTION_KEY is invalid; using plaintext token storage")
        return None


def _encrypt(value: str | None):
    if not value:
        return value
    cipher = _get_cipher()
    if not cipher:
        return value
    return cipher.encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt(value: str | None):
    if not value:
        return value
    cipher = _get_cipher()
    if not cipher:
        return value
    try:
        return cipher.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return value


def _cipher_configured():
    return _get_cipher() is not None


def _looks_fernet_token(value: str | None):
    return bool(value and value.startswith("gAAAA"))


def _rewrap_session_secrets_if_needed(db: Session, session_row: UserSession, token: str | None, refresh_token: str | None):
    if not _cipher_configured():
        return

    changed = False

    if token and session_row.token and not _looks_fernet_token(session_row.token):
        session_row.token = _encrypt(token)
        changed = True

    if refresh_token and session_row.refresh_token and not _looks_fernet_token(session_row.refresh_token):
        session_row.refresh_token = _encrypt(refresh_token)
        changed = True

    if session_row.token_info_json and not _looks_fernet_token(session_row.token_info_json):
        session_row.token_info_json = _encrypt(session_row.token_info_json)
        changed = True

    if changed:
        session_row.updated_at = datetime.utcnow()
        db.commit()


def get_spotify_oauth():
    return SpotifyOAuth(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
        redirect_uri=settings.SPOTIFY_REDIRECT_URI,
        scope=SCOPES,
    )


def get_spotify_client(access_token: str):
    return spotipy.Spotify(auth=access_token)


def _parse_expiry(token_info: dict):
    expires_at = token_info.get("expires_at")
    if isinstance(expires_at, (int, float)):
        return datetime.fromtimestamp(expires_at, tz=timezone.utc).replace(tzinfo=None)
    expires_in = token_info.get("expires_in")
    if isinstance(expires_in, (int, float)):
        return datetime.utcnow() + timedelta(seconds=int(expires_in))
    return None


def save_user_session(db: Session, user_id: str, token: str = None, token_info: dict | None = None):
    token_info = token_info or {}
    token_value = token or token_info.get("access_token")
    refresh_token = token_info.get("refresh_token")
    token_expires_at = _parse_expiry(token_info)

    existing = db.query(UserSession).filter(UserSession.user_id == user_id).first()

    if existing:
        if token_value:
            existing.token = _encrypt(token_value)
        if refresh_token:
            existing.refresh_token = _encrypt(refresh_token)
        if token_expires_at:
            existing.token_expires_at = token_expires_at
        if token_info:
            existing.token_info_json = _encrypt(json.dumps(token_info))
        existing.updated_at = datetime.utcnow()
    else:
        db.add(
            UserSession(
                user_id=user_id,
                token=_encrypt(token_value),
                refresh_token=_encrypt(refresh_token) if refresh_token else None,
                token_expires_at=token_expires_at,
                token_info_json=_encrypt(json.dumps(token_info)) if token_info else None,
            )
        )

    db.commit()


def _refresh_access_token_if_needed(db: Session, session_row: UserSession):
    if not session_row:
        return None

    token = _decrypt(session_row.token)
    refresh_token = _decrypt(session_row.refresh_token)
    expires_at = session_row.token_expires_at

    still_valid = not expires_at or expires_at > (datetime.utcnow() + timedelta(seconds=45))
    if token and still_valid:
        return token

    if not refresh_token:
        return token

    try:
        sp_oauth = get_spotify_oauth()
        refreshed = sp_oauth.refresh_access_token(refresh_token)
        new_token = refreshed.get("access_token")
        if new_token:
            save_user_session(db, session_row.user_id, token_info=refreshed)
            return new_token
    except Exception:
        logger.exception("Failed to refresh Spotify token for user %s", session_row.user_id)

    return token


def _serialize_session(session_row: UserSession | None, token: str | None):
    if not session_row:
        return {"token": None, "user_id": None}
    return {
        "token": token,
        "user_id": session_row.user_id,
        "token_expires_at": session_row.token_expires_at.isoformat() if session_row.token_expires_at else None,
    }


def load_user_session(db: Session, user_id: str | None = None):
    query = db.query(UserSession)
    if user_id:
        session = query.filter(UserSession.user_id == user_id).order_by(UserSession.updated_at.desc()).first()
    else:
        session = query.order_by(UserSession.updated_at.desc()).first()

    if not session:
        return {"token": None, "user_id": None}

    token = _refresh_access_token_if_needed(db, session)
    refresh_token = _decrypt(session.refresh_token)
    _rewrap_session_secrets_if_needed(db, session, token, refresh_token)
    return _serialize_session(session, token)


def load_latest_user_session(db: Session):
    return load_user_session(db)


def load_request_user_session(db: Session, request: Request | None = None):
    requested_user_id = None
    if request is not None:
        requested_user_id = (request.headers.get("X-User-Id") or "").strip() or None
    return load_user_session(db, user_id=requested_user_id)


def _played_at_to_ms(played_at: str):
    dt = datetime.fromisoformat(played_at.replace("Z", "+00:00"))
    return int(dt.astimezone(timezone.utc).timestamp() * 1000)


def fetch_recent_tracks(sp, max_tracks: int = 1000):
    tracks = []
    before = None

    while len(tracks) < max_tracks:
        batch_size = min(50, max_tracks - len(tracks))
        data = sp.current_user_recently_played(limit=batch_size, before=before)
        items = data.get("items", [])

        if not items:
            break

        for item in items:
            track = item.get("track")
            if not track:
                continue

            uri = track.get("uri")
            spotify_id = track.get("id")
            if not spotify_id and isinstance(uri, str) and uri.startswith("spotify:track:"):
                spotify_id = uri.split(":")[-1]

            tracks.append(
                {
                    "title": track.get("name"),
                    "artist": (track.get("artists") or [{}])[0].get("name"),
                    "spotify_id": spotify_id,
                    "played_at": item.get("played_at"),
                }
            )

            if len(tracks) >= max_tracks:
                break

        last_played_at = items[-1].get("played_at")
        if not last_played_at:
            break

        before = _played_at_to_ms(last_played_at) - 1

    return tracks


def _pick_track_id(items, artist: str | None = None):
    if not items:
        return None

    if artist:
        target = artist.strip().lower()
        for item in items:
            names = [a.get("name", "").lower() for a in item.get("artists", [])]
            if any(target in n or n in target for n in names):
                return item.get("id")

    return items[0].get("id")


def resolve_track_id(sp, title: str, artist: str | None = None):
    queries = []

    if title and artist:
        queries.append((f"track:{title} artist:{artist}", 5))
        queries.append((f"{title} {artist}", 5))

    if title:
        queries.append((title, 5))

    if artist:
        queries.append((f"artist:{artist}", 5))

    for query, limit in queries:
        result = sp.search(q=query, type="track", limit=limit)
        items = result.get("tracks", {}).get("items", [])
        track_id = _pick_track_id(items, artist=artist)
        if track_id:
            return track_id

    return None


def search_track(sp, title: str, artist: str):
    return resolve_track_id(sp, title, artist)


def create_playlist(sp, user_id: str, track_ids):
    playlist = sp.user_playlist_create(
        user=user_id,
        name="AI Generated Playlist",
        public=False,
    )

    if track_ids:
        sp.playlist_add_items(playlist["id"], track_ids)

    return playlist
