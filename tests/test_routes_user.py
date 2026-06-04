from datetime import datetime, timedelta

from backend.app.models.api_cache import ApiCache
from backend.app.models.job import Job
from backend.app.models.user_session import UserSession
from backend.app.routes import user_routes
from backend.app.services.job_service import create_job
from backend.app.time_utils import utcnow_naive


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

    # Use a small chunk size so we get multiple progress updates even for 5 tracks.
    monkeypatch.setattr(user_routes, "_BULK_CHUNK", 2)

    # Enrichment must NOT be triggered automatically — the user runs dedup first.
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Import must not auto-enrich; dedup/enrichment happen after all files are uploaded.")
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
    # Bulk flow emits phase messages then per-chunk history progress.
    assert any("artist" in m.lower() for m in messages), "expected artist-sync phase message"
    assert any("library" in m.lower() or "tracks" in m.lower() for m in messages)
    # History phase: at least one "Importing X / 5" line with chunk-level granularity.
    assert any("Importing" in m and "/ 5" in m for m in messages), f"no history progress message found in: {messages}"
    # Final done message from _run_import_history_job
    assert any("Next" in m or "Deduplication" in m or "complete" in m.lower() for m in messages)

    assert result["valid_tracks"] == 5
    assert result["enrichment_queued"] is False
    assert result["progress_current"] == 5
    assert result["progress_total"] == 5
    assert result["new_songs"] == 5           # all 5 tracks are brand-new
    assert result["new_history_rows"] == 5    # all 5 inserted


def test_new_import_clears_previous_import_jobs_and_rate_limit(db_session):
    now = utcnow_naive()
    db_session.add_all([
        Job(
            id="old-running",
            user_id="u1",
            job_type="import_history",
            status="running",
            progress_current=10,
            progress_total=100,
            created_at=now,
        ),
        Job(
            id="old-failed",
            user_id="u1",
            job_type="import_history",
            status="failed",
            progress_current=5,
            progress_total=100,
            created_at=now,
        ),
        Job(
            id="other-job",
            user_id="u1",
            job_type="sync_history",
            status="running",
            created_at=now,
        ),
        ApiCache(
            provider="rate_limit",
            cache_key=f"rate_limit:{user_routes.IMPORT_RATE_LIMIT_NAMESPACE}:u1",
            response_json="[1,2,3]",
            status_code=200,
            fetched_at=now,
            expires_at=now + timedelta(minutes=10),
        ),
    ])
    db_session.commit()

    cleanup = user_routes._clear_previous_import_requests(db_session, "u1")

    assert cleanup["cancelled_active_imports"] == 1
    assert cleanup["deleted_previous_imports"] == 2
    assert cleanup["cleared_import_rate_limits"] == 1
    assert db_session.query(Job).filter_by(user_id="u1", job_type="import_history").count() == 0
    assert db_session.query(Job).filter_by(id="other-job").count() == 1
    assert db_session.query(ApiCache).filter_by(provider="rate_limit").count() == 0
