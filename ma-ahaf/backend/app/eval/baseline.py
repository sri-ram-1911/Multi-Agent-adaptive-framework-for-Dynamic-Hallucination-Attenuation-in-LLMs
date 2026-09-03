"""Static-RAG baseline — the same LLM + retriever, no adaptive control, no
verification / revision / abstention. Used as the comparison system (proposal
§16 Phase 5 ablations).
"""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.llm.gateway import Gateway, UsageMeter

_SYS = "Answer the question using the context. If unsure, answer anyway with your best guess."

# optional module-level override for DB-less eval (set by scripts.eval_local)
_LOCAL_CORPUS = None


def set_local_corpus(corpus) -> None:  # noqa: ANN001
    global _LOCAL_CORPUS
    _LOCAL_CORPUS = corpus


def static_rag(db: Session | None, tenant_id: str, prompt: str) -> dict:
    t0 = time.perf_counter()
    meter = UsageMeter()
    gw = Gateway(meter)
    if db is None and _LOCAL_CORPUS is not None:
        evs = _LOCAL_CORPUS.retrieve(prompt, rerank_k=5)
    else:
        from app.retrieval.hybrid import HybridRetriever

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
