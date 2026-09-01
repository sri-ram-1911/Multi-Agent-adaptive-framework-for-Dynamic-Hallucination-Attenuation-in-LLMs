"""Seed the default tenant + a small sample knowledge base.

    python -m scripts.seed_kb
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.logging import get_logger
from app.db.models import Document, Tenant
from app.db.session import session_scope
from app.retrieval.vector_store import add_chunks

log = get_logger("seed_kb")
CORPUS_DIR = Path("/data/corpus")


def _chunk(text: str, size: int = 120) -> list[str]:
    words = text.split()
    return [" ".join(words[i : i + size]) for i in range(0, len(words), size)] or [text]


def main() -> None:
    with session_scope() as db:
        tenant = db.query(Tenant).filter_by(name="default").one_or_none()
        if tenant is None:
            tenant = Tenant(name="default", policy_profile="balanced")
            db.add(tenant)
            db.flush()
            log.info("seed.tenant_created", id=tenant.id)

        if db.query(Document).filter_by(tenant_id=tenant.id).count() > 0:
            log.info("seed.kb_exists_skip")
            return

        files = sorted(CORPUS_DIR.glob("*.json"))
        if not files:
            log.warning("seed.no_corpus", dir=str(CORPUS_DIR))
            return

        for f in files:
            doc = json.loads(f.read_text(encoding="utf-8"))
            published = None
            if doc.get("published_at"):
                published = datetime.fromisoformat(doc["published_at"]).replace(tzinfo=UTC)
            d = Document(
                tenant_id=tenant.id, title=doc["title"], source=doc.get("source", "doc"),
                authority=doc.get("authority", 0.6), published_at=published,
                uri=doc.get("uri"), meta=doc.get("meta", {}),
            )
            db.add(d)
            db.flush()
            parts = _chunk(doc["text"])
            add_chunks(db, document_id=d.id, tenant_id=tenant.id, texts=parts)
            log.info("seed.doc", title=d.title, chunks=len(parts))

    log.info("seed.kb_done")


if __name__ == "__main__":
    main()
