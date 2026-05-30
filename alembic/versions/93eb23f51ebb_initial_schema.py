"""initial_schema

Revision ID: 93eb23f51ebb
Revises:
Create Date: 2026-05-30

Baseline migration that adds model-defined indexes absent from the original
hand-rolled schema.  Partial unique indexes managed by startup migrations
(uq_artists_spotify_id, uq_songs_title_artist_id_active,
uq_listening_history_user_song_played_at) are intentionally left untouched.

IMPORTANT — for the already-deployed Neon database, do NOT run this migration.
Instead, stamp it as applied so Alembic knows the baseline:

    alembic stamp 93eb23f51ebb

New schema changes going forward should use:

    alembic revision --autogenerate -m "describe_change"
    alembic upgrade head
"""
from typing import Sequence, Union

from alembic import op


revision: str = '93eb23f51ebb'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_dedup_merge_logs_batch_id', 'dedup_merge_logs', ['batch_id'])
    op.create_index('ix_dedup_merge_logs_user_id', 'dedup_merge_logs', ['user_id'])
    op.create_index('ix_songs_enrichment_status', 'songs', ['enrichment_status'])
    op.create_index('ix_songs_is_deleted', 'songs', ['is_deleted'])
    op.create_index('ix_user_sessions_token_expires_at', 'user_sessions', ['token_expires_at'])
    op.create_index('ix_artists_spotify_id', 'artists', ['spotify_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_artists_spotify_id', table_name='artists')
    op.drop_index('ix_user_sessions_token_expires_at', table_name='user_sessions')
    op.drop_index('ix_songs_is_deleted', table_name='songs')
    op.drop_index('ix_songs_enrichment_status', table_name='songs')
    op.drop_index('ix_dedup_merge_logs_user_id', table_name='dedup_merge_logs')
    op.drop_index('ix_dedup_merge_logs_batch_id', table_name='dedup_merge_logs')
