import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from spotipy.exceptions import SpotifyException

from backend.app.error_handlers import install_error_handlers


def _client():
    app = FastAPI()
    install_error_handlers(app)
    return app


def test_spotify_errors_are_readable_json():
    app = _client()

    @app.get("/boom")
    def boom():
        raise SpotifyException(403, -1, "Forbidden")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom", headers={"X-Request-ID": "req-test"})

    assert response.status_code == 403
    assert response.json()["error"] == "spotify_error"
    assert "Spotify refused" in response.json()["message"]
    assert response.headers["X-Request-ID"] == "req-test"


def test_external_request_errors_are_readable_json():
    app = _client()

    @app.get("/boom")
    def boom():
        raise requests.Timeout("slow upstream")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 502
    assert response.json()["error"] == "external_request_error"
    assert response.json()["message"] == "External service request failed."
