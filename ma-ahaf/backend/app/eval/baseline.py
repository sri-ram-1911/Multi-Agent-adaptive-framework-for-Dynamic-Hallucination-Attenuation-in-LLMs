"""Static-RAG baseline — the same LLM + retriever, no adaptive control, no
verification / revision / abstention. Used as the comparison system (proposal
§16 Phase 5 ablations).
"""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.llm.gateway import Gateway, UsageMeter
from app.retrieval.hybrid import HybridRetriever

_SYS = "Answer the question using the context. If unsure, answer anyway with your best guess."


def static_rag(db: Session, tenant_id: str, prompt: str) -> dict:
    t0 = time.perf_counter()
    meter = UsageMeter()
    gw = Gateway(meter)
    evs = HybridRetriever(db).retrieve(prompt, tenant_id=tenant_id, rerank_k=5)
    context = "\n---\n".join(f"[S{i+1}] {e.text}" for i, e in enumerate(evs))
    resp = gw.complete(
        "generator",
        [{"role": "system", "content": _SYS},
         {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {prompt}"}],
        temperature=0.4, max_tokens=600, want_logprobs=True,
    )
    return {
        "response": resp.text.strip(),
        "evidence": evs,
        "confidence": round(1 - resp.uncertainty, 3),
        "latency_ms": int((time.perf_counter() - t0) * 1000),
        "usage": meter,
    }
