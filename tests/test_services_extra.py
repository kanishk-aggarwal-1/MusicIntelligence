"""Additional service-level tests targeting uncovered paths."""
from datetime import datetime

from backend.app.models.api_cache import ApiCache
from backend.app.models.artist import Artist
from backend.app.models.job import Job
from backend.app.models.listening_history import ListeningHistory
from backend.app.models.recommendation_feedback import RecommendationFeedback
from backend.app.models.song import Song
from backend.app.models.song_tag import SongTag
from backend.app.models.tag import Tag
from backend.app.models.user_session import UserSession
from backend.app.services import api_cache_service, job_service, recommendation_service
from backend.app.services.api_cache_service import (
    clear_provider_cache,
    get_cached_response,
    store_cached_response,
)
from backend.app.services.job_service import (
    cancel_job,
    create_job,
    get_active_job,
    get_job,
    list_jobs,
    run_job,
)
from backend.app.services.recommendation_service import (
    backfill_missing_metadata,
    build_discovery_feed,
    build_song_vector,
    build_user_profile,
    discover_new_songs,
    recommend_songs,
    sync_listening_history,
)
from backend.app.services import enrichment_service


def _session(user_id: str):
    return UserSession(user_id=user_id, token="tok", token_info_json="{}")


def _artist(db, name: str) -> Artist:
    a = db.query(Artist).filter_by(name=name).first()
    if not a:
        a = Artist(name=name)
        db.add(a)
        db.flush()
    return a


def _song_with_tag(db, *, artist_name: str, title: str, tag_name: str,
                   spotify_id: str | None = None, genre: str | None = None) -> Song:
    artist = _artist(db, artist_name)
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
        enrichment_status="complete",
        is_deleted=False,
        popularity_score=1.0,
    )
    db.add(song)
    db.flush()
    db.add(SongTag(song_id=song.id, tag_id=tag.id))
    db.flush()
    return song


# ── job_service ───────────────────────────────────────────────────────────────

def test_list_jobs_returns_user_jobs(testing_session_local, db_session):
    db_session.add(_session("u1"))
    create_job(db_session, user_id="u1", job_type="sync_history", progress_total=10)
    create_job(db_session, user_id="u1", job_type="enrichment", progress_total=5)
    db_session.commit()

    jobs = list_jobs(db_session, user_id="u1", limit=10)
    assert len(jobs) == 2
    types = {j.job_type for j in jobs}
    assert "sync_history" in types
    assert "enrichment" in types


def test_list_jobs_scoped_to_user(testing_session_local, db_session):
    create_job(db_session, user_id="u1", job_type="sync_history")
    create_job(db_session, user_id="u2", job_type="sync_history")
    db_session.commit()

    jobs = list_jobs(db_session, user_id="u1")
    assert all(j.user_id == "u1" for j in jobs)


def test_cancel_job_sets_cancelled(testing_session_local, db_session, monkeypatch):
    monkeypatch.setattr(job_service, "SessionLocal", testing_session_local)
    job = create_job(db_session, user_id="u1", job_type="sync_history")
    db_session.commit()

    result = cancel_job(db_session, job_id=job.id, user_id="u1")
    assert result.status == "cancelled"


def test_cancel_job_not_found_returns_none(testing_session_local, db_session):
    result = cancel_job(db_session, job_id="nonexistent-id", user_id="u1")
    assert result is None


def test_cancel_already_finished_job_is_noop(testing_session_local, db_session, monkeypatch):
    monkeypatch.setattr(job_service, "SessionLocal", testing_session_local)
    job = create_job(db_session, user_id="u1", job_type="sync_history")
    job.status = "succeeded"
    db_session.commit()

    result = cancel_job(db_session, job_id=job.id, user_id="u1")
    assert result.status == "succeeded"


def test_run_job_records_failure(testing_session_local, db_session, monkeypatch):
    monkeypatch.setattr(job_service, "SessionLocal", testing_session_local)
    job = create_job(db_session, user_id="u1", job_type="sync_history")
    db_session.commit()

    def _failing_handler(db, progress):
        raise ValueError("simulated failure")

    run_job(job.id, _failing_handler)
    db_session.expire_all()
    stored = get_job(db_session, job_id=job.id, user_id="u1")
    assert stored.status == "failed"
    assert "simulated failure" in stored.error


