"""Tests for scheduled playlist refresh (/playlists/schedules)."""
from datetime import timedelta

from backend.app.models.user_session import UserSession
from backend.app.models.playlist_schedule import PlaylistSchedule
from backend.app.routes import playlist_routes
from backend.app.services import playlist_schedule_service as svc
from backend.app.time_utils import utcnow_naive


def _session(user_id: str):
    return UserSession(user_id=user_id, token="tok", token_info_json="{}")


def _fake_preview(generated_id=999):
    def _inner(db, user_id, payload):
        return {"generated_playlist": {"id": generated_id}}
    return _inner


# ── service-level ────────────────────────────────────────────────────────────

def test_compute_next_run_cadence():
    now = utcnow_naive()
    assert svc.compute_next_run("daily", now=now) == now + timedelta(days=1)
    assert svc.compute_next_run("weekly", now=now) == now + timedelta(weeks=1)
    # Unknown cadence falls back to weekly.
    assert svc.compute_next_run("bogus", now=now) == now + timedelta(weeks=1)


def test_due_schedules_filters_by_next_run(db_session):
    now = utcnow_naive()
    due = PlaylistSchedule(user_id="u1", cadence="weekly", active=True,
                           next_run_at=now - timedelta(minutes=1), created_at=now)
    future = PlaylistSchedule(user_id="u1", cadence="weekly", active=True,
                              next_run_at=now + timedelta(days=1), created_at=now)
    inactive = PlaylistSchedule(user_id="u1", cadence="weekly", active=False,
                                next_run_at=now - timedelta(minutes=1), created_at=now)
    db_session.add_all([due, future, inactive])
    db_session.commit()

    rows = svc.due_schedules(db_session, user_id="u1", now=now)
    ids = {r.id for r in rows}
    assert due.id in ids
    assert future.id not in ids
    assert inactive.id not in ids


# ── routes ───────────────────────────────────────────────────────────────────

def test_create_and_list_schedule(monkeypatch, client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()
    monkeypatch.setattr(playlist_routes, "_build_preview", _fake_preview())

    client = client_factory(playlist_routes.router)
    created = client.post("/playlists/schedules", json={"cadence": "weekly", "max_tracks": 25},
                          headers={"X-User-Id": "u1"})
    assert created.status_code == 200
    assert created.json()["cadence"] == "weekly"
    assert created.json()["max_tracks"] == 25

    listed = client.get("/playlists/schedules", headers={"X-User-Id": "u1"})
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1


def test_create_schedule_rejects_unknown_cadence(client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()
    client = client_factory(playlist_routes.router)
    resp = client.post("/playlists/schedules", json={"cadence": "hourly"}, headers={"X-User-Id": "u1"})
    assert resp.status_code == 400


def test_get_schedules_processes_due(monkeypatch, client_factory, db_session):
    db_session.add(_session("u1"))
    # next_run_at defaults to now on create, so it is immediately due.
    db_session.commit()
    calls = []
    monkeypatch.setattr(
        playlist_routes, "_build_preview",
        lambda db, user_id, payload: calls.append(user_id) or {"generated_playlist": {"id": 7}},
    )

    client = client_factory(playlist_routes.router)
    client.post("/playlists/schedules", json={"cadence": "daily"}, headers={"X-User-Id": "u1"})

    resp = client.get("/playlists/schedules", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    assert resp.json()["ran_now"] >= 1
    assert calls == ["u1"]
    # After running, next_run_at advances into the future and last_generated id is set.
    item = resp.json()["items"][0]
    assert item["last_generated_playlist_id"] == 7
    assert item["next_run_at"] is not None


def test_run_schedule_now(monkeypatch, client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()
    monkeypatch.setattr(playlist_routes, "_build_preview", _fake_preview(generated_id=42))

    client = client_factory(playlist_routes.router)
    created = client.post("/playlists/schedules", json={"cadence": "weekly"}, headers={"X-User-Id": "u1"})
    schedule_id = created.json()["id"]

    ran = client.post(f"/playlists/schedules/{schedule_id}/run", headers={"X-User-Id": "u1"})
    assert ran.status_code == 200
    assert ran.json()["generated_playlist_id"] == 42
    assert ran.json()["schedule"]["last_run_at"] is not None


def test_delete_schedule(monkeypatch, client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()
    monkeypatch.setattr(playlist_routes, "_build_preview", _fake_preview())

    client = client_factory(playlist_routes.router)
    created = client.post("/playlists/schedules", json={"cadence": "weekly"}, headers={"X-User-Id": "u1"})
    schedule_id = created.json()["id"]

    deleted = client.delete(f"/playlists/schedules/{schedule_id}", headers={"X-User-Id": "u1"})
    assert deleted.status_code == 200

    missing = client.delete(f"/playlists/schedules/{schedule_id}", headers={"X-User-Id": "u1"})
    assert missing.status_code == 404


def test_schedules_require_auth(client_factory, db_session):
    client = client_factory(playlist_routes.router)
    assert client.get("/playlists/schedules").status_code == 401
    assert client.post("/playlists/schedules", json={"cadence": "weekly"}).status_code == 401
