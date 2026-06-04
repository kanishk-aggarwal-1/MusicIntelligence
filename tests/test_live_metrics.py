"""Tests for persistent live metrics (live_metrics_service + GET /stats)."""
from backend.app.models.metric_counter import MetricCounter  # noqa: F401  (register table)
from backend.app.services import live_metrics_service as lm
from backend.app.routes import stats_routes


def _use_test_db(monkeypatch, testing_session_local, test_engine):
    monkeypatch.setattr(lm, "SessionLocal", testing_session_local)
    monkeypatch.setattr(lm, "engine", test_engine)


def test_counters_accumulate_atomically(monkeypatch, testing_session_local, test_engine):
    _use_test_db(monkeypatch, testing_session_local, test_engine)

    for _ in range(5):
        lm.increment(lm.TRACKS_SYNCED, 2)
    lm.increment(lm.TRACKS_SYNCED)  # +1

    counters = lm.get_counters()
    assert counters[lm.TRACKS_SYNCED] == 11


def test_increment_many_single_transaction(monkeypatch, testing_session_local, test_engine):
    _use_test_db(monkeypatch, testing_session_local, test_engine)

    lm.increment_many({lm.CACHE_HITS: 3, lm.CACHE_MISSES: 1, lm.SPOTIFY_CALLS: 2, lm.LASTFM_CALLS: 1})
    lm.increment_many({lm.PLAYLIST_TRACKS_REQUESTED: 10, lm.PLAYLIST_TRACKS_RESOLVED: 8})

    counters = lm.get_counters()
    assert counters[lm.CACHE_HITS] == 3
    assert counters[lm.CACHE_MISSES] == 1
    assert counters[lm.PLAYLIST_TRACKS_RESOLVED] == 8


def test_build_stats_computes_rates(monkeypatch, testing_session_local, test_engine):
    _use_test_db(monkeypatch, testing_session_local, test_engine)

    lm.increment(lm.CACHE_HITS, 3)
    lm.increment(lm.CACHE_MISSES, 1)
    lm.increment_many({lm.SPOTIFY_CALLS: 2, lm.LASTFM_CALLS: 1})
    lm.increment_many({lm.PLAYLIST_TRACKS_REQUESTED: 10, lm.PLAYLIST_TRACKS_RESOLVED: 8})
    lm.increment(lm.PLAYLISTS_GENERATED)

    stats = lm.build_stats()
    assert stats["cache"]["hit_rate_pct"] == 75.0          # 3 / (3+1)
    assert stats["cache"]["api_calls_saved"] == 3          # each hit = a call avoided
    assert stats["cache"]["api_calls_saved_pct"] == 75.0
    assert stats["external_api_calls"]["total"] == 3
    assert stats["playlists"]["generated"] == 1
    assert stats["playlists"]["resolution_rate_pct"] == 80.0  # 8 / 10


def test_build_stats_handles_zero_safely(monkeypatch, testing_session_local, test_engine):
    _use_test_db(monkeypatch, testing_session_local, test_engine)
    stats = lm.build_stats()
    # No division-by-zero when there is no traffic yet.
    assert stats["cache"]["hit_rate_pct"] == 0.0
    assert stats["playlists"]["resolution_rate_pct"] == 0.0


def test_increment_is_fail_open(monkeypatch):
    """A broken DB layer must never raise into live traffic."""
    def _boom():
        raise RuntimeError("db is down")
    monkeypatch.setattr(lm, "SessionLocal", _boom)
    # Must not raise.
    lm.increment(lm.CACHE_HITS)
    lm.increment_many({lm.CACHE_MISSES: 2})
    counters = lm.get_counters()  # also fail-open, returns zeros
    assert counters[lm.CACHE_HITS] == 0


def test_stats_endpoint_is_public_and_non_sensitive(monkeypatch, testing_session_local, test_engine, client_factory):
    _use_test_db(monkeypatch, testing_session_local, test_engine)
    lm.increment(lm.CACHE_HITS, 4)

    client = client_factory(stats_routes.router)
    # No auth headers — endpoint must be publicly readable.
    resp = client.get("/stats")
    assert resp.status_code == 200

    body = resp.json()
    assert body["cache"]["hits"] == 4
    assert "note" in body

    # Guard against leaking anything sensitive in the public payload.
    text = resp.text.lower()
    for forbidden in ("token", "refresh", "secret", "password", "email", "user_id"):
        assert forbidden not in text
