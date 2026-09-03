"""Run a handful of prompts through the real pipeline (local models, no DB) and
write each full trace to demo_traces.json incrementally.

    HF_HUB_OFFLINE=1 python -m scripts.capture_traces
"""

from __future__ import annotations

import json
import os
import sys
import time

os.environ.setdefault("MAAHAF_OTEL_ENABLED", "false")
os.environ.setdefault("MAAHAF_LOG_LEVEL", "ERROR")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# read provider from .env if not already in the environment
_prov = os.environ.get("MAAHAF_LLM__PROVIDER")
_envfile = os.path.join(os.path.dirname(__file__), "..", ".env")
if _prov is None and os.path.exists(_envfile):
    with open(_envfile, encoding="utf-8") as _f:
        for _l in _f:
            if _l.startswith("MAAHAF_LLM__PROVIDER="):
                _prov = _l.split("=", 1)[1].strip()
_prov = _prov or "hf"

if _prov == "hf":
    os.environ.setdefault("MAAHAF_LLM__PROVIDER", "hf")
    os.environ.setdefault("MAAHAF_LLM__HF_MODEL", "google/flan-t5-small")
    os.environ.setdefault("MAAHAF_ZEROSHOT_MODEL",
                          "MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33")
    os.environ.setdefault("MAAHAF_MAX_REVISION_LOOPS", "0")
    os.environ.setdefault("MAAHAF_VERIFIER_LLM_ENABLED", "false")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
else:
    # OpenAI (or other) — still use local embeddings/rerank/NLI; keep those offline
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("MAAHAF_ZEROSHOT_MODEL",
                          "MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33")

from app.claimgraph.graph import to_cytoscape  # noqa: E402
from app.controller.risk_model import explain  # noqa: E402
from app.orchestration import nodes as N  # noqa: E402
from app.orchestration.pipeline import run_pipeline  # noqa: E402
from app.retrieval.local_store import LocalCorpus  # noqa: E402

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "corpus")
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "demo_traces.json")

PROMPTS = sys.argv[1:] or [
    # factual — answerable from the KB
    "What is the ACME Cloud refund policy for annual plans, and what happens after 14 days?",
    # high-stakes — NOT in the KB, must abstain rather than fabricate
    "What is the safe daily dose of ibuprofen for a 6-year-old child?",
    # analytical — synthesis across several KB docs
    "A customer needs SSO and a one-hour response for critical issues. Which ACME plan fits and why?",
    # mixed — factual + creative in one answer
    "Summarise ACME's annual refund rule, then draft a friendly one-line message "
    "for a customer just past the 14-day window.",
    # creative — creativity-first, minimal verification
    "Write a two-line poem about a raindrop returning to the sea.",
]


def main() -> None:
    corpus = LocalCorpus.from_dir(CORPUS_DIR)

    def pre(s):
        if s.policy and s.policy.grounding_intensity >= 0.45:
            s.evidence = corpus.retrieve(s.prompt, k=8, rerank_k=5)
        return s

    def ret(s):
        p = corpus.retrieve_multi([s.prompt], k=10, rerank_k=5)
        s.evidence = p
        for cl in s.claim_graph.claims:
            if cl.claim_type not in ("creative", "opinion"):
                cl.evidence_ids = [e.chunk_id for e in p[:4]]
        s.signals.evidence_coverage = 1.0 if p else 0.0
        sc = [e.source_score for e in p] or [0.5]
        s.signals.source_agreement = round(1 - (max(sc) - min(sc)), 3)
        return s

    N.n_pre_retrieve = pre
    N.n_retrieve = ret

    out: list[dict] = []
    for i, prompt in enumerate(PROMPTS):
        t = time.time()
        st = run_pipeline(None, tenant_id="demo", prompt=prompt, persist=False)
        dt = int((time.time() - t) * 1000)
        cg = st.claim_graph
        out.append({
            "prompt": prompt, "action": st.action, "action_reason": st.action_reason,
            "task_type": st.task_type, "risk_score": st.risk_score,
            "max_claim_risk": round(cg.max_risk(), 3), "confidence": st.confidence,
            "calibrated_confidence": st.calibrated_confidence,
            "agent_disagreement": st.agent_disagreement, "creativity_score": st.creativity_score,
            "final_response": st.final_response, "policy": st.policy.model_dump(),
            "claims": [
                {"text": cl.text, "claim_type": cl.claim_type, "verdict": cl.verdict,
                 "criticality": cl.criticality, "risk_score": cl.risk_score,
                 "risk_level": cl.risk_level, "risk_contributions": cl.risk_contributions,
                 "entailment": cl.entailment_score, "contradiction": cl.contradiction_score,
                 "explanation": explain(cl)}
                for cl in cg.claims
            ],
            "evidence": [
                {"title": e.document_title, "source": e.source, "text": e.text[:280],
                 "source_score": e.source_score, "rerank": round(e.rerank_score, 3),
                 "stance": e.stance}
                for e in st.evidence[:6]
            ],
            "timeline": [
                {"agent": r.agent, "ms": r.latency_ms, "tokens": r.tokens,
                 "model": r.model_version, "rationale": r.rationale}
                for r in st.records
            ],
            "claim_graph": to_cytoscape(cg),
            "latency_ms": dt,
            "tokens": st.__dict__.get("_usage").total_tokens,
            "cost_usd": round(st.__dict__.get("_usage").cost_usd, 5),
        })
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
        print(f"[{i + 1}/{len(PROMPTS)}] {st.action:9} {dt // 1000}s  {prompt[:55]}", flush=True)

    print(f"wrote {OUT} ({len(out)} traces)")


if __name__ == "__main__":
    main()
