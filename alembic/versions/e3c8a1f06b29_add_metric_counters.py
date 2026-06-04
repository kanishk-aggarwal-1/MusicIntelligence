"""add metric_counters

Revision ID: e3c8a1f06b29
Revises: d9b3f1a25c47
Create Date: 2026-06-03

Adds the metric_counters table backing persistent, cumulative live-traffic
metrics. Guarded with an inspector check so it is safe on both fresh and
already-deployed databases (where create_all may have created it already).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "e3c8a1f06b29"
down_revision: Union[str, Sequence[str], None] = "d9b3f1a25c47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "metric_counters" not in inspector.get_table_names():
        op.create_table(
            "metric_counters",
            sa.Column("name", sa.String(), primary_key=True),
            sa.Column("value", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("metric_counters")
