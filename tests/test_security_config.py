from backend.app.config import settings


def test_cors_defaults_are_local_only():
    assert "*" not in settings.BACKEND_CORS_ORIGINS
    assert "http://127.0.0.1:5500" in settings.BACKEND_CORS_ORIGINS
