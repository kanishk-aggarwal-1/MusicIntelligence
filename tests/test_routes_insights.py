"""Tests for /insights routes (insights_routes.py)."""
from datetime import datetime, timedelta

from backend.app.models.artist import Artist
from backend.app.models.listening_history import ListeningHistory
from backend.app.models.listening_goal import ListeningGoal
from backend.app.models.recommendation_feedback import RecommendationFeedback
from backend.app.models.song import Song
from backend.app.models.song_tag import SongTag
from backend.app.models.tag import Tag
from backend.app.models.user_session import UserSession
from backend.app.routes import insights_routes
from backend.app.services import api_cache_service, recommendation_service
from backend.app.time_utils import utcnow_naive


def _session(user_id: str):
    return UserSession(user_id=user_id, token="tok", token_info_json="{}")


def _artist(db, name: str) -> Artist:
    a = db.query(Artist).filter_by(name=name).first()
    if not a:
        a = Artist(name=name)
        db.add(a)
        db.flush()
    return a


def _song(db, *, artist_name: str, title: str, genre: str | None = None,
          spotify_id: str | None = None, enrichment_status: str = "complete") -> Song:
    artist = _artist(db, artist_name)
    s = Song(
        title=title,
        artist_id=artist.id,
        genre=genre,
        spotify_id=spotify_id,
        enrichment_status=enrichment_status,
        is_deleted=False,
    )
    db.add(s)
    db.flush()
    return s


def _tag_song(db, song: Song, tag_name: str, weight: float | None = None) -> None:
    t = db.query(Tag).filter_by(name=tag_name).first()
    if not t:
        t = Tag(name=tag_name)
        db.add(t)
        db.flush()
    db.add(SongTag(song_id=song.id, tag_id=t.id, weight=weight))


def _history(db, user_id: str, song: Song, played_at: datetime):
    db.add(ListeningHistory(user_id=user_id, song_id=song.id, played_at=played_at))


# ── /insights/taste-timeline ─────────────────────────────────────────────────

