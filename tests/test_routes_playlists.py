"""Tests for /playlists routes — generated history, detail, playlist service."""
from datetime import datetime

from backend.app.models.artist import Artist
from backend.app.models.generated_playlist import GeneratedPlaylist
from backend.app.models.listening_history import ListeningHistory
from backend.app.models.song import Song
from backend.app.models.song_tag import SongTag
from backend.app.models.tag import Tag
from backend.app.models.user_session import UserSession
from backend.app.routes import playlist_routes
from backend.app.services import generated_playlist_service
from backend.app.services.generated_playlist_service import (
    build_playlist_name,
    create_playlist_preview_record,
    serialize_generated_playlist,
)
from backend.app.routes.playlist_routes import (
    _apply_quality_controls,
    _cap_artist_repetition,
    _dedupe_keep_order,
    _deprioritize_recent_playlist_repeats,
)


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
          genre: str | None = None) -> Song:
    artist = _artist(db, artist_name)
    s = Song(
        title=title,
        artist_id=artist.id,
        spotify_id=spotify_id,
        genre=genre,
        enrichment_status="complete",
        is_deleted=False,
    )
    db.add(s)
    db.flush()
    return s


def _tag_song(db, song: Song, tag_name: str) -> None:
    t = db.query(Tag).filter_by(name=tag_name).first()
    if not t:
        t = Tag(name=tag_name)
        db.add(t)
        db.flush()
    db.add(SongTag(song_id=song.id, tag_id=t.id))


def _playlist_record(db, user_id: str, song: Song, name: str = "Test Playlist") -> GeneratedPlaylist:
    artist = db.query(Artist).filter_by(id=song.artist_id).first()
    item = {
        "song": song,
        "score": 0.9,
        "components": {"base_score": 0.9},
        "reasons": ["played often"],
        "tag_names": [],
    }
    item["song"].artist = artist
    return create_playlist_preview_record(
        db,
        user_id=user_id,
        name=name,
        context_type=None,
        request_params={"max_tracks": 1},
        candidate_pool_size=5,
        items=[item],
    )


def _playlist_with_songs(db, user_id, songs):
    items = [{"song": song, "score": 0.8, "components": {}, "reasons": [], "tag_names": []} for song in songs]
    for song in songs:
        song.artist = db.query(Artist).filter_by(id=song.artist_id).first()
    return create_playlist_preview_record(
        db, user_id=user_id, name="Editable", context_type=None,
        request_params={"max_tracks": len(songs)}, candidate_pool_size=len(songs), items=items,
    )


# ── GET /playlists/generated ─────────────────────────────────────────────────

