"""Tests for /songs routes (music_routes.py)."""
from datetime import datetime

from backend.app.models.artist import Artist
from backend.app.models.listening_history import ListeningHistory
from backend.app.models.song import Song
from backend.app.models.song_tag import SongTag
from backend.app.models.tag import Tag
from backend.app.models.user_session import UserSession
from backend.app.models.user_song_pref import UserSongPref
from backend.app.models.generated_playlist import GeneratedPlaylist
from backend.app.models.generated_playlist_track import GeneratedPlaylistTrack
from backend.app.routes import music_routes
from backend.app.services import enrichment_service
from backend.app.services.recommendation_service import _apply_enrichment


def _session(user_id: str):
    return UserSession(user_id=user_id, token="tok", token_info_json="{}")


def _artist(db, name: str) -> Artist:
    a = db.query(Artist).filter_by(name=name).first()
    if not a:
        a = Artist(name=name)
        db.add(a)
        db.flush()
    return a


def _song(db, *, artist_name: str, title: str, spotify_id: str | None = None,
          genre: str | None = None, enrichment_status: str = "complete",
          listeners: int = 0, is_deleted: bool = False) -> Song:
    artist = _artist(db, artist_name)
    s = Song(
        title=title,
        artist_id=artist.id,
        spotify_id=spotify_id,
        genre=genre,
        enrichment_status=enrichment_status,
        listeners=listeners,
        is_deleted=is_deleted,
    )
    db.add(s)
    db.flush()
    return s


def _tag(db, song: Song, tag_name: str) -> None:
    t = db.query(Tag).filter_by(name=tag_name).first()
    if not t:
        t = Tag(name=tag_name)
        db.add(t)
        db.flush()
    db.add(SongTag(song_id=song.id, tag_id=t.id))
    db.flush()


def _weighted_tag(db, song: Song, tag_name: str, weight: float) -> None:
    t = db.query(Tag).filter_by(name=tag_name).first()
    if not t:
        t = Tag(name=tag_name)
        db.add(t)
        db.flush()
    db.add(SongTag(song_id=song.id, tag_id=t.id, weight=weight))
    db.flush()


def _history(db, user_id: str, song: Song, played_at=None):
    db.add(ListeningHistory(
        user_id=user_id,
        song_id=song.id,
        played_at=played_at or datetime(2026, 5, 1, 10, 0),
    ))


# ── GET /songs/ ───────────────────────────────────────────────────────────────

