from datetime import timedelta

import pytest

from backend.app.authz import capabilities_for
from backend.app.config import settings
from backend.app.models.user_session import UserSession
from backend.app.routes import insights_routes, job_routes, music_routes, playlist_routes, user_routes
from backend.app.time_utils import utcnow_naive


def _demo_session():
    return UserSession(
        user_id=settings.DEMO_USER_ID,
        token="__demo__",
        token_expires_at=utcnow_naive() - timedelta(days=1),
        token_info_json="{}",
    )


def test_demo_session_exposes_read_only_capabilities(client_factory, db_session):
    db_session.add(_demo_session())
    db_session.commit()
    client = client_factory(user_routes.router)

    response = client.get("/user/session", headers={"X-User-Id": settings.DEMO_USER_ID})

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_demo"] is True
    assert payload["capabilities"]["preview_playlists"] is True
    assert payload["capabilities"]["mutate_library"] is False
    assert payload["capabilities"]["create_spotify_playlists"] is False


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("post", "/insights/feedback", {"song_id": 1, "action": "like"}),
        ("delete", "/insights/feedback", None),
        ("post", "/insights/goals", {"goal_type": "new_songs_per_week", "target_value": 5}),
        ("post", "/insights/cache/clear", None),
        ("post", "/insights/dedup-apply", None),
        ("post", "/songs/1/hide", None),
        ("post", "/jobs/missing/cancel", None),
        ("post", "/playlists/schedules", {"cadence": "weekly"}),
    ],
)
def test_demo_mutations_are_consistently_rejected(client_factory, db_session, method, path, json_body):
    db_session.add(_demo_session())
    db_session.commit()
    client = client_factory(
        insights_routes.router,
        music_routes.router,
        job_routes.router,
        playlist_routes.router,
    )

    response = client.request(
        method.upper(),
        path,
        headers={"X-User-Id": settings.DEMO_USER_ID},
        json=json_body,
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "capability_not_available"


def test_real_user_capabilities_reflect_spotify_connection():
    disconnected = capabilities_for("real-user", spotify_connected=False)
    connected = capabilities_for("real-user", spotify_connected=True)

    assert disconnected["manage_goals"] is True
    assert disconnected["create_spotify_playlists"] is False
    assert connected["create_spotify_playlists"] is True
    assert connected["sync_spotify"] is True


def test_demo_cannot_export_shared_account_data(client_factory, db_session):
    db_session.add(_demo_session())
    db_session.commit()
    client = client_factory(user_routes.router)

    response = client.get("/user/export-data", headers={"X-User-Id": settings.DEMO_USER_ID})

    assert response.status_code == 403
    assert response.json()["detail"]["capability"] == "manage_account"
