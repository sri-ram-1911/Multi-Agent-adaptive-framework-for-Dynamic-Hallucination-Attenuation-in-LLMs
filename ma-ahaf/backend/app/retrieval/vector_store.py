"""pgvector similarity search + chunk upsert."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import Chunk
from app.retrieval.embeddings import embed, embed_one
from app.retrieval.schema import Evidence


def add_chunks(db: Session, *, document_id: str, tenant_id: str, texts: list[str],
               metas: list[dict] | None = None) -> list[str]:
    metas = metas or [{} for _ in texts]
    vecs = embed(texts)
    ids: list[str] = []
    for i, (t, v, m) in enumerate(zip(texts, vecs, metas, strict=True)):
        c = Chunk(document_id=document_id, tenant_id=tenant_id, ordinal=i, text=t,
                  embedding=v, meta=m)
        db.add(c)
        db.flush()
        ids.append(c.id)
    return ids


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def vector_search(db: Session, query: str, *, tenant_id: str, k: int = 8) -> list[Evidence]:
    qv = _vec_literal(embed_one(query, is_query=True))
    rows = db.execute(
        text(
            """
            SELECT c.id, c.document_id, c.text, d.title, d.source,
                   1 - (c.embedding <=> CAST(:qv AS vector)) AS score
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.tenant_id = :tid
            ORDER BY c.embedding <=> CAST(:qv AS vector)
            LIMIT :k
            """
        ),
        {"qv": qv, "tid": tenant_id, "k": k},
    ).all()
    return [
        Evidence(
            chunk_id=r.id, document_id=r.document_id, document_title=r.title,
            source=r.source, text=r.text, vector_score=float(r.score),
        )
        for r in rows
    ]