def test_generated_history_empty(client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()

    client = client_factory(playlist_routes.router)
    resp = client.get("/playlists/generated", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_generated_history_requires_auth(client_factory, db_session):
    client = client_factory(playlist_routes.router)
    resp = client.get("/playlists/generated")
    assert resp.status_code == 401


def test_generated_history_returns_playlists(client_factory, db_session):
    db_session.add(_session("u1"))
    s = _song(db_session, artist_name="Hist Artist", title="Hist Track", spotify_id="h1")
    _playlist_record(db_session, "u1", s, name="My Playlist")
    db_session.commit()

    client = client_factory(playlist_routes.router)
    resp = client.get("/playlists/generated", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "My Playlist"
    assert "tracks" not in items[0]


# ── GET /playlists/generated/{id} ────────────────────────────────────────────

def test_generated_detail_not_found(client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()

    client = client_factory(playlist_routes.router)
    resp = client.get("/playlists/generated/99999", headers={"X-User-Id": "u1"})
    assert resp.status_code == 404


def test_generated_detail_returns_tracks(client_factory, db_session):
    db_session.add(_session("u1"))
    s = _song(db_session, artist_name="Detail Artist", title="Detail Track", spotify_id="d1", genre="chill")
    record = _playlist_record(db_session, "u1", s, name="Detail Playlist")
    db_session.commit()

    client = client_factory(playlist_routes.router)
    resp = client.get(f"/playlists/generated/{record.id}", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Detail Playlist"
    assert len(data["tracks"]) == 1
    assert data["tracks"][0]["song"]["title"] == "Detail Track"


def test_generated_detail_scoped_to_user(client_factory, db_session):
    db_session.add_all([_session("u1"), _session("u2")])
    s = _song(db_session, artist_name="Scoped Artist", title="Scoped Track")
    record = _playlist_record(db_session, "u2", s)
    db_session.commit()

    client = client_factory(playlist_routes.router)
    resp = client.get(f"/playlists/generated/{record.id}", headers={"X-User-Id": "u1"})
    assert resp.status_code == 404


# ── POST /playlists/preview ───────────────────────────────────────────────────

def test_playlist_preview_no_history_returns_empty(client_factory, db_session):
    db_session.add(_session("u1"))
    db_session.commit()

    client = client_factory(playlist_routes.router)
    resp = client.post(
        "/playlists/preview",
        json={"max_tracks": 5},
        headers={"X-User-Id": "u1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["generated_playlist"]["tracks"] == []


def test_playlist_preview_creates_record(client_factory, db_session):
    db_session.add(_session("u1"))
    s1 = _song(db_session, artist_name="A", title="S1", spotify_id="s1", genre="indie")
    s2 = _song(db_session, artist_name="B", title="S2", spotify_id="s2", genre="rock")
    _tag_song(db_session, s1, "indie")
    _tag_song(db_session, s2, "rock")
    db_session.add_all([
        ListeningHistory(user_id="u1", song_id=s1.id, played_at=datetime(2026, 5, 1, 10, 0)),
        ListeningHistory(user_id="u1", song_id=s2.id, played_at=datetime(2026, 5, 2, 10, 0)),
    ])
    db_session.commit()

    before = db_session.query(GeneratedPlaylist).count()
    client = client_factory(playlist_routes.router)
    resp = client.post(
        "/playlists/preview",
        json={"max_tracks": 10, "diversity": 0.5, "familiarity": 0.5},
        headers={"X-User-Id": "u1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["quality_controls"]["artist_cap"] == 2
    assert data["quality_controls"]["recent_repeat_guard_active"] is False
    assert data["quality_controls"]["notes"]
    assert data["preview_summary"]
    assert "artists for variety" in data["preview_summary"]
    assert db_session.query(GeneratedPlaylist).count() == before + 1


# ── Utility helpers ───────────────────────────────────────────────────────────

def test_dedupe_keep_order_removes_nones_and_dupes():
    result = _dedupe_keep_order(["a", None, "b", "a", "c", None])
    assert result == ["a", "b", "c"]


def test_apply_quality_controls_empty_list():
    assert _apply_quality_controls([], 0.5, 0.5) == []


def test_apply_quality_controls_diversity_interleaves_artists():
    artist_a = Artist(name="A")
    artist_b = Artist(name="B")
    song_a1 = Song(title="A1", artist=artist_a, spotify_id="a1", is_deleted=False)
    song_a2 = Song(title="A2", artist=artist_a, spotify_id="a2", is_deleted=False)
    song_b1 = Song(title="B1", artist=artist_b, spotify_id="b1", is_deleted=False)

    details = [
        {"song": song_a1, "score": 0.9},
        {"song": song_a2, "score": 0.85},
        {"song": song_b1, "score": 0.8},
    ]
    result = _apply_quality_controls(details, diversity=0.8, familiarity=0.3)
    artists = [d["song"].artist.name for d in result]
    # With diversity=0.8, artist A should not appear twice consecutively
    for i in range(len(artists) - 1):
        assert not (artists[i] == "A" and artists[i + 1] == "A"), \
            f"Artist A appears consecutively at positions {i} and {i+1}"


def test_apply_quality_controls_familiarity_sorts_by_spotify_id():
    artist = Artist(name="C")
    known = Song(title="Known", artist=artist, spotify_id="sp1", is_deleted=False)
    unknown = Song(title="Unknown", artist=artist, spotify_id=None, is_deleted=False)

    details = [
        {"song": unknown, "score": 0.99},
        {"song": known, "score": 0.5},
    ]
    result = _apply_quality_controls(details, diversity=0.3, familiarity=0.9)
    # High familiarity means known tracks should come first
    assert result[0]["song"].spotify_id is not None


def test_cap_artist_repetition_prefers_alternatives_when_available():
    artist_a = Artist(name="A")
    artist_b = Artist(name="B")
    artist_c = Artist(name="C")
    details = [
        {"song": Song(title="A1", artist=artist_a, spotify_id="a1", is_deleted=False), "score": 0.99},
        {"song": Song(title="A2", artist=artist_a, spotify_id="a2", is_deleted=False), "score": 0.98},
        {"song": Song(title="A3", artist=artist_a, spotify_id="a3", is_deleted=False), "score": 0.97},
        {"song": Song(title="B1", artist=artist_b, spotify_id="b1", is_deleted=False), "score": 0.8},
        {"song": Song(title="C1", artist=artist_c, spotify_id="c1", is_deleted=False), "score": 0.7},
    ]

    result = _cap_artist_repetition(details, max_tracks=3, diversity=0.8)
    artists = [item["song"].artist.name for item in result[:3]]

    assert artists == ["A", "B", "C"]


def test_deprioritize_recent_playlist_repeats_when_fresh_tracks_are_available():
    artist = Artist(name="Repeat Artist")
    repeated = Song(id=1, title="Repeated", artist=artist, spotify_id="r1", is_deleted=False)
    fresh_1 = Song(id=2, title="Fresh 1", artist=artist, spotify_id="f1", is_deleted=False)
    fresh_2 = Song(id=3, title="Fresh 2", artist=artist, spotify_id="f2", is_deleted=False)
    details = [
        {"song": repeated, "score": 0.99},
        {"song": fresh_1, "score": 0.8},
        {"song": fresh_2, "score": 0.7},
    ]

    result = _deprioritize_recent_playlist_repeats(details, {1}, max_tracks=2)

    assert [item["song"].id for item in result[:2]] == [2, 3]


def test_deprioritize_recent_playlist_repeats_keeps_order_when_needed():
    artist = Artist(name="Repeat Artist")
    repeated = Song(id=1, title="Repeated", artist=artist, spotify_id="r1", is_deleted=False)
    fresh = Song(id=2, title="Fresh", artist=artist, spotify_id="f1", is_deleted=False)
    details = [
        {"song": repeated, "score": 0.99},
        {"song": fresh, "score": 0.8},
    ]

    result = _deprioritize_recent_playlist_repeats(details, {1}, max_tracks=2)

    assert result == details


# ── serialize_generated_playlist ────────────────────────────────────────────

def test_serialize_without_tracks_omits_tracks_key(db_session):
    db_session.add(_session("u1"))
    s = _song(db_session, artist_name="Ser Artist", title="Ser Track", spotify_id="sr1")
    record = _playlist_record(db_session, "u1", s)
    db_session.commit()

    payload = serialize_generated_playlist(record, include_tracks=False)
    assert "tracks" not in payload
    assert payload["name"] == "Test Playlist"


def test_serialize_with_tracks_includes_song_fields(db_session):
    db_session.add(_session("u1"))
    s = _song(db_session, artist_name="SerT Artist", title="SerT Track", spotify_id="srt1", genre="jazz")
    record = _playlist_record(db_session, "u1", s)
    db_session.commit()

    payload = serialize_generated_playlist(record, include_tracks=True)
    assert len(payload["tracks"]) == 1
    track = payload["tracks"][0]
    assert track["song"]["title"] == "SerT Track"
    assert track["song"]["genre"] == "jazz"


def test_build_playlist_name_uses_genre_and_context(db_session):
    s = _song(db_session, artist_name="Name Artist", title="Name Track", genre="indie")
    item = {
        "song": s,
        "score": 0.9,
        "components": {"familiarity_score": 0.8},
        "reasons": [],
        "tag_names": [],
    }

    name = build_playlist_name([item], context_type="focus")

    assert name.startswith("Indie Focus Mix - ")
def test_generated_playlist_tracks_can_be_edited_and_deleted(client_factory, db_session):
    db_session.add(_session("u1"))
    songs = [_song(db_session, artist_name="Editor", title=f"Song {i}") for i in range(3)]
    record = _playlist_with_songs(db_session, "u1", songs)
    client = client_factory(playlist_routes.router)
    tracks = sorted(record.tracks, key=lambda track: track.position)

    reordered = client.patch(
        f"/playlists/generated/{record.id}/tracks/reorder",
        json={"track_ids": [tracks[2].id, tracks[0].id, tracks[1].id]},
        headers={"X-User-Id": "u1"},
    )
    assert [item["id"] for item in reordered.json()["tracks"]] == [tracks[2].id, tracks[0].id, tracks[1].id]
    pinned = client.patch(
        f"/playlists/generated/{record.id}/tracks/{tracks[0].id}",
        json={"is_pinned": True}, headers={"X-User-Id": "u1"},
    )
    assert pinned.json()["is_pinned"] is True
    removed = client.delete(
        f"/playlists/generated/{record.id}/tracks/{tracks[1].id}", headers={"X-User-Id": "u1"},
    )
    assert [item["position"] for item in removed.json()["tracks"]] == [1, 2]
    assert client.delete(f"/playlists/generated/{record.id}", headers={"X-User-Id": "u1"}).status_code == 200
    assert db_session.query(GeneratedPlaylist).filter_by(id=record.id).first() is None


def test_replace_track_uses_unused_candidate(monkeypatch, client_factory, db_session):
    db_session.add(_session("u1"))
    original = _song(db_session, artist_name="Editor", title="Original")
    replacement = _song(db_session, artist_name="Editor", title="Replacement")
    record = _playlist_with_songs(db_session, "u1", [original])
    monkeypatch.setattr(playlist_routes, "recommend_songs", lambda *args, **kwargs: [{
        "song": replacement, "score": 0.75, "components": {"base": 0.75}, "reasons": ["fresh pick"],
    }])
    client = client_factory(playlist_routes.router)
    response = client.post(
        f"/playlists/generated/{record.id}/tracks/{record.tracks[0].id}/replace",
        headers={"X-User-Id": "u1"},
    )
    assert response.status_code == 200
    assert response.json()["tracks"][0]["song_id"] == replacement.id
