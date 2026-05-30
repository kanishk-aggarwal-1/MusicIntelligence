from datetime import datetime
from functools import partial

from backend.app.models.artist import Artist
from backend.app.models.generated_playlist import GeneratedPlaylist
from backend.app.models.job import Job
from backend.app.models.listening_history import ListeningHistory
from backend.app.models.song import Song
from backend.app.models.song_tag import SongTag
from backend.app.models.tag import Tag
from backend.app.models.user_session import UserSession
from backend.app.models.recommendation_feedback import RecommendationFeedback
from backend.app.routes import dashboard_routes, discovery_routes, insights_routes, music_routes, playlist_routes
from backend.app.services import api_cache_service, discovery_workflow_service, enrichment_service, job_service, recommendation_service
from backend.app.services.api_cache_service import get_cached_response, store_cached_response
from backend.app.services.job_service import create_job, get_job, run_job
from backend.app.services.recommendation_service import _apply_enrichment, recommend_songs, sync_listening_history
from backend.app.routes.playlist_routes import _enforce_known_ratio


def _user_session(user_id: str):
    return UserSession(user_id=user_id, token="token", token_info_json="{}")


def _song_with_tag(db, *, artist_name: str, title: str, tag_name: str, spotify_id: str | None = None, genre: str | None = None, popularity: float = 1.0):
    artist = db.query(Artist).filter_by(name=artist_name).first()
    if not artist:
        artist = Artist(name=artist_name)
        db.add(artist)
        db.flush()

    tag = db.query(Tag).filter_by(name=tag_name).first()
    if not tag:
        tag = Tag(name=tag_name)
        db.add(tag)
        db.flush()

    song = Song(
        title=title,
        artist_id=artist.id,
        spotify_id=spotify_id,
        genre=genre,
        popularity_score=popularity,
        enrichment_status="complete",
        is_deleted=False,
    )
    db.add(song)
    db.flush()
    db.add(SongTag(song_id=song.id, tag_id=tag.id))
    db.flush()
    return song


def test_api_cache_persists_success_and_failure(testing_session_local, monkeypatch):
    monkeypatch.setattr(api_cache_service, "SessionLocal", testing_session_local)

    store_cached_response("lastfm", "track:good", payload={"name": "Song"}, status_code=200)
    cached = get_cached_response("lastfm", "track:good")
    assert cached["status_code"] == 200
    assert cached["payload"] == {"name": "Song"}

    store_cached_response("lastfm", "track:bad", payload=None, status_code=503, error="temporary failure")
    failed = get_cached_response("lastfm", "track:bad")
    assert failed["status_code"] == 503
    assert failed["error"] == "temporary failure"


def test_job_service_records_result(testing_session_local, db_session, monkeypatch):
    monkeypatch.setattr(job_service, "SessionLocal", testing_session_local)
    job_service.record_job.__globals__["METRICS"]["jobs"].clear()
    job = create_job(db_session, user_id="user-1", job_type="sync_history", progress_total=2)

    def _handler(db, progress):
        progress.update(current=1, total=2, message="Halfway")
        return {"message": "Done", "progress_current": 2, "progress_total": 2, "rows": 7}

    run_job(job.id, _handler)
    db_session.expire_all()
    stored = get_job(db_session, job_id=job.id, user_id="user-1")
    assert stored.status == "succeeded"
    assert "rows" in stored.result_json
    assert job_service.record_job.__globals__["METRICS"]["jobs"]["queued"] == 1
    assert job_service.record_job.__globals__["METRICS"]["jobs"]["running"] == 1
    assert job_service.record_job.__globals__["METRICS"]["jobs"]["succeeded"] == 1