def test_get_job_without_user_id_filter(testing_session_local, db_session):
    job = create_job(db_session, user_id="u1", job_type="enrichment")
    db_session.commit()

    result = get_job(db_session, job_id=job.id)
    assert result is not None
    assert result.user_id == "u1"


def test_get_active_job_returns_latest_queued_or_running(db_session):
    old = create_job(db_session, user_id="u1", job_type="sync_history")
    old.status = "succeeded"
    queued = create_job(db_session, user_id="u1", job_type="sync_history")
    running = create_job(db_session, user_id="u1", job_type="sync_history")
    running.status = "running"
    other_user = create_job(db_session, user_id="u2", job_type="sync_history")
    db_session.commit()

    result = get_active_job(db_session, user_id="u1", job_type="sync_history")

    assert result.id == running.id
    assert result.id not in {old.id, other_user.id}


# ── recommendation_service: build_discovery_feed ─────────────────────────────

def test_build_discovery_feed_empty_history(db_session):
    db_session.add(_session("u1"))
    db_session.commit()
    result = build_discovery_feed(db_session, "u1", limit=10)
    assert isinstance(result, list)


def test_build_discovery_feed_with_history(db_session):
    db_session.add(_session("u1"))
    s1 = _song_with_tag(db_session, artist_name="Feed A", title="Feed S1", tag_name="indie", spotify_id="f1")
    s2 = _song_with_tag(db_session, artist_name="Feed B", title="Feed S2", tag_name="rock", spotify_id="f2")
    db_session.add_all([
        ListeningHistory(user_id="u1", song_id=s1.id, played_at=datetime(2026, 5, 1, 10, 0)),
        ListeningHistory(user_id="u1", song_id=s2.id, played_at=datetime(2026, 5, 2, 10, 0)),
    ])
    db_session.commit()

    result = build_discovery_feed(db_session, "u1", limit=10)
    assert isinstance(result, list)
    # Feed items should include song fields
    for item in result:
        assert "song_id" in item or "title" in item


# ── recommendation_service: recommend_songs with context ─────────────────────

def test_recommend_songs_with_context_type(db_session):
    db_session.add(_session("u1"))
    s1 = _song_with_tag(db_session, artist_name="Ctx A", title="Focus S1", tag_name="electronic", spotify_id="c1")
    s2 = _song_with_tag(db_session, artist_name="Ctx B", title="Focus S2", tag_name="ambient", spotify_id="c2")
    db_session.add_all([
        ListeningHistory(user_id="u1", song_id=s1.id, played_at=datetime(2026, 5, 1, 10, 0)),
        ListeningHistory(user_id="u1", song_id=s2.id, played_at=datetime(2026, 5, 2, 10, 0)),
    ])
    db_session.commit()

    result = recommend_songs(db_session, "u1", context_type="focus", allow_discovery=False, limit=5)
    assert isinstance(result, list)


def test_discover_new_songs_ignores_lastfm_artist_failures(monkeypatch, db_session):
    db_session.add(_session("u1"))
    song = _song_with_tag(
        db_session,
        artist_name="Failing Discovery Artist",
        title="Discovery Seed",
        tag_name="indie",
        spotify_id="disc-fail-1",
    )
    db_session.add(ListeningHistory(user_id="u1", song_id=song.id, played_at=datetime(2026, 5, 1, 10, 0)))
    db_session.commit()

    def _failing_discovery(*args, **kwargs):
        raise RuntimeError("lastfm unavailable")

    monkeypatch.setattr(recommendation_service, "discover_songs_from_artist", _failing_discovery)

    result, summary = discover_new_songs(db_session, "u1", include_summary=True)

    assert result == []
    assert summary["seed_artists"] == 1


def test_recommend_songs_excludes_never_show(db_session):
    db_session.add(_session("u1"))
    s1 = _song_with_tag(db_session, artist_name="Excl A", title="Never Show Song", tag_name="pop", spotify_id="n1")
    s2 = _song_with_tag(db_session, artist_name="Excl B", title="Normal Song", tag_name="pop", spotify_id="n2")
    db_session.add_all([
        ListeningHistory(user_id="u1", song_id=s1.id, played_at=datetime(2026, 5, 1, 10, 0)),
        ListeningHistory(user_id="u1", song_id=s2.id, played_at=datetime(2026, 5, 2, 10, 0)),
    ])
    db_session.add(RecommendationFeedback(user_id="u1", song_id=s1.id, action="never_show"))
    db_session.commit()

    details = recommend_songs(db_session, "u1", return_details=True, allow_discovery=False, limit=10)
    titles = [d["song"].title for d in details]
    assert "Never Show Song" not in titles


