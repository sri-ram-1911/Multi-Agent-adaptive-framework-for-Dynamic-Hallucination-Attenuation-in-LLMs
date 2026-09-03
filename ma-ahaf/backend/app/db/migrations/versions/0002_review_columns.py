"""human review columns on escalation_queue

Revision ID: 0002_review_columns
Revises: 0001_init
Create Date: 2026-08-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_review_columns"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("escalation_queue", sa.Column("decision", sa.String(), nullable=True))
    op.add_column("escalation_queue", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column("escalation_queue", sa.Column("reviewed_by", sa.String(), nullable=True))
    op.add_column(
        "escalation_queue",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    for col in ("reviewed_at", "reviewed_by", "review_note", "decision"):
        op.drop_column("escalation_queue", col)