def test_sync_history_normalizes_timezone_and_prevents_duplicates(db_session):
    db_session.add(_user_session("user-1"))
    db_session.commit()

    first = sync_listening_history(
        db_session,
        "user-1",
        [{"title": "Midnight Song", "artist": "Clockwork", "spotify_id": "sp-1", "played_at": "2026-05-01T23:30:00-04:00"}],
    )
    second = sync_listening_history(
        db_session,
        "user-1",
        [{"title": "Midnight Song", "artist": "Clockwork", "spotify_id": "sp-1", "played_at": "2026-05-02T03:30:00Z"}],
    )

    assert first["new_history_rows"] == 1
    assert second["existing_history_rows"] == 1
    stored = db_session.query(ListeningHistory).one()
    assert stored.played_at == datetime(2026, 5, 2, 3, 30)


def test_sync_history_deduplicates_items_within_same_batch(db_session):
    db_session.add(_user_session("user-1"))
    db_session.commit()

    result = sync_listening_history(
        db_session,
        "user-1",
        [
            {"title": "Repeated Song", "artist": "Loop Artist", "spotify_id": "loop-1", "played_at": "2026-05-02T03:30:00Z"},
            {"title": "Repeated Song", "artist": "Loop Artist", "spotify_id": "loop-1", "played_at": "2026-05-02T03:30:00Z"},
        ],
    )

    assert result["new_history_rows"] == 1
    assert result["existing_history_rows"] == 1
    assert db_session.query(ListeningHistory).count() == 1


