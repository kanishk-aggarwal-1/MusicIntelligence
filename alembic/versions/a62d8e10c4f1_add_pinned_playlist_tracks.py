"""add pinned playlist tracks

Revision ID: a62d8e10c4f1
Revises: f4b7c2d91a10
"""
from alembic import op
import sqlalchemy as sa

revision = "a62d8e10c4f1"
down_revision = "f4b7c2d91a10"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("generated_playlist_tracks", sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("generated_playlist_tracks", "is_pinned")