def test_taste_timeline_returns_monthly_data(client_factory, db_session):
    db_session.add(_session("u1"))
    s = _song(db_session, artist_name="Timeline Artist", title="Timeline Track", genre="indie")
    _history(db_session, "u1", s, datetime(2026, 4, 15, 10, 0))
    _history(db_session, "u1", s, datetime(2026, 5, 10, 10, 0))
    db_session.commit()

    client = client_factory(insights_routes.router)
    resp = client.get("/insights/taste-timeline?months=6", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    data = resp.json()
    assert "monthly_top_artists" in data
    assert "monthly_top_genres" in data
    assert any(r["artist"] == "Timeline Artist" for r in data["monthly_top_artists"])
    assert any(r["genre"] == "indie" for r in data["monthly_top_genres"])


def test_taste_timeline_requires_auth(client_factory, db_session):
    client = client_factory(insights_routes.router)
    resp = client.get("/insights/taste-timeline")
    assert resp.status_code == 401


def test_taste_timeline_empty_for_new_user(client_factory, db_session):
    db_session.add(_session("u2"))
    db_session.commit()
    client = client_factory(insights_routes.router)
    resp = client.get("/insights/taste-timeline", headers={"X-User-Id": "u2"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["monthly_top_artists"] == []
    assert data["monthly_top_genres"] == []


# ── /insights/discovery-feed ─────────────────────────────────────────────────

def test_discovery_feed_returns_items(monkeypatch, client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()

    # insights_routes imports build_discovery_feed directly; patch its local binding
    monkeypatch.setattr(
        insights_routes, "build_discovery_feed",
        lambda db, user_id, limit=20: [
            {"song_id": 1, "title": "Discovered Track", "artist": "New Artist",
             "score": 0.95, "image_url": None, "preview_url": None}
        ]
    )

    client = client_factory(insights_routes.router)
    resp = client.get("/insights/discovery-feed?limit=5", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1
    assert resp.json()["items"][0]["title"] == "Discovered Track"


def test_compute_new_for_you_discovers_uncached_tracks(monkeypatch, db_session):
    """The discovery computation (run inside a background job) filters out
    already-listened tracks and tags each result with a reason."""
    db_session.add(_session("u1"))
    top_songs = []
    for i in range(5):
        song = _song(db_session, artist_name=f"Seed Artist {i}", title=f"Seed Track {i}", spotify_id=f"seed-{i}")
        top_songs.append(song)
        _history(db_session, "u1", song, datetime(2026, 5, i + 1, 10, 0))
    db_session.commit()

    cached_payloads = []
    monkeypatch.setattr(
        insights_routes,
        "store_cached_response",
        lambda provider, key, payload=None, **kwargs: cached_payloads.append((provider, key, payload)),
    )

    def _fake_discover(artist_name, **kwargs):
        return [
            {"title": f"New from {artist_name}", "artist": "New Artist", "spotify_id": f"new-{artist_name}"},
            {"title": top_songs[0].title, "artist": "Seed Artist 0", "spotify_id": top_songs[0].spotify_id},
        ]

    monkeypatch.setattr(insights_routes, "discover_songs_from_artist", _fake_discover)

    payload = insights_routes._compute_new_for_you(db_session, "u1")

    assert len(payload["items"]) == 5
    assert payload["items"][0]["reason"].startswith("Similar to Seed Artist")
    assert all(item["title"] != "Seed Track 0" for item in payload["items"])
    # Each item carries an actionable Spotify link (search URL fallback here).
    assert all(item["spotify_url"] for item in payload["items"])
    assert cached_payloads[0][0] == "insights"
    assert cached_payloads[0][1] == "new_for_you:u1"


def test_new_for_you_endpoint_schedules_job_on_cache_miss(monkeypatch, client_factory, db_session):
    """With enough artists and no cache, the endpoint returns pending + a job id
    instead of blocking on Last.fm."""
    db_session.add(_session("u1"))
    for i in range(5):
        song = _song(db_session, artist_name=f"Seed Artist {i}", title=f"Seed Track {i}", spotify_id=f"seed-{i}")
        _history(db_session, "u1", song, datetime(2026, 5, i + 1, 10, 0))
    db_session.commit()

    monkeypatch.setattr(insights_routes, "get_cached_response", lambda provider, key: None)
    # Discovery must NOT run synchronously on the request path.
    monkeypatch.setattr(
        insights_routes, "discover_songs_from_artist",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Last.fm called on request path")),
    )

    client = client_factory(insights_routes.router)
    resp = client.get("/insights/new-for-you", headers={"X-User-Id": "u1"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["job_id"]
    assert data["items"] == []


def test_new_for_you_returns_cached_result_ready(monkeypatch, client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()

    monkeypatch.setattr(
        insights_routes, "get_cached_response",
        lambda provider, key: {"payload": {"items": [{"title": "Cached"}], "distinct_artist_count": 9}},
    )

    client = client_factory(insights_routes.router)
    resp = client.get("/insights/new-for-you", headers={"X-User-Id": "u1"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["items"][0]["title"] == "Cached"


def test_new_for_you_requires_five_artists(monkeypatch, client_factory, db_session):
    db_session.add(_session("u1"))
    song = _song(db_session, artist_name="Only Artist", title="Only Track")
    _history(db_session, "u1", song, datetime(2026, 5, 1, 10, 0))
    db_session.commit()

    monkeypatch.setattr(insights_routes, "get_cached_response", lambda provider, key: None)
    monkeypatch.setattr(insights_routes, "store_cached_response", lambda *args, **kwargs: None)

    client = client_factory(insights_routes.router)
    resp = client.get("/insights/new-for-you", headers={"X-User-Id": "u1"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["distinct_artist_count"] == 1
    assert data["status"] == "ready"


def test_taste_profile_summarizes_tags_and_genres(client_factory, db_session):
    db_session.add(_session("u1"))
    s1 = _song(db_session, artist_name="Taste A", title="Taste 1", genre="indie")
    s2 = _song(db_session, artist_name="Taste B", title="Taste 2", genre="ambient")
    _tag_song(db_session, s1, "post-punk", weight=3)
    _tag_song(db_session, s2, "ambient", weight=1)
    _history(db_session, "u1", s1, datetime(2026, 5, 1, 10, 0))
    _history(db_session, "u1", s2, datetime(2026, 5, 2, 10, 0))
    db_session.commit()

    client = client_factory(insights_routes.router)
    resp = client.get("/insights/taste-profile", headers={"X-User-Id": "u1"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["profile_strength"] == "building"
    assert data["total_tagged_songs"] == 2
    assert data["top_tags"][0] == {"name": "post-punk", "pct": 75}
    assert {item["name"] for item in data["top_genres"]} == {"indie", "ambient"}


# ── /insights/feedback & feedback-summary ────────────────────────────────────

def test_feedback_invalid_action_rejected(client_factory, db_session):
    db_session.add(_session("u1"))
    s = _song(db_session, artist_name="Fb Artist", title="Fb Track")
    db_session.commit()

    client = client_factory(insights_routes.router)
    resp = client.post(
        "/insights/feedback",
        json={"song_id": s.id, "action": "unknown_action"},
        headers={"X-User-Id": "u1"},
    )
    assert resp.status_code == 400


def test_feedback_summary_aggregates_counts(client_factory, db_session):
    db_session.add(_session("u1"))
    s = _song(db_session, artist_name="Summ Artist", title="Summ Track")
    db_session.add_all([
        RecommendationFeedback(user_id="u1", song_id=s.id, action="like"),
        RecommendationFeedback(user_id="u1", song_id=s.id, action="like"),
        RecommendationFeedback(user_id="u1", song_id=s.id, action="dislike"),
    ])
    db_session.commit()

    client = client_factory(insights_routes.router)
    resp = client.get("/insights/feedback-summary", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    by_action = {r["action"]: r["count"] for r in resp.json()["summary"]}
    assert by_action["like"] == 2
    assert by_action["dislike"] == 1


def test_feedback_summary_empty_for_new_user(client_factory, db_session):
    db_session.add(_session("new-user"))
    db_session.commit()
    client = client_factory(insights_routes.router)
    resp = client.get("/insights/feedback-summary", headers={"X-User-Id": "new-user"})
    assert resp.status_code == 200
    assert resp.json()["summary"] == []


def test_feedback_history_can_remove_one_or_reset_all(client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.add(_session("u2"))
    song = _song(db_session, artist_name="History Artist", title="History Track")
    own_one = RecommendationFeedback(user_id="u1", song_id=song.id, action="like")
    own_two = RecommendationFeedback(user_id="u1", song_id=song.id, action="skip")
    other = RecommendationFeedback(user_id="u2", song_id=song.id, action="dislike")
    db_session.add_all([own_one, own_two, other])
    db_session.commit()
    own_one_id = own_one.id
    other_id = other.id

    client = client_factory(insights_routes.router)
    history = client.get("/insights/feedback-history", headers={"X-User-Id": "u1"})
    assert history.status_code == 200
    assert history.json()["total"] == 2
    assert history.json()["items"][0]["song"]["artist"] == "History Artist"

    assert client.delete(f"/insights/feedback/{other_id}", headers={"X-User-Id": "u1"}).status_code == 404
    assert client.delete(f"/insights/feedback/{own_one_id}", headers={"X-User-Id": "u1"}).status_code == 200
    reset = client.delete("/insights/feedback", headers={"X-User-Id": "u1"})
    assert reset.status_code == 200
    assert reset.json()["deleted"] == 1
    assert db_session.query(RecommendationFeedback).filter_by(user_id="u2").count() == 1


# ── /insights/goals & goals-status ───────────────────────────────────────────

def test_create_goal_and_list_status(client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()

    client = client_factory(insights_routes.router)
    create_resp = client.post(
        "/insights/goals",
        json={"goal_type": "new_songs_per_week", "target_value": 10, "period": "weekly"},
        headers={"X-User-Id": "u1"},
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["goal_id"]

    status_resp = client.get("/insights/goals-status", headers={"X-User-Id": "u1"})
    assert status_resp.status_code == 200
    goals = status_resp.json()["goals"]
    assert len(goals) == 1
    assert goals[0]["goal_type"] == "new_songs_per_week"
    assert goals[0]["target"] == 10
    assert goals[0]["progress"] >= 0


def test_goals_status_listening_days_type(client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.add(ListeningGoal(
        user_id="u1",
        goal_type="listening_days_per_week",
        target_value=5,
        period="weekly",
        active=True,
    ))
    db_session.commit()

    client = client_factory(insights_routes.router)
    resp = client.get("/insights/goals-status", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    goals = resp.json()["goals"]
    assert goals[0]["goal_type"] == "listening_days_per_week"


def test_goals_status_repeat_rate_type(client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.add(ListeningGoal(
        user_id="u1",
        goal_type="repeat_rate_max",
        target_value=30,
        period="weekly",
        active=True,
    ))
    db_session.commit()

    client = client_factory(insights_routes.router)
    resp = client.get("/insights/goals-status", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    goals = resp.json()["goals"]
    assert goals[0]["goal_type"] == "repeat_rate_max"
    assert goals[0]["status"] == "on_track"


def test_goal_counts_only_first_time_songs_in_period(client_factory, db_session):
    now = utcnow_naive()
    db_session.add(_session("u1"))
    old_song = _song(db_session, artist_name="Goal Artist", title="Old Song")
    new_song = _song(db_session, artist_name="Goal Artist", title="New Song")
    db_session.add_all([
        ListeningHistory(user_id="u1", song_id=old_song.id, played_at=now - timedelta(days=30)),
        ListeningHistory(user_id="u1", song_id=old_song.id, played_at=now),
        ListeningHistory(user_id="u1", song_id=new_song.id, played_at=now),
        ListeningGoal(user_id="u1", goal_type="new_songs_per_week", target_value=1, period="weekly", active=True),
    ])
    db_session.commit()

    client = client_factory(insights_routes.router)
    response = client.get("/insights/goals-status", headers={"X-User-Id": "u1"})
    assert response.json()["goals"][0]["progress"] == 1


def test_goal_validation_and_pause_resume(client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()
    client = client_factory(insights_routes.router)

    invalid = client.post(
        "/insights/goals",
        json={"goal_type": "unsupported", "target_value": 5, "period": "yearly"},
        headers={"X-User-Id": "u1"},
    )
    assert invalid.status_code == 400

    created = client.post(
        "/insights/goals",
        json={"goal_type": "listening_days_per_week", "target_value": 3, "period": "monthly"},
        headers={"X-User-Id": "u1"},
    )
    goal_id = created.json()["goal_id"]
    paused = client.patch(
        f"/insights/goals/{goal_id}",
        json={"active": False, "target_value": 4},
        headers={"X-User-Id": "u1"},
    )
    assert paused.status_code == 200
    assert paused.json()["active"] is False
    status = client.get("/insights/goals-status", headers={"X-User-Id": "u1"}).json()["goals"][0]
    assert status["active"] is False
    assert status["target"] == 4


# ── /insights/data-quality ───────────────────────────────────────────────────

def test_data_quality_returns_coverage_metrics(client_factory, db_session):
    db_session.add(_session("u1"))
    s1 = _song(db_session, artist_name="DQ Artist", title="DQ Song 1",
               genre="electronic", spotify_id="dq1", enrichment_status="complete")
    s2 = _song(db_session, artist_name="DQ Artist", title="DQ Song 2",
               genre=None, spotify_id=None, enrichment_status="failed")
    _tag_song(db_session, s1, "techno")
    _history(db_session, "u1", s1, datetime(2026, 5, 1, 12, 0))
    _history(db_session, "u1", s2, datetime(2026, 5, 2, 12, 0))
    db_session.commit()

    client = client_factory(insights_routes.router)
    resp = client.get("/insights/data-quality", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_songs"] == 2
    assert "coverage" in data
    assert "enrichment_status" in data
    assert "missing" in data
    # One song has a tag, one doesn't
    assert data["missing"]["tags"] == 1


def test_data_quality_requires_auth(client_factory, db_session):
    client = client_factory(insights_routes.router)
    resp = client.get("/insights/data-quality")
    assert resp.status_code == 401


# ── /insights/cache/clear ────────────────────────────────────────────────────

def test_clear_cache_calls_provider_clear(monkeypatch, client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()

    cleared_providers = []

    def _fake_clear(provider: str) -> int:
        cleared_providers.append(provider)
        return 3

    monkeypatch.setattr(insights_routes, "clear_provider_cache", _fake_clear)

    client = client_factory(insights_routes.router)
    resp = client.post("/insights/cache/clear?provider=lastfm", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    assert resp.json()["cleared"] == 3
    assert "lastfm" in cleared_providers


# ── /insights/dedup-apply dry_run ────────────────────────────────────────────

def test_dedup_apply_dry_run_does_not_commit(client_factory, db_session):
    db_session.add_all([_session("u1"), _session("u2")])
    a = _artist(db_session, "Dry Run Artist")

    def _dup_song(title):
        s = Song(title=title, artist_id=a.id, is_deleted=False)
        db_session.add(s)
        db_session.flush()
        return s

    keep = _dup_song("Same Song")
    dup = _dup_song("Same Song (Live)")
    _history(db_session, "u1", keep, datetime(2026, 5, 1, 9, 0))
    _history(db_session, "u1", dup, datetime(2026, 5, 1, 10, 0))
    db_session.commit()

    client = client_factory(insights_routes.router)
    resp = client.post(
        "/insights/dedup-apply?dry_run=true",
        headers={"X-User-Id": "u1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["groups"] >= 1

    # dry_run must not mark any songs deleted
    db_session.refresh(dup)
    assert dup.is_deleted is False
