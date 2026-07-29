"""Tests for the AI DJ agent — POST /playlists/dj and dj_agent_service."""
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from backend.app.models.artist import Artist
from backend.app.models.listening_history import ListeningHistory
from backend.app.models.song import Song
from backend.app.models.song_tag import SongTag
from backend.app.models.tag import Tag
from backend.app.models.user_session import UserSession
from backend.app.routes import playlist_routes


# ---------------------------------------------------------------------------
# Test data helpers (mirrors test_routes_playlists.py conventions)
# ---------------------------------------------------------------------------

def _session(user_id: str):
    return UserSession(user_id=user_id, token="tok", token_info_json="{}")


def _artist(db, name: str) -> Artist:
    a = db.query(Artist).filter_by(name=name).first()
    if not a:
        a = Artist(name=name)
        db.add(a)
        db.flush()
    return a


def _song(db, *, artist_name: str, title: str, spotify_id: str | None = None) -> Song:
    artist = _artist(db, artist_name)
    s = Song(
        title=title,
        artist_id=artist.id,
        spotify_id=spotify_id,
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
    db.flush()


def _history(db, user_id: str, song: Song, plays: int = 5) -> None:
    base = datetime(2024, 1, 1)
    for i in range(plays):
        db.add(ListeningHistory(
            user_id=user_id,
            song_id=song.id,
            played_at=base + timedelta(hours=i),
        ))
    db.flush()


def _setup_library(db, user_id: str):
    """Create a minimal library with songs, tags, and history."""
    songs = []
    for i in range(6):
        s = _song(db, artist_name=f"Artist{i}", title=f"Song{i}", spotify_id=f"sp{i}")
        _tag_song(db, s, "indie" if i % 2 == 0 else "rock")
        _history(db, user_id, s, plays=i + 3)
        songs.append(s)
    db.commit()
    return songs


# ---------------------------------------------------------------------------
# Mock factories for Anthropic tool-use loop
# ---------------------------------------------------------------------------

def _make_tool_use_response(tool_name: str, tool_id: str, tool_input: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = tool_name
    block.input = tool_input
    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [block]
    return response


def _make_end_turn_response(note: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = note
    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [block]
    return response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_dj_agent_happy_path(db_session, client_factory, monkeypatch):
    """Full agent loop: profile → build_playlist → end_turn with DJ note."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    user_id = "dj_happy"
    db_session.add(_session(user_id))
    _setup_library(db_session, user_id)

    turns = [
        _make_tool_use_response("get_listening_profile", "tu1", {}),
        _make_tool_use_response(
            "build_playlist", "tu2",
            {"context_type": "chill", "familiarity": 0.6, "diversity": 0.5},
        ),
        _make_end_turn_response(
            "Riding your indie wave — light and familiar, perfect for winding down."
        ),
    ]

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = turns

    with patch("backend.app.services.dj_agent_service.anthropic") as mock_anthropic:
        mock_anthropic.Anthropic.return_value = mock_client
        client = client_factory(playlist_routes.router)
        resp = client.post(
            "/playlists/dj",
            json={"prompt": "chill evening session", "max_tracks": 10},
            headers={"X-User-Id": user_id},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "Riding your indie wave" in body["dj_note"]
    assert "generated_playlist" in body
    assert body["dj_prompt"] == "chill evening session"
    assert "context_type" in body["dj_params"]
    assert mock_client.messages.create.call_count == 3


def test_dj_agent_no_build_playlist_call(db_session, client_factory, monkeypatch):
    """Claude exits without calling build_playlist — fallback must still produce a playlist."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    user_id = "dj_fallback"
    db_session.add(_session(user_id))
    _setup_library(db_session, user_id)

    # Agent immediately returns end_turn without any tool calls
    turns = [_make_end_turn_response("Just vibing with your library.")]

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = turns

    with patch("backend.app.services.dj_agent_service.anthropic") as mock_anthropic:
        mock_anthropic.Anthropic.return_value = mock_client
        client = client_factory(playlist_routes.router)
        resp = client.post(
            "/playlists/dj",
            json={"prompt": "anything", "max_tracks": 5},
            headers={"X-User-Id": user_id},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "generated_playlist" in body
    assert body["dj_note"] == "Just vibing with your library."


def test_dj_agent_max_iterations(db_session, client_factory, monkeypatch):
    """Agent stuck in tool_use loop — exits cleanly after MAX_ITERATIONS."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    user_id = "dj_loop"
    db_session.add(_session(user_id))
    _setup_library(db_session, user_id)

    from backend.app.services.dj_agent_service import MAX_ITERATIONS

    infinite = _make_tool_use_response("get_listening_profile", "tu_inf", {})

    mock_client = MagicMock()
    mock_client.messages.create.return_value = infinite  # same response every call

    with patch("backend.app.services.dj_agent_service.anthropic") as mock_anthropic:
        mock_anthropic.Anthropic.return_value = mock_client
        client = client_factory(playlist_routes.router)
        resp = client.post(
            "/playlists/dj",
            json={"prompt": "test loop", "max_tracks": 5},
            headers={"X-User-Id": user_id},
        )

    assert resp.status_code == 200
    assert mock_client.messages.create.call_count == MAX_ITERATIONS


def test_dj_missing_api_key(db_session, client_factory, monkeypatch):
    """Missing ANTHROPIC_API_KEY returns 503."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    user_id = "dj_nokey"
    db_session.add(_session(user_id))
    db_session.commit()

    client = client_factory(playlist_routes.router)
    resp = client.post(
        "/playlists/dj",
        json={"prompt": "anything", "max_tracks": 10},
        headers={"X-User-Id": user_id},
    )
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_dj_empty_prompt(db_session, client_factory, monkeypatch):
    """Empty prompt returns 400."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    user_id = "dj_empty"
    db_session.add(_session(user_id))
    db_session.commit()

    client = client_factory(playlist_routes.router)
    resp = client.post(
        "/playlists/dj",
        json={"prompt": "   ", "max_tracks": 10},
        headers={"X-User-Id": user_id},
    )
    assert resp.status_code == 400