def test_songs_list_basic(client_factory, db_session):
    db_session.add(_session("u1"))
    s = _song(db_session, artist_name="Alpha", title="Track A", spotify_id="sp1", genre="indie")
    _history(db_session, "u1", s)
    db_session.commit()

    client = client_factory(music_routes.router)
    resp = client.get("/songs/", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    songs = resp.json()
    assert len(songs) == 1
    assert songs[0]["title"] == "Track A"
    assert songs[0]["artist"] == "Alpha"
    assert songs[0]["genre"] == "indie"
    assert songs[0]["listening_count"] == 1


def test_songs_list_includes_highest_weight_top_tag(client_factory, db_session):
    db_session.add(_session("u1"))
    s = _song(db_session, artist_name="Tagged Alpha", title="Tagged Track")
    _weighted_tag(db_session, s, "low", 1.0)
    _weighted_tag(db_session, s, "high", 5.0)
    _history(db_session, "u1", s)
    db_session.commit()

    client = client_factory(music_routes.router)
    resp = client.get("/songs/", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    assert resp.json()[0]["top_tag"] == "high"


def test_songs_list_requires_auth(client_factory, db_session):
    client = client_factory(music_routes.router)
    resp = client.get("/songs/")
    assert resp.status_code == 401


def test_songs_list_genre_filter(client_factory, db_session):
    db_session.add(_session("u1"))
    s1 = _song(db_session, artist_name="A1", title="Indie Song", genre="indie")
    s2 = _song(db_session, artist_name="A2", title="Rock Song", genre="rock")
    _history(db_session, "u1", s1)
    _history(db_session, "u1", s2)
    db_session.commit()

    client = client_factory(music_routes.router)
    resp = client.get("/songs/?genre=indie", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    titles = [s["title"] for s in resp.json()]
    assert "Indie Song" in titles
    assert "Rock Song" not in titles


def test_songs_list_invalid_quick_filter(client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()
    client = client_factory(music_routes.router)
    resp = client.get("/songs/?quick_filter=nonexistent", headers={"X-User-Id": "u1"})
    assert resp.status_code == 400


def test_songs_list_quick_filter_missing_tags(client_factory, db_session):
    db_session.add(_session("u1"))
    s_with_tags = _song(db_session, artist_name="Tagged Artist", title="Tagged Song")
    s_no_tags = _song(db_session, artist_name="Bare Artist", title="Bare Song")
    _tag(db_session, s_with_tags, "indie")
    _history(db_session, "u1", s_with_tags)
    _history(db_session, "u1", s_no_tags)
    db_session.commit()

    client = client_factory(music_routes.router)
    resp = client.get("/songs/?quick_filter=missing_tags", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    titles = [s["title"] for s in resp.json()]
    assert "Bare Song" in titles
    assert "Tagged Song" not in titles


def test_songs_list_quick_filter_hidden(client_factory, db_session):
    db_session.add(_session("u1"))
    visible = _song(db_session, artist_name="Va", title="Visible")
    hidden  = _song(db_session, artist_name="Ha", title="Hidden")
    _history(db_session, "u1", visible)
    _history(db_session, "u1", hidden)
    # Mark hidden via UserSongPref (per-user, not global Song.is_deleted)
    db_session.add(UserSongPref(user_id="u1", song_id=hidden.id, is_hidden=True))
    db_session.commit()

    client = client_factory(music_routes.router)
    resp = client.get("/songs/?quick_filter=hidden&include_deleted=true", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    titles = [s["title"] for s in resp.json()]
    assert "Hidden" in titles
    assert "Visible" not in titles


def test_songs_list_quick_filter_active(client_factory, db_session):
    db_session.add(_session("u1"))
    active = _song(db_session, artist_name="Aa", title="Active Song")
    hidden = _song(db_session, artist_name="Ha", title="Hidden Song")
    _history(db_session, "u1", active)
    _history(db_session, "u1", hidden)
    db_session.add(UserSongPref(user_id="u1", song_id=hidden.id, is_hidden=True))
    db_session.commit()

    client = client_factory(music_routes.router)
    resp = client.get("/songs/?quick_filter=active&include_deleted=true", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    titles = [s["title"] for s in resp.json()]
    assert "Active Song" in titles
    assert "Hidden Song" not in titles


def test_songs_list_quick_filter_high_popularity(client_factory, db_session):
    db_session.add(_session("u1"))
    popular = _song(db_session, artist_name="Pop", title="Chart Topper", listeners=100000)
    popular.popularity_score = 5.0
    obscure = _song(db_session, artist_name="Obs", title="Deep Cut", listeners=10)
    obscure.popularity_score = 1.0
    _history(db_session, "u1", popular)
    _history(db_session, "u1", obscure)
    db_session.commit()

    client = client_factory(music_routes.router)
    resp = client.get("/songs/?quick_filter=high_popularity", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    titles = [s["title"] for s in resp.json()]
    assert "Chart Topper" in titles
    assert "Deep Cut" not in titles


def test_songs_list_enrichment_status_filter(client_factory, db_session):
    db_session.add(_session("u1"))
    failed = _song(db_session, artist_name="Fa", title="Failed Enrichment", enrichment_status="failed")
    ok = _song(db_session, artist_name="Oa", title="OK Song", enrichment_status="complete")
    _history(db_session, "u1", failed)
    _history(db_session, "u1", ok)
    db_session.commit()

    client = client_factory(music_routes.router)
    resp = client.get("/songs/?enrichment_status=failed", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    titles = [s["title"] for s in resp.json()]
    assert "Failed Enrichment" in titles
    assert "OK Song" not in titles


# ── GET /songs/{id} ───────────────────────────────────────────────────────────

def test_song_detail_not_found(client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()
    client = client_factory(music_routes.router)
    resp = client.get("/songs/99999", headers={"X-User-Id": "u1"})
    assert resp.status_code == 404


def test_song_detail_includes_tags(client_factory, db_session):
    db_session.add(_session("u1"))
    s = _song(db_session, artist_name="Detail Artist", title="Detail Track", spotify_id="dt1")
    _tag(db_session, s, "shoegaze")
    db_session.add(ListeningHistory(user_id="u1", song_id=s.id, played_at=datetime(2026, 5, 10, 8, 0)))
    db_session.commit()

    client = client_factory(music_routes.router)
    resp = client.get(f"/songs/{s.id}", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Detail Track"
    assert "shoegaze" in data["tags"]
    assert data["listening_count"] == 1


def test_playlist_inclusion_count_is_scoped_to_current_user(client_factory, db_session):
    db_session.add_all([_session("u1"), _session("u2")])
    song = _song(db_session, artist_name="Shared Artist", title="Shared Track", spotify_id="shared")
    db_session.add(ListeningHistory(user_id="u1", song_id=song.id, played_at=datetime(2026, 5, 10, 8, 0)))
    p1 = GeneratedPlaylist(user_id="u1", name="Mine")
    p2 = GeneratedPlaylist(user_id="u2", name="Theirs")
    db_session.add_all([p1, p2])
    db_session.flush()
    db_session.add_all([
        GeneratedPlaylistTrack(generated_playlist_id=p1.id, song_id=song.id, position=0),
        GeneratedPlaylistTrack(generated_playlist_id=p2.id, song_id=song.id, position=0),
    ])
    db_session.commit()

    client = client_factory(music_routes.router)
    response = client.get(f"/songs/{song.id}", headers={"X-User-Id": "u1"})
    assert response.status_code == 200
    assert response.json()["playlist_inclusion_count"] == 1


# ── POST /songs/{id}/hide  /restore ──────────────────────────────────────────

def test_hide_requires_auth(client_factory, db_session):
    # No UserSession in DB — load_request_user_session falls back to None
    s = _song(db_session, artist_name="A", title="T")
    db_session.commit()
    client = client_factory(music_routes.router)
    resp = client.post(f"/songs/{s.id}/hide")
    assert resp.status_code == 401


def test_hide_nonexistent_song(client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()
    client = client_factory(music_routes.router)
    resp = client.post("/songs/99999/hide", headers={"X-User-Id": "u1"})
    assert resp.status_code == 404


# ── POST /songs/{id}/retry-enrichment ────────────────────────────────────────

def test_retry_enrichment_calls_enrich_and_applies(monkeypatch, client_factory, db_session):
    db_session.add(_session("u1"))
    s = _song(db_session, artist_name="Retry Artist", title="Retry Track",
              enrichment_status="pending", genre=None)
    db_session.commit()

    def _fake_enrich(song):
        return {
            "status": "complete",
            "genre": "ambient",
            "tags": [{"name": "ambient", "count": 50}],
            "listeners": 1000,
            "playcount": 5000,
            "error": None,
        }

    monkeypatch.setattr(music_routes, "enrich_song", _fake_enrich)

    def _fake_apply(db, song, payload):
        song.genre = payload.get("genre")
        song.enrichment_status = payload.get("status", "complete")
        return 1

    monkeypatch.setattr(music_routes, "_apply_enrichment", _fake_apply)

    client = client_factory(music_routes.router)
    resp = client.post(f"/songs/{s.id}/retry-enrichment", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["enrichment_status"] == "complete"
    assert data["changed"] == 1


def test_retry_enrichment_song_not_found(client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()
    client = client_factory(music_routes.router)
    resp = client.post("/songs/99999/retry-enrichment", headers={"X-User-Id": "u1"})
    assert resp.status_code == 404
