from backend.app.config import settings
from backend.app.models.user_session import UserSession
from backend.app.services.spotify_service import (
    clear_user_session,
    create_playlist,
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


def test_create_playlist_uses_current_user_endpoint(monkeypatch):
    from backend.app.services import spotify_service

    calls = []

    class FakeResponse:
        def __init__(self, url, payload):
            self.url = url
            self.payload = payload
            self.status_code = 200
            self.text = "{}"

        @property
        def reason(self):
            return "OK"

        def json(self):
            if self.url.endswith("/playlists"):
                return {"id": "playlist-id", "name": self.payload["name"]}
            return {"snapshot_id": "snapshot-id"}

    class FakeSpotify:
        def _auth_headers(self):
            return {"Authorization": "Bearer token"}

        def current_user(self):
            return {"id": "current-user"}

        def current_user_unfollow_playlist(self, playlist_id):
            calls.append(("unfollow", playlist_id))

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        return FakeResponse(url, json)

    monkeypatch.setattr(spotify_service.requests, "post", fake_post)

    playlist = create_playlist(FakeSpotify(), "stale-user-id", ["track-1"], name="Test Mix")

    assert playlist["id"] == "playlist-id"
    assert calls[0][0] == "https://api.spotify.com/v1/users/current-user/playlists"
    assert calls[0][1]["Authorization"] == "Bearer token"
    assert calls[0][1]["Content-Type"] == "application/json"
    assert calls[0][2]["name"] == "Test Mix"
    assert calls[1][0] == "https://api.spotify.com/v1/playlists/playlist-id/items"
    assert calls[1][2] == {"uris": ["spotify:track:track-1"]}
