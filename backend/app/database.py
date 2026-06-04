import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings


logger = logging.getLogger(__name__)

# Neon's serverless PostgreSQL aggressively closes idle SSL connections.
# pool_pre_ping=True checks connections on checkout but can't save a
# connection that drops MID-query (OperationalError: SSL connection has
# been closed unexpectedly).
#
# TCP keepalives prevent the network layer from silently dropping the
# connection after a period of inactivity:
#   keepalives_idle   – send first keepalive probe after 30 s of silence
#   keepalives_interval – retry probe every 10 s
#   keepalives_count    – give up after 5 missed probes (= 80 s total)
#
# pool_recycle=300 discards connections older than 5 min so the pool
# never holds a connection that Neon has already hard-closed server-side.
_is_postgres = settings.DATABASE_URL.startswith("postgres")
_connect_args = (
    {
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "connect_timeout": 10,
    }
    if _is_postgres
    else {}
)

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def _column_type_map(inspector, table_name):
    return {col["name"]: str(col["type"]).lower() for col in inspector.get_columns(table_name)}


def run_startup_migrations():
    """Apply frozen legacy compatibility migrations.

    This function exists only to keep older deployed Neon databases compatible
    with the current SQLAlchemy models through additive/raw SQL fixes. Do not
    add new schema changes here; use Alembic for migrations going forward.
    """
    try:
        inspector = inspect(engine)
        dialect = engine.dialect.name
        table_names = set(inspector.get_table_names())

        with engine.begin() as conn:
            if "artists" in table_names:
                cols = _column_type_map(inspector, "artists")
                if dialect == "postgresql":
                    conn.execute(text("ALTER TABLE artists ADD COLUMN IF NOT EXISTS spotify_id VARCHAR"))
                    conn.execute(text("ALTER TABLE artists ADD COLUMN IF NOT EXISTS genres TEXT"))
                    conn.execute(text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_artists_spotify_id "
                        "ON artists (spotify_id) WHERE spotify_id IS NOT NULL"
                    ))
                else:
                    if "spotify_id" not in cols:
                        conn.execute(text("ALTER TABLE artists ADD COLUMN spotify_id VARCHAR"))
                    if "genres" not in cols:
                        conn.execute(text("ALTER TABLE artists ADD COLUMN genres TEXT"))

            if "songs" in table_names:
                cols = _column_type_map(inspector, "songs")

                if "artist" in cols and "artist_id" not in cols:
                    conn.execute(text("ALTER TABLE songs RENAME COLUMN artist TO artist_id"))
                    logger.info("Migrated legacy songs.artist column to songs.artist_id")
                    inspector = inspect(engine)
                    cols = _column_type_map(inspector, "songs")

                if dialect == "postgresql" and "artist_id" in cols and ("character" in cols["artist_id"] or "text" in cols["artist_id"] or "varchar" in cols["artist_id"]):
                    conn.execute(
                        text(
                            """
                            INSERT INTO artists(name)
                            SELECT DISTINCT artist_id
                            FROM songs
                            WHERE artist_id IS NOT NULL AND artist_id <> ''
                            ON CONFLICT (name) DO NOTHING
                            """
                        )
                    )
                    conn.execute(text("ALTER TABLE songs ADD COLUMN IF NOT EXISTS artist_id_int INTEGER"))
                    conn.execute(
                        text(
                            """
                            UPDATE songs s
                            SET artist_id_int = a.id
                            FROM artists a
                            WHERE a.name = s.artist_id
                            """
                        )
                    )
                    conn.execute(text("ALTER TABLE songs DROP COLUMN artist_id"))
                    conn.execute(text("ALTER TABLE songs RENAME COLUMN artist_id_int TO artist_id"))
                    logger.info("Remapped songs.artist_id from text artist names to integer artist ids")

                inspector = inspect(engine)
                cols = _column_type_map(inspector, "songs")

                if dialect == "postgresql":
                    conn.execute(text("ALTER TABLE songs ADD COLUMN IF NOT EXISTS image_url VARCHAR"))
                    conn.execute(text("ALTER TABLE songs ADD COLUMN IF NOT EXISTS preview_url VARCHAR"))
                    conn.execute(text("ALTER TABLE songs DROP COLUMN IF EXISTS musicbrainz_id"))
                    conn.execute(text("ALTER TABLE songs ADD COLUMN IF NOT EXISTS listeners INTEGER DEFAULT 0"))
                    conn.execute(text("ALTER TABLE songs ADD COLUMN IF NOT EXISTS playcount INTEGER DEFAULT 0"))
                    conn.execute(text("ALTER TABLE songs ADD COLUMN IF NOT EXISTS popularity_score DOUBLE PRECISION"))
                    conn.execute(text("ALTER TABLE songs ADD COLUMN IF NOT EXISTS enrichment_status VARCHAR DEFAULT 'pending'"))
                    conn.execute(text("ALTER TABLE songs ADD COLUMN IF NOT EXISTS enrichment_error VARCHAR"))
                    conn.execute(text("ALTER TABLE songs ADD COLUMN IF NOT EXISTS discovery_source VARCHAR"))
                    conn.execute(text("ALTER TABLE songs ADD COLUMN IF NOT EXISTS discovery_confidence DOUBLE PRECISION"))
                    conn.execute(text("ALTER TABLE songs ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE"))
                else:
                    if "image_url" not in cols:
                        conn.execute(text("ALTER TABLE songs ADD COLUMN image_url VARCHAR"))
                    if "preview_url" not in cols:
                        conn.execute(text("ALTER TABLE songs ADD COLUMN preview_url VARCHAR"))
                    if "musicbrainz_id" in cols:
                        conn.execute(text("ALTER TABLE songs DROP COLUMN musicbrainz_id"))
                        inspector = inspect(engine)
                        cols = _column_type_map(inspector, "songs")
                    if "listeners" not in cols:
                        conn.execute(text("ALTER TABLE songs ADD COLUMN listeners INTEGER DEFAULT 0"))
                    if "playcount" not in cols:
                        conn.execute(text("ALTER TABLE songs ADD COLUMN playcount INTEGER DEFAULT 0"))
                    if "popularity_score" not in cols:
                        conn.execute(text("ALTER TABLE songs ADD COLUMN popularity_score FLOAT"))
                    if "enrichment_status" not in cols:
                        conn.execute(text("ALTER TABLE songs ADD COLUMN enrichment_status VARCHAR DEFAULT 'pending'"))
                    if "enrichment_error" not in cols:
                        conn.execute(text("ALTER TABLE songs ADD COLUMN enrichment_error VARCHAR"))
                    if "discovery_source" not in cols:
                        conn.execute(text("ALTER TABLE songs ADD COLUMN discovery_source VARCHAR"))
                    if "discovery_confidence" not in cols:
                        conn.execute(text("ALTER TABLE songs ADD COLUMN discovery_confidence FLOAT"))
                    if "is_deleted" not in cols:
                        conn.execute(text("ALTER TABLE songs ADD COLUMN is_deleted BOOLEAN DEFAULT 0"))

                if dialect == "postgresql":
                    conn.execute(
                        text(
                            """
                            WITH dupes AS (
                                SELECT id,
                                       MIN(id) OVER (PARTITION BY title, artist_id) AS keeper_id,
                                       ROW_NUMBER() OVER (PARTITION BY title, artist_id ORDER BY id) AS rn
                                FROM songs
                                WHERE is_deleted = FALSE
                                  AND title IS NOT NULL
                                  AND artist_id IS NOT NULL
                            )
                            UPDATE listening_history lh
                            SET song_id = d.keeper_id
                            FROM dupes d
                            WHERE d.rn > 1
                              AND lh.song_id = d.id
                            """
                        )
                    )
                    conn.execute(
                        text(
                            """
                            WITH dupes AS (
                                SELECT id,
                                       MIN(id) OVER (PARTITION BY title, artist_id) AS keeper_id,
                                       ROW_NUMBER() OVER (PARTITION BY title, artist_id ORDER BY id) AS rn
                                FROM songs
                                WHERE is_deleted = FALSE
                                  AND title IS NOT NULL
                                  AND artist_id IS NOT NULL
                            )
                            INSERT INTO song_tags (song_id, tag_id, weight, popularity, spotify_id)
                            SELECT d.keeper_id, st.tag_id, st.weight, st.popularity, st.spotify_id
                            FROM dupes d
                            JOIN song_tags st ON st.song_id = d.id
                            WHERE d.rn > 1
                            ON CONFLICT (song_id, tag_id) DO NOTHING
                            """
                        )
                    )
                    conn.execute(
                        text(
                            """
                            WITH dupes AS (
                                SELECT id,
                                       ROW_NUMBER() OVER (PARTITION BY title, artist_id ORDER BY id) AS rn
                                FROM songs
                                WHERE is_deleted = FALSE
                                  AND title IS NOT NULL
                                  AND artist_id IS NOT NULL
                            )
                            DELETE FROM song_tags st
                            USING dupes d
                            WHERE d.rn > 1
                              AND st.song_id = d.id
                            """
                        )
                    )
                    conn.execute(
                        text(
                            """
                            WITH ranked AS (
                                SELECT id, ROW_NUMBER() OVER (
                                    PARTITION BY title, artist_id
                                    ORDER BY id
                                ) AS rn
                                FROM songs
                                WHERE is_deleted = FALSE
                                  AND title IS NOT NULL
                                  AND artist_id IS NOT NULL
                            )
                            UPDATE songs
                            SET is_deleted = TRUE
                            WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
                            """
                        )
                    )
                    conn.execute(
                        text(
                            """
                            CREATE UNIQUE INDEX IF NOT EXISTS uq_songs_title_artist_id_active
                            ON songs (title, artist_id)
                            WHERE is_deleted = FALSE
                            """
                        )
                    )
                else:
                    conn.execute(
                        text(
                            """
                            CREATE UNIQUE INDEX IF NOT EXISTS uq_songs_title_artist_id_active
                            ON songs (title, artist_id)
                            WHERE is_deleted = 0
                            """
                        )
                    )

            if "song_tags" in table_names:
                cols = _column_type_map(inspector, "song_tags")

                if dialect == "postgresql":
                    conn.execute(text("ALTER TABLE song_tags ADD COLUMN IF NOT EXISTS weight DOUBLE PRECISION"))
                    conn.execute(text("ALTER TABLE song_tags ADD COLUMN IF NOT EXISTS popularity DOUBLE PRECISION"))
                    conn.execute(text("ALTER TABLE song_tags ADD COLUMN IF NOT EXISTS spotify_id VARCHAR"))
                else:
                    if "weight" not in cols:
                        conn.execute(text("ALTER TABLE song_tags ADD COLUMN weight FLOAT"))
                    if "popularity" not in cols:
                        conn.execute(text("ALTER TABLE song_tags ADD COLUMN popularity FLOAT"))
                    if "spotify_id" not in cols:
                        conn.execute(text("ALTER TABLE song_tags ADD COLUMN spotify_id VARCHAR"))

            if "listening_history" in table_names:
                lh_cols = _column_type_map(inspector, "listening_history")
                if dialect == "postgresql":
                    conn.execute(text("ALTER TABLE listening_history DROP COLUMN IF EXISTS ms_played"))
                    conn.execute(text("ALTER TABLE listening_history DROP COLUMN IF EXISTS skipped"))
                else:
                    if "ms_played" in lh_cols:
                        conn.execute(text("ALTER TABLE listening_history DROP COLUMN ms_played"))
                    if "skipped" in lh_cols:
                        conn.execute(text("ALTER TABLE listening_history DROP COLUMN skipped"))

                if dialect == "postgresql":
                    conn.execute(
                        text(
                            """
                            DELETE FROM listening_history lh
                            USING listening_history dup
                            WHERE lh.id > dup.id
                              AND lh.user_id = dup.user_id
                              AND lh.song_id = dup.song_id
                              AND lh.played_at = dup.played_at
                            """
                        )
                    )
                    conn.execute(
                        text(
                            """
                            CREATE UNIQUE INDEX IF NOT EXISTS uq_listening_history_user_song_played_at
                            ON listening_history (user_id, song_id, played_at)
                            """
                        )
                    )
                else:
                    conn.execute(
                        text(
                            """
                            DELETE FROM listening_history
                            WHERE id NOT IN (
                                SELECT MIN(id)
                                FROM listening_history
                                GROUP BY user_id, song_id, played_at
                            )
                            """
                        )
                    )
                    conn.execute(
                        text(
                            """
                            CREATE UNIQUE INDEX IF NOT EXISTS uq_listening_history_user_song_played_at
                            ON listening_history (user_id, song_id, played_at)
                            """
                        )
                    )

            if "user_sessions" in table_names:
                cols = _column_type_map(inspector, "user_sessions")
                if dialect == "postgresql":
                    conn.execute(text("ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMP"))
                    conn.execute(text("ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS refresh_token VARCHAR"))
                    conn.execute(text("ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS token_info_json TEXT"))
                else:
                    if "token_expires_at" not in cols:
                        conn.execute(text("ALTER TABLE user_sessions ADD COLUMN token_expires_at TIMESTAMP"))
                    if "refresh_token" not in cols:
                        conn.execute(text("ALTER TABLE user_sessions ADD COLUMN refresh_token VARCHAR"))
                    if "token_info_json" not in cols:
                        conn.execute(text("ALTER TABLE user_sessions ADD COLUMN token_info_json TEXT"))

            if "dedup_merge_logs" in table_names:
                cols = _column_type_map(inspector, "dedup_merge_logs")
                if dialect == "postgresql":
                    conn.execute(text("ALTER TABLE dedup_merge_logs ADD COLUMN IF NOT EXISTS user_id VARCHAR"))
                    conn.execute(text("ALTER TABLE dedup_merge_logs ADD COLUMN IF NOT EXISTS batch_id VARCHAR"))
                    conn.execute(text("ALTER TABLE dedup_merge_logs ADD COLUMN IF NOT EXISTS snapshot_json TEXT"))
                else:
                    if "user_id" not in cols:
                        conn.execute(text("ALTER TABLE dedup_merge_logs ADD COLUMN user_id VARCHAR"))
                    if "batch_id" not in cols:
                        conn.execute(text("ALTER TABLE dedup_merge_logs ADD COLUMN batch_id VARCHAR"))
                    if "snapshot_json" not in cols:
                        conn.execute(text("ALTER TABLE dedup_merge_logs ADD COLUMN snapshot_json TEXT"))

            if "jobs" in table_names:
                cols = _column_type_map(inspector, "jobs")
                if dialect == "postgresql" and "result_json" not in cols:
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS result_json TEXT"))
                elif dialect != "postgresql":
                    if "result_json" not in cols:
                        conn.execute(text("ALTER TABLE jobs ADD COLUMN result_json TEXT"))

            if "generated_playlists" in table_names:
                cols = _column_type_map(inspector, "generated_playlists")
                if dialect == "postgresql":
                    conn.execute(text("ALTER TABLE generated_playlists ADD COLUMN IF NOT EXISTS summary_json TEXT"))
                else:
                    if "summary_json" not in cols:
                        conn.execute(text("ALTER TABLE generated_playlists ADD COLUMN summary_json TEXT"))

    except SQLAlchemyError:
        # Log but do NOT re-raise.  These are idempotent additive migrations
        # that should already be applied on the production DB.  A transient
        # Neon connection error at cold-start (Neon serverless wakes slowly)
        # was propagating here → crashing the entire app import → Render
        # restart loop.  The app can serve requests fine even if this pass
        # failed; the next startup will retry.
        logger.exception("Startup migration failed — continuing")


def get_db():

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()

