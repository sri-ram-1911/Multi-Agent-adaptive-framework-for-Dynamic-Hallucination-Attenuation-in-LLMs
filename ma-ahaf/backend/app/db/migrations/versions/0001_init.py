"""initial schema

Revision ID: 0001_init
Revises:
Create Date: 2026-08-30
"""
from __future__ import annotations

from alembic import op

from app.db.models import Base

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    # Keep the FTS vector current.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION chunks_tsv_trigger() RETURNS trigger AS $$
        BEGIN
          NEW.tsv := to_tsvector('english', coalesce(NEW.text, ''));
          RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_chunks_tsv ON chunks")
    op.execute(
        "CREATE TRIGGER trg_chunks_tsv BEFORE INSERT OR UPDATE ON chunks "
        "FOR EACH ROW EXECUTE FUNCTION chunks_tsv_trigger()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DROP TRIGGER IF EXISTS trg_chunks_tsv ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_tsv_trigger()")
    Base.metadata.drop_all(bind=bind)