def test_recommend_songs_discovery_disabled(db_session):
    db_session.add(_session("u1"))
    s1 = _song_with_tag(db_session, artist_name="Excl2 A", title="Excl Song A", tag_name="jazz", spotify_id="e1")
    s2 = _song_with_tag(db_session, artist_name="Excl2 B", title="Excl Song B", tag_name="jazz", spotify_id="e2")
    db_session.add_all([
        ListeningHistory(user_id="u1", song_id=s1.id, played_at=datetime(2026, 5, 1, 10, 0)),
        ListeningHistory(user_id="u1", song_id=s2.id, played_at=datetime(2026, 5, 2, 10, 0)),
    ])
    db_session.commit()

    # allow_discovery=False skips lastfm discovery path
    details = recommend_songs(db_session, "u1", return_details=True, allow_discovery=False, limit=10)
    assert isinstance(details, list)


def test_recommend_songs_more_like_this_feedback(db_session):
    db_session.add(_session("u1"))
    s1 = _song_with_tag(db_session, artist_name="MLT A", title="More Like This", tag_name="blues", spotify_id="m1")
    s2 = _song_with_tag(db_session, artist_name="MLT B", title="Companion", tag_name="blues", spotify_id="m2")
    db_session.add_all([
        ListeningHistory(user_id="u1", song_id=s1.id, played_at=datetime(2026, 5, 1, 10, 0)),
        ListeningHistory(user_id="u1", song_id=s2.id, played_at=datetime(2026, 5, 2, 10, 0)),
    ])
    db_session.add(RecommendationFeedback(user_id="u1", song_id=s1.id, action="more_like_this"))
    db_session.commit()

    result = recommend_songs(db_session, "u1", return_details=True, allow_discovery=False, limit=5)
    assert isinstance(result, list)


# ── api_cache_service: update and clear paths ────────────────────────────────

def test_store_cache_updates_existing_entry(testing_session_local, monkeypatch):
    monkeypatch.setattr(api_cache_service, "SessionLocal", testing_session_local)
    store_cached_response("lastfm", "update-key", payload={"v": 1}, status_code=200)
    store_cached_response("lastfm", "update-key", payload={"v": 2}, status_code=200)
    result = get_cached_response("lastfm", "update-key")
    assert result["payload"] == {"v": 2}


def test_clear_provider_cache_removes_entries(testing_session_local, monkeypatch):
    monkeypatch.setattr(api_cache_service, "SessionLocal", testing_session_local)
    store_cached_response("lastfm", "clear-key-1", payload={"a": 1}, status_code=200)
    store_cached_response("lastfm", "clear-key-2", payload={"b": 2}, status_code=200)
    store_cached_response("spotify", "keep-key", payload={"c": 3}, status_code=200)

    deleted = clear_provider_cache("lastfm")
    assert deleted == 2

    assert get_cached_response("lastfm", "clear-key-1") is None
    assert get_cached_response("spotify", "keep-key") is not None


# ── recommendation_service: utility functions ────────────────────────────────

def test_build_user_profile_counts_tags(db_session):
    db_session.add(_session("u1"))
    s1 = _song_with_tag(db_session, artist_name="Prof A", title="Prof T1", tag_name="indie")
    s2 = _song_with_tag(db_session, artist_name="Prof B", title="Prof T2", tag_name="indie")
    s3 = _song_with_tag(db_session, artist_name="Prof C", title="Prof T3", tag_name="rock")
    db_session.add_all([
        ListeningHistory(user_id="u1", song_id=s1.id, played_at=datetime(2026, 5, 1, 10, 0)),
        ListeningHistory(user_id="u1", song_id=s2.id, played_at=datetime(2026, 5, 2, 10, 0)),
        ListeningHistory(user_id="u1", song_id=s3.id, played_at=datetime(2026, 5, 3, 10, 0)),
    ])
    db_session.commit()

    profile = build_user_profile(db_session, "u1")
    assert profile["indie"] == 2
    assert profile["rock"] == 1


