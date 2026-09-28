"""add (user_id, played_at) index on listening_history

Speeds up the app's most common query shape — a single user's plays within a
date window (dashboard / insights / stats). The existing unique constraint
(user_id, song_id, played_at) can't range-scan on played_at because it sits
behind song_id.

Idempotent (IF NOT EXISTS) so it is safe to run against a database where the
index was already created manually.

Revision ID: 4f2a9c1b7e30
Revises: b731fc24e2a0
"""
from typing import Sequence, Union

from alembic import op

revision: str = "4f2a9c1b7e30"
down_revision: Union[str, Sequence[str], None] = "b731fc24e2a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_listening_history_user_played "
        "ON listening_history (user_id, played_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_listening_history_user_played")
