"""Knowledge-base ingestion + search (proposal §11 'configurable private KBs')."""

from __future__ import annotations

import contextlib
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, requires
from app.api.schemas import KBDocumentIn, KBSearchRequest
from app.db.models import Chunk, Document
from app.db.session import get_db
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.vector_store import add_chunks

router = APIRouter(prefix="/v1/kb", tags=["knowledge-base"])


def _chunk(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    words = text.split()
    out, i = [], 0
    step = max(1, size - overlap)
    while i < len(words):
        out.append(" ".join(words[i : i + size]))
        i += step
    return out or [text]


@router.post("/documents", status_code=201)
def ingest(
    body: KBDocumentIn,
    principal: Principal = Depends(requires("operator")),
    db: Session = Depends(get_db),
) -> dict:
    published = None
    if body.published_at:
        with contextlib.suppress(ValueError):
            published = datetime.fromisoformat(body.published_at)
    doc = Document(
        tenant_id=principal.tenant_id, title=body.title, source=body.source,
        uri=body.uri, authority=body.authority, published_at=published,
    )
    db.add(doc)
    db.flush()
    parts = _chunk(body.text)
    ids = add_chunks(db, document_id=doc.id, tenant_id=principal.tenant_id, texts=parts)
    return {"document_id": doc.id, "chunks": len(ids)}


@router.get("/documents")
def list_documents(
    principal: Principal = Depends(requires("viewer")),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.execute(
        select(Document.id, Document.title, Document.source, Document.authority,
               func.count(Chunk.id).label("chunks"))
        .join(Chunk, Chunk.document_id == Document.id, isouter=True)
        .where(Document.tenant_id == principal.tenant_id)
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
    ).all()
    return [dict(r._mapping) for r in rows]


@router.post("/search")
def search(
    body: KBSearchRequest,
    principal: Principal = Depends(requires("viewer")),
    db: Session = Depends(get_db),
) -> list[dict]:
    evs = HybridRetriever(db).retrieve(body.query, tenant_id=principal.tenant_id, rerank_k=body.k)
    return [
        {"chunk_id": e.chunk_id, "document_title": e.document_title, "text": e.text,
         "vector_score": round(e.vector_score, 4), "keyword_score": round(e.keyword_score, 4),
         "fused_score": round(e.fused_score, 5), "rerank_score": round(e.rerank_score, 4)}
        for e in evs
    ]