def test_build_song_vector_returns_tag_dict(db_session):
    s = _song_with_tag(db_session, artist_name="Vec A", title="Vec T1", tag_name="electronic")
    _tag_extra = db_session.query(Tag).filter_by(name="ambient").first()
    if not _tag_extra:
        _tag_extra = Tag(name="ambient")
        db_session.add(_tag_extra)
        db_session.flush()
    db_session.add(SongTag(song_id=s.id, tag_id=_tag_extra.id))
    db_session.commit()
    db_session.refresh(s)

    vector = build_song_vector(s)
    assert "electronic" in vector
    assert "ambient" in vector
    assert vector["electronic"] == 1


def test_build_song_vector_empty_when_no_tags(db_session):
    artist = _artist(db_session, "No Tags Artist")
    s = Song(title="No Tags", artist_id=artist.id, is_deleted=False, enrichment_status="pending")
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    assert build_song_vector(s) == {}


# ── recommendation_service: backfill_missing_metadata ────────────────────────

def test_backfill_missing_metadata_enriches_pending_songs(monkeypatch, db_session):
    db_session.add(_session("u1"))
    artist = _artist(db_session, "Backfill Artist")
    pending = Song(
        title="Pending Song",
        artist_id=artist.id,
        enrichment_status="pending",
        is_deleted=False,
    )
    db_session.add(pending)
    db_session.flush()
    db_session.add(ListeningHistory(user_id="u1", song_id=pending.id, played_at=datetime(2026, 5, 1, 10, 0)))
    db_session.commit()

    monkeypatch.setattr(
        enrichment_service, "get_track_tags",
        lambda *a, **kw: [{"name": "indie", "count": 100}]
    )
    monkeypatch.setattr(enrichment_service, "get_artist_tags", lambda *a, **kw: [])
    monkeypatch.setattr(enrichment_service, "get_track_info", lambda *a, **kw: {
        "listeners": 5000, "playcount": 20000, "genre": "indie"
    })

    result = backfill_missing_metadata(db_session, user_id="u1", max_songs=10)
    assert result["scanned"] >= 1


def test_backfill_missing_metadata_skips_complete_songs(monkeypatch, db_session):
    db_session.add(_session("u1"))
    # _song_with_tag always creates with enrichment_status="complete"
    s = _song_with_tag(db_session, artist_name="Complete Artist", title="Complete Song", tag_name="rock")
    db_session.add(ListeningHistory(user_id="u1", song_id=s.id, played_at=datetime(2026, 5, 1, 10, 0)))
    db_session.commit()

    result = backfill_missing_metadata(db_session, user_id="u1", max_songs=10)
    assert result["scanned"] == 0


def test_backfill_normalizes_stale_pending_complete_song(db_session):
    db_session.add(_session("u1"))
    artist = _artist(db_session, "Stale Pending Artist")
    tag = Tag(name="already-tagged")
    db_session.add(tag)
    db_session.flush()
    song = Song(
        title="Already Rich",
        artist_id=artist.id,
        genre="indie",
        listeners=100,
        playcount=200,
        enrichment_status="pending",
        is_deleted=False,
    )
    db_session.add(song)
    db_session.flush()
    db_session.add(SongTag(song_id=song.id, tag_id=tag.id))
    db_session.add(ListeningHistory(user_id="u1", song_id=song.id, played_at=datetime(2026, 5, 1, 10, 0)))
    db_session.commit()

    result = backfill_missing_metadata(db_session, user_id="u1", max_songs=10)
    db_session.refresh(song)

    assert result["scanned"] == 0
    assert result["updated"] == 1
    assert song.enrichment_status == "complete"


def test_sync_listening_history_can_skip_inline_enrichment(monkeypatch, db_session):
    def _unexpected_enrichment(song):
        raise AssertionError("inline enrichment should not run")

    monkeypatch.setattr(recommendation_service, "enrich_song", _unexpected_enrichment)

    result = sync_listening_history(
        db_session,
        "u1",
        [{
            "title": "Imported Track",
            "artist": "Imported Artist",
            "spotify_id": "imported-track-id",
            "played_at": "2026-05-01T10:00:00Z",
        }],
        enrich_inline=False,
    )

    song = db_session.query(Song).filter_by(spotify_id="imported-track-id").one()
    history = db_session.query(ListeningHistory).filter_by(user_id="u1", song_id=song.id).one()

    assert result["new_songs"] == 1
    assert result["new_history_rows"] == 1
    assert song.enrichment_status == "pending"
    assert history.played_at == datetime(2026, 5, 1, 10, 0)