def test_dashboard_stats_are_user_scoped(client_factory, db_session):
    db_session.add_all([_user_session("user-1"), _user_session("user-2")])
    song_a = _song_with_tag(db_session, artist_name="A", title="Song A", tag_name="indie", spotify_id="a1")
    song_b = _song_with_tag(db_session, artist_name="B", title="Song B", tag_name="rock", spotify_id="b1")
    db_session.add_all(
        [
            ListeningHistory(user_id="user-1", song_id=song_a.id, played_at=datetime(2026, 5, 1, 12, 0)),
            ListeningHistory(user_id="user-1", song_id=song_a.id, played_at=datetime(2026, 5, 2, 12, 0)),
            ListeningHistory(user_id="user-2", song_id=song_b.id, played_at=datetime(2026, 5, 2, 12, 0)),
        ]
    )
    db_session.commit()

    client = client_factory(dashboard_routes.router)
    response = client.get("/dashboard/stats?days=30", headers={"X-User-Id": "user-1"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_plays"] == 2
    assert payload["top_artists"][0]["artist"] == "A"


def test_dedup_preview_apply_and_undo_are_user_scoped(client_factory, db_session):
    db_session.add_all([_user_session("user-1"), _user_session("user-2")])
    keep = _song_with_tag(db_session, artist_name="Dup Artist", title="Same Song", tag_name="pop", spotify_id="dup-1")
    dup = _song_with_tag(db_session, artist_name="Dup Artist", title="Same Song (Live)", tag_name="pop", spotify_id="dup-2")
    other_user_song = _song_with_tag(db_session, artist_name="Dup Artist", title="Same Song - Remix", tag_name="pop", spotify_id="dup-3")
    db_session.add_all(
        [
            ListeningHistory(user_id="user-1", song_id=keep.id, played_at=datetime(2026, 5, 1, 10, 0)),
            ListeningHistory(user_id="user-1", song_id=dup.id, played_at=datetime(2026, 5, 1, 11, 0)),
            ListeningHistory(user_id="user-2", song_id=other_user_song.id, played_at=datetime(2026, 5, 1, 12, 0)),
        ]
    )
    db_session.commit()

    client = client_factory(insights_routes.router)
    preview = client.get("/insights/dedup-preview", headers={"X-User-Id": "user-1"})
    assert preview.status_code == 200
    groups = preview.json()["duplicate_groups"]
    assert len(groups) == 1
    assert groups[0]["count"] == 2

    applied = client.post("/insights/dedup-apply?limit_groups=10", headers={"X-User-Id": "user-1"})
    assert applied.status_code == 200
    batch_id = applied.json()["batch_id"]
    db_session.refresh(dup)
    db_session.refresh(other_user_song)
    assert dup.is_deleted is True
    assert other_user_song.is_deleted is False

    undone = client.post(f"/insights/dedup-undo/{batch_id}", headers={"X-User-Id": "user-1"})
    assert undone.status_code == 200
    db_session.refresh(dup)
    assert dup.is_deleted is False


def test_playlist_preview_saves_history_without_mutating_songs(client_factory, db_session):
    db_session.add(_user_session("user-1"))
    known = _song_with_tag(db_session, artist_name="Preview Artist", title="Known Track", tag_name="chill", spotify_id="known-1", genre="chill", popularity=2.5)
    unknown = _song_with_tag(db_session, artist_name="Preview Artist", title="Unknown Track", tag_name="chill", spotify_id=None, genre="chill", popularity=3.5)
    extra = _song_with_tag(db_session, artist_name="Other Artist", title="Extra Track", tag_name="ambient", spotify_id="known-2", genre="ambient", popularity=1.8)
    db_session.add_all(
        [
            ListeningHistory(user_id="user-1", song_id=known.id, played_at=datetime(2026, 5, 3, 9, 0)),
            ListeningHistory(user_id="user-1", song_id=unknown.id, played_at=datetime(2026, 5, 4, 9, 0)),
            ListeningHistory(user_id="user-1", song_id=extra.id, played_at=datetime(2026, 5, 5, 9, 0)),
        ]
    )
    db_session.commit()

    before_song_count = db_session.query(Song).count()
    client = client_factory(playlist_routes.router)
    response = client.post(
        "/playlists/preview",
        json={"max_tracks": 2, "min_known_ratio": 0.5, "diversity": 0.5, "familiarity": 0.5},
        headers={"X-User-Id": "user-1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["generated_playlist"]["tracks"]
    assert db_session.query(Song).count() == before_song_count
    assert db_session.query(GeneratedPlaylist).count() == 1


def test_min_known_ratio_reorders_known_tracks():
    artist = Artist(name="Ratio Artist")
    known_song = Song(title="Known", artist=artist, spotify_id="known", is_deleted=False)
    unknown_song = Song(title="Unknown", artist=artist, spotify_id=None, is_deleted=False)
    known_song_2 = Song(title="Known 2", artist=artist, spotify_id="known-2", is_deleted=False)

    details = [
        {"song": unknown_song, "score": 0.99},
        {"song": known_song, "score": 0.85},
        {"song": known_song_2, "score": 0.8},
    ]
    reordered = _enforce_known_ratio(details, max_tracks=2, min_known_ratio=1.0)
    assert reordered[0]["song"].spotify_id is not None
    assert reordered[1]["song"].spotify_id is not None


def test_enrichment_failure_sets_failed_status(monkeypatch, db_session):
    song = _song_with_tag(db_session, artist_name="Fail Artist", title="Fail Song", tag_name="starter", spotify_id=None, genre=None, popularity=0)
    song.genre = None
    song.enrichment_status = "pending"
    db_session.commit()

    monkeypatch.setattr(enrichment_service, "get_track_tags", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("tags failed")))
    monkeypatch.setattr(enrichment_service, "get_artist_tags", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("artist tags failed")))
    monkeypatch.setattr(enrichment_service, "get_track_info", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("track info failed")))

    payload = enrichment_service.enrich_song(song)
    song.song_tags.clear()
    changed = _apply_enrichment(db_session, song, payload)
    assert changed == 0
    assert song.enrichment_status == "failed"
    assert "tags failed" in song.enrichment_error


def test_playlist_preview_requires_login(client_factory, db_session):
    client = client_factory(playlist_routes.router)
    response = client.post("/playlists/preview", json={"max_tracks": 2})
    assert response.status_code == 401


def test_feedback_accepts_new_actions(client_factory, db_session):
    db_session.add(_user_session("user-1"))
    song = _song_with_tag(db_session, artist_name="Feedback Artist", title="Feedback Song", tag_name="indie", spotify_id="fb-1")
    db_session.commit()

    client = client_factory(insights_routes.router)
    response = client.post(
        "/insights/feedback",
        json={"song_id": song.id, "action": "too_familiar"},
        headers={"X-User-Id": "user-1"},
    )
    assert response.status_code == 200
    assert response.json()["action"] == "too_familiar"


def test_too_familiar_feedback_penalizes_overplayed_song(db_session):
    artist = Artist(name="Feedback Bias Artist")
    favored = Song(title="Favored", artist=artist, spotify_id="fav-1", is_deleted=False)
    fresher = Song(title="Fresher", artist=artist, spotify_id="fresh-1", is_deleted=False)
    db_session.add_all([artist, favored, fresher])
    db_session.flush()

    indie = Tag(name="indie")
    db_session.add(indie)
    db_session.flush()
    db_session.add_all([
        SongTag(song_id=favored.id, tag_id=indie.id),
        SongTag(song_id=fresher.id, tag_id=indie.id),
    ])

    for hour in range(6):
        db_session.add(ListeningHistory(user_id="user-1", song_id=favored.id, played_at=datetime(2026, 5, 1, hour, 0)))
    db_session.add(ListeningHistory(user_id="user-1", song_id=fresher.id, played_at=datetime(2026, 5, 2, 10, 0)))
    db_session.add(RecommendationFeedback(user_id="user-1", song_id=favored.id, action="too_familiar"))
    db_session.commit()

    details = recommend_songs(db_session, "user-1", return_details=True, allow_discovery=False, limit=2)
    assert details[0]["song"].title == "Fresher"
    assert details[0]["score"] > details[1]["score"]


def test_song_detail_and_hide_restore(client_factory, db_session):
    db_session.add(_user_session("user-1"))
    song = _song_with_tag(db_session, artist_name="Control Artist", title="Control Song", tag_name="electronic", spotify_id="ctl-1")
    db_session.add(ListeningHistory(user_id="user-1", song_id=song.id, played_at=datetime(2026, 5, 5, 10, 0)))
    db_session.commit()

    client = client_factory(music_routes.router)
    detail = client.get(f"/songs/{song.id}", headers={"X-User-Id": "user-1"})
    assert detail.status_code == 200
    assert detail.json()["listening_count"] == 1

    hidden = client.post(f"/songs/{song.id}/hide", headers={"X-User-Id": "user-1"})
    assert hidden.status_code == 200
    db_session.refresh(song)
    assert song.is_deleted is True

    restored = client.post(f"/songs/{song.id}/restore", headers={"X-User-Id": "user-1"})
    assert restored.status_code == 200
    db_session.refresh(song)
    assert song.is_deleted is False


def test_discovery_preview_and_accept(monkeypatch, client_factory, db_session):
    db_session.add(_user_session("user-1"))
    seed_song = _song_with_tag(db_session, artist_name="Seed Artist", title="Seed Track", tag_name="indie", spotify_id="seed-1")
    db_session.add(ListeningHistory(user_id="user-1", song_id=seed_song.id, played_at=datetime(2026, 5, 5, 10, 0)))
    db_session.commit()

    monkeypatch.setattr(discovery_workflow_service, "discover_songs_from_artist", lambda artist_name: [
        {"title": "Found Track", "artist": "Found Artist", "discovery_source": "lastfm_top_tracks", "discovery_confidence": 0.7}
    ])

    preview = discovery_workflow_service.build_discovery_preview(db_session, "user-1", seed_limit=1, max_candidates=10)
    assert preview["candidate_count"] == 1

    job = Job(
        id="job-discovery-1",
        user_id="user-1",
        job_type="discovery_preview",
        status="succeeded",
        result_json='{\"candidates\":[{\"candidate_id\":1,\"title\":\"Found Track\",\"artist\":\"Found Artist\",\"discovery_source\":\"lastfm_top_tracks\",\"discovery_confidence\":0.7}]}',
    )
    db_session.add(job)
    db_session.commit()

    monkeypatch.setattr(discovery_workflow_service, "store_discovered_songs", lambda db, selected, user_id=None, limit=None: {"store_attempted": len(selected), "store_rate_limited": False})

    client = client_factory(discovery_routes.router)
    accepted = client.post(
        "/discoveries/accept",
        json={"job_id": "job-discovery-1", "candidate_ids": [1]},
        headers={"X-User-Id": "user-1"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["accepted"] == 1
