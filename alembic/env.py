import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Load .env for local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Alembic Config object
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import app models so autogenerate can detect schema changes
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.app.database import Base  # noqa: E402
from backend.app.models import (  # noqa: F401, E402
    api_cache,
    artist,
    dedup_merge_log,
    generated_playlist,
    generated_playlist_track,
    job,
    listening_goal,
    listening_history,
    recommendation_feedback,
    song,
    song_tag,
    tag,
    user_session,
    user_song_pref,
)

target_metadata = Base.metadata


def _get_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    # SQLAlchemy 2.x requires postgresql:// not postgres://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def run_migrations_offline() -> None:
    url = _get_url() or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg.setdefault("sqlalchemy.url", _get_url())

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
