from datetime import datetime

from backend.app.models.job import Job
from backend.app.models.user_session import UserSession
from backend.app.routes import user_routes
from backend.app.services.job_service import create_job


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
    monkeypatch.setattr(user_routes.settings, "APP_ENV", "production")

    assert (
        user_routes._frontend_message_origin("https://music-intelligence-eight.vercel.app")
        == "https://music-intelligence-eight.vercel.app"
    )
    assert user_routes._frontend_message_origin("https://evil.example") == "http://127.0.0.1:5173"


def test_sync_history_job_reuses_active_job(client_factory, db_session):
    db_session.add(_session("u1"))
    existing = create_job(
        db_session,
        user_id="u1",
        job_type="sync_history",
        message="Already syncing",
        progress_total=3,
    )
    db_session.commit()

    client = client_factory(user_routes.router)
    resp = client.post("/user/sync-history/job", headers={"X-User-Id": "u1"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["id"] == existing.id
    assert payload["message"] == "Already syncing"
    assert db_session.query(Job).filter_by(user_id="u1", job_type="sync_history").count() == 1


def test_import_history_job_reports_incremental_progress(monkeypatch, db_session):
    updates = []

    class FakeProgress:
        def update(self, **kwargs):
            updates.append(kwargs)

    monkeypatch.setattr(user_routes, "IMPORT_PROGRESS_BATCH_SIZE", 2)
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Import should not auto-enrich; dedup/enrichment happens after all files are imported.")

    monkeypatch.setattr(user_routes, "backfill_missing_metadata", fail_if_called)

    data = [
        {
            "master_metadata_track_name": f"Track {i}",
            "master_metadata_album_artist_name": "Artist",
            "spotify_track_uri": f"spotify:track:{i}",
            "ts": f"2026-05-0{i + 1}T10:00:00Z",
            "ms_played": 60_000,
        }
        for i in range(5)
    ]

    result = user_routes._run_import_history_job(db_session, FakeProgress(), user_id="u1", data=data)

    messages = [item.get("message") for item in updates if item.get("message")]
    assert "Importing 0 / 5 tracks into library" in messages
    assert "Importing 2 / 5 tracks into library" in messages
    assert "Importing 4 / 5 tracks into library" in messages
    assert "Importing 5 / 5 tracks into library" in messages
    assert "Import complete. Run deduplication, then metadata enrichment." in messages
    assert result["valid_tracks"] == 5
    assert result["enrichment_queued"] is False
    assert result["next_step"] == "Run deduplication, then metadata enrichment."
    assert result["progress_current"] == 5
    assert result["progress_total"] == 5
