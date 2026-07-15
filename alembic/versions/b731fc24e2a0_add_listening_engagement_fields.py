"""add listening engagement fields

Revision ID: b731fc24e2a0
Revises: a62d8e10c4f1
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "b731fc24e2a0"
down_revision = "a62d8e10c4f1"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = {col["name"] for col in inspect(bind).get_columns("listening_history")}
    for name, type_ in (
        ("ms_played", sa.Integer()), ("skipped", sa.Boolean()),
        ("platform", sa.String()), ("country", sa.String()),
        ("offline", sa.Boolean()), ("incognito", sa.Boolean()),
    ):
        if name not in existing:
            op.add_column("listening_history", sa.Column(name, type_, nullable=True))


def downgrade():
    for name in ("incognito", "offline", "country", "platform", "skipped", "ms_played"):
        op.drop_column("listening_history", name)
