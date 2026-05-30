from datetime import datetime

from backend.app.models.job import Job
from backend.app.models.user_session import UserSession
from backend.app.routes import user_routes


def _session(user_id: str):
    return UserSession(user_id=user_id, token="tok", token_info_json="{}")


def test_sync_status_uses_job_finished_time(client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.add(Job(
        id="sync-job",
        user_id="u1",
        job_type="sync_history",
        status="succeeded",
        progress_current=3,
        progress_total=3,
        finished_at=datetime(2026, 5, 30, 12, 0),
    ))
    db_session.commit()

    client = client_factory(user_routes.router)
    resp = client.get("/user/sync-status", headers={"X-User-Id": "u1"})

    assert resp.status_code == 200
    assert resp.json()["last_synced_at"] == "2026-05-30T12:00:00"


def test_frontend_message_origin_uses_allowed_state(monkeypatch):
    monkeypatch.setattr(
        user_routes.settings,
        "BACKEND_CORS_ORIGINS",
        ["http://127.0.0.1:5173", "https://music-intelligence-eight.vercel.app"],
    )

    assert (
        user_routes._frontend_message_origin("https://music-intelligence-eight.vercel.app")
        == "https://music-intelligence-eight.vercel.app"
    )
    assert user_routes._frontend_message_origin("https://evil.example") == "http://127.0.0.1:5173"
