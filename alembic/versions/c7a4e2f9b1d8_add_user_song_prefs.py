"""add user_song_prefs

Revision ID: c7a4e2f9b1d8
Revises: 93eb23f51ebb
Create Date: 2026-06-02

Adds the per-user song preference table (UserSongPref) that replaces the global
Song.is_deleted flag for hide/restore. The table was previously created only by
Base.metadata.create_all(); this migration brings it under Alembic control.

The upgrade is guarded with an inspector check so it is safe to run on both a
fresh database and the already-deployed Neon database (where create_all has
already created the table). On the deployed DB you may also simply:

    alembic stamp head
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "c7a4e2f9b1d8"
down_revision: Union[str, Sequence[str], None] = "93eb23f51ebb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "user_song_prefs" not in existing_tables:
        op.create_table(
            "user_song_prefs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("song_id", sa.Integer(), sa.ForeignKey("songs.id"), nullable=False),
            sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("user_id", "song_id", name="uq_user_song_pref"),
        )

    existing_indexes = {
        idx["name"] for idx in inspector.get_indexes("user_song_prefs")
    } if "user_song_prefs" in inspector.get_table_names() else set()

    if "ix_user_song_prefs_user_id" not in existing_indexes:
        op.create_index("ix_user_song_prefs_user_id", "user_song_prefs", ["user_id"])
    if "ix_user_song_prefs_song_id" not in existing_indexes:
        op.create_index("ix_user_song_prefs_song_id", "user_song_prefs", ["song_id"])


def downgrade() -> None:
    op.drop_index("ix_user_song_prefs_song_id", table_name="user_song_prefs")
    op.drop_index("ix_user_song_prefs_user_id", table_name="user_song_prefs")
    op.drop_table("user_song_prefs")
