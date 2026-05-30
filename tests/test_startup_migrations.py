"""Test run_startup_migrations() exercising SQLite branches."""
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, run_startup_migrations


@pytest.fixture()
def sqlite_engine():
    """Fresh in-memory SQLite engine with all tables + startup migrations applied."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


def test_run_startup_migrations_succeeds_on_sqlite(sqlite_engine, monkeypatch):
    monkeypatch.setattr("backend.app.database.engine", sqlite_engine)
    # Should not raise
    run_startup_migrations()
    inspector = inspect(sqlite_engine)
    assert "songs" in inspector.get_table_names()
    assert "artists" in inspector.get_table_names()


def test_run_startup_migrations_idempotent(sqlite_engine, monkeypatch):
    monkeypatch.setattr("backend.app.database.engine", sqlite_engine)
    # Running twice must not raise
    run_startup_migrations()
    run_startup_migrations()


def test_migrations_add_expected_columns(sqlite_engine, monkeypatch):
    monkeypatch.setattr("backend.app.database.engine", sqlite_engine)
    run_startup_migrations()
    inspector = inspect(sqlite_engine)

    song_cols = {c["name"] for c in inspector.get_columns("songs")}
    assert "image_url" in song_cols
    assert "preview_url" in song_cols
    assert "enrichment_status" in song_cols
    assert "is_deleted" in song_cols

    artist_cols = {c["name"] for c in inspector.get_columns("artists")}
    assert "spotify_id" in artist_cols
    assert "genres" in artist_cols

    session_cols = {c["name"] for c in inspector.get_columns("user_sessions")}
    assert "token_expires_at" in session_cols
    assert "refresh_token" in session_cols
    assert "token_info_json" in session_cols


def test_migrations_no_ms_played_column(sqlite_engine, monkeypatch):
    """ms_played and skipped should be dropped if they exist."""
    # Manually add the legacy columns
    with sqlite_engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE listening_history ADD COLUMN ms_played INTEGER"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE listening_history ADD COLUMN skipped BOOLEAN"))
        except Exception:
            pass

    monkeypatch.setattr("backend.app.database.engine", sqlite_engine)
    run_startup_migrations()

    inspector = inspect(sqlite_engine)
    lh_cols = {c["name"] for c in inspector.get_columns("listening_history")}
    assert "ms_played" not in lh_cols
    assert "skipped" not in lh_cols


def test_migrations_song_tag_columns(sqlite_engine, monkeypatch):
    monkeypatch.setattr("backend.app.database.engine", sqlite_engine)
    run_startup_migrations()
    inspector = inspect(sqlite_engine)
    st_cols = {c["name"] for c in inspector.get_columns("song_tags")}
    assert "weight" in st_cols
    assert "popularity" in st_cols
    assert "spotify_id" in st_cols


def test_migrations_dedup_merge_log_columns(sqlite_engine, monkeypatch):
    monkeypatch.setattr("backend.app.database.engine", sqlite_engine)
    run_startup_migrations()
    inspector = inspect(sqlite_engine)
    cols = {c["name"] for c in inspector.get_columns("dedup_merge_logs")}
    assert "user_id" in cols
    assert "batch_id" in cols
    assert "snapshot_json" in cols
