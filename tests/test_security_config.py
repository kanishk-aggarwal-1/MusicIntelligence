from backend.app.config import settings
from backend.app.services.spotify_service import create_session_cookie_value, read_session_cookie_value


def test_cors_defaults_are_local_only():
    assert "*" not in settings.BACKEND_CORS_ORIGINS
    assert "http://127.0.0.1:5500" in settings.BACKEND_CORS_ORIGINS


def test_session_encryption_key_is_configured_for_local_env():
    assert settings.APP_ENV != "production" or settings.SESSION_ENCRYPTION_KEY


def test_signed_session_cookie_round_trip_and_rejects_tampering():
    value = create_session_cookie_value("user-1")
    assert read_session_cookie_value(value) == "user-1"
    assert read_session_cookie_value(value + "tampered") is None
