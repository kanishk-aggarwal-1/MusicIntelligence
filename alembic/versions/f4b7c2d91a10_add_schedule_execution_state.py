"""add schedule execution state

Revision ID: f4b7c2d91a10
Revises: e3c8a1f06b29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f4b7c2d91a10"
down_revision: Union[str, Sequence[str], None] = "e3c8a1f06b29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("playlist_schedules", sa.Column("running_since", sa.DateTime(), nullable=True))
    op.add_column("playlist_schedules", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("playlist_schedules", sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_playlist_schedules_running_since", "playlist_schedules", ["running_since"])


def downgrade() -> None:
    op.drop_index("ix_playlist_schedules_running_since", table_name="playlist_schedules")
    op.drop_column("playlist_schedules", "consecutive_failures")
    op.drop_column("playlist_schedules", "last_error")
    op.drop_column("playlist_schedules", "running_since")
