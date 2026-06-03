"""add playlist_schedules

Revision ID: d9b3f1a25c47
Revises: c7a4e2f9b1d8
Create Date: 2026-06-02

Adds the playlist_schedules table backing scheduled playlist refresh. Guarded
with an inspector check so it is safe on both fresh and already-deployed
databases (where create_all may have created the table already).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "d9b3f1a25c47"
down_revision: Union[str, Sequence[str], None] = "c7a4e2f9b1d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "playlist_schedules" not in inspector.get_table_names():
        op.create_table(
            "playlist_schedules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column("context_type", sa.String(), nullable=True),
            sa.Column("min_known_ratio", sa.Float(), nullable=False, server_default="0.6"),
            sa.Column("diversity", sa.Float(), nullable=False, server_default="0.5"),
            sa.Column("familiarity", sa.Float(), nullable=False, server_default="0.5"),
            sa.Column("max_tracks", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("cadence", sa.String(), nullable=False, server_default="weekly"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_run_at", sa.DateTime(), nullable=True),
            sa.Column("next_run_at", sa.DateTime(), nullable=True),
            sa.Column("last_generated_playlist_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    existing_indexes = (
        {idx["name"] for idx in inspector.get_indexes("playlist_schedules")}
        if "playlist_schedules" in inspector.get_table_names()
        else set()
    )
    if "ix_playlist_schedules_user_id" not in existing_indexes:
        op.create_index("ix_playlist_schedules_user_id", "playlist_schedules", ["user_id"])
    if "ix_playlist_schedules_next_run_at" not in existing_indexes:
        op.create_index("ix_playlist_schedules_next_run_at", "playlist_schedules", ["next_run_at"])


def downgrade() -> None:
    op.drop_index("ix_playlist_schedules_next_run_at", table_name="playlist_schedules")
    op.drop_index("ix_playlist_schedules_user_id", table_name="playlist_schedules")
    op.drop_table("playlist_schedules")
