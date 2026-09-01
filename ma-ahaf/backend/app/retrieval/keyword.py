"""Lexical retrieval via PostgreSQL full-text search (proposal §11 hybrid retrieval)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.retrieval.schema import Evidence


def keyword_search(db: Session, query: str, *, tenant_id: str, k: int = 8) -> list[Evidence]:
    rows = db.execute(
        text(
            """
            SELECT c.id, c.document_id, c.text, d.title, d.source,
                   ts_rank_cd(c.tsv, plainto_tsquery('english', :q)) AS score
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.tenant_id = :tid
              AND c.tsv @@ plainto_tsquery('english', :q)
            ORDER BY score DESC
            LIMIT :k
            """
        ),
        {"q": query, "tid": tenant_id, "k": k},
    ).all()
    return [
        Evidence(
            chunk_id=r.id, document_id=r.document_id, document_title=r.title,
            source=r.source, text=r.text, keyword_score=float(r.score),
        )
        for r in rows
    ]
