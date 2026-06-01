from backend.app.config import settings
from backend.app.models.user_session import UserSession
from backend.app.services.spotify_service import (
    clear_user_session,
    create_session_cookie_value,
    get_missing_stored_playlist_scopes,
    missing_playlist_scopes,
    read_session_cookie_value,
)


def test_cors_defaults_are_local_only():
    assert "*" not in settings.BACKEND_CORS_ORIGINS
    assert "http://127.0.0.1:5500" in settings.BACKEND_CORS_ORIGINS


def test_session_encryption_key_is_configured_for_local_env():
    assert settings.APP_ENV != "production" or settings.SESSION_ENCRYPTION_KEY


def test_signed_session_cookie_round_trip_and_rejects_tampering():
    value = create_session_cookie_value("user-1")
    assert read_session_cookie_value(value) == "user-1"
    assert read_session_cookie_value(value + "tampered") is None


def test_missing_playlist_scopes_detects_under_scoped_token():
    token_info = {"scope": "user-read-recently-played user-top-read playlist-modify-private"}

    assert missing_playlist_scopes(token_info) == ["playlist-modify-public"]
    assert missing_playlist_scopes({"scope": "user-read-recently-played playlist-modify-private playlist-modify-public"}) == []


def test_stored_playlist_scope_helpers(db_session):
    db_session.add(UserSession(
        user_id="u1",
        token="tok",
        token_info_json='{"scope":"user-read-recently-played playlist-modify-private"}',
    ))
    db_session.commit()

    assert get_missing_stored_playlist_scopes(db_session, "u1") == ["playlist-modify-public"]
    assert clear_user_session(db_session, "u1") == 1
    assert get_missing_stored_playlist_scopes(db_session, "u1") == ["playlist-modify-private", "playlist-modify-public"]
