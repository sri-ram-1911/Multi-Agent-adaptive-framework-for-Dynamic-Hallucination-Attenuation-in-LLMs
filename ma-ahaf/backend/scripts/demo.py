"""End-to-end demo of the full 13-agent pipeline with NO database and NO API key.

Modes:
  --real  (default)  real ML/DL everywhere: bge-small embeddings, ms-marco
                     cross-encoder reranker, DeBERTa-v3 NLI verifier,
                     bart-large-mnli zero-shot intent, and a LOCAL flan-t5
                     generator (google/flan-t5-base). First run downloads the
                     models (~2 GB) into the HF cache.
  --mock             deterministic MockAdapter + hashing embedder + heuristics
                     (instant, offline, no downloads) — plumbing check only.

    python -m scripts.demo               # real
    python -m scripts.demo --mock
    python -m scripts.demo --real --model google/flan-t5-large
"""

from __future__ import annotations

import contextlib
import os
import sys
import textwrap

# ---- must set provider BEFORE importing app.* (import-time offline flags) ----
_argv = sys.argv[1:]
_mock = "--mock" in _argv
if "--model" in _argv:
    os.environ["MAAHAF_LLM__HF_MODEL"] = _argv[_argv.index("--model") + 1]
os.environ["MAAHAF_LLM__PROVIDER"] = "mock" if _mock else os.environ.get("MAAHAF_LLM__PROVIDER", "hf")
os.environ.setdefault("MAAHAF_OTEL_ENABLED", "false")
os.environ.setdefault("MAAHAF_LOG_LEVEL", "ERROR")
# keep the local-model demo snappy: 1 revision loop + a small zero-shot model
os.environ.setdefault("MAAHAF_MAX_REVISION_LOOPS", "1" if not _mock else "2")
if not _mock:
    os.environ.setdefault(
        "MAAHAF_ZEROSHOT_MODEL", "MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33"
    )
    os.environ.setdefault("MAAHAF_LLM__HF_MODEL", "google/flan-t5-base")
    if "--large" in _argv:
        os.environ["MAAHAF_LLM__HF_MODEL"] = "google/flan-t5-large"
    if "--small" in _argv:
        os.environ["MAAHAF_LLM__HF_MODEL"] = "google/flan-t5-small"
    # use only locally-cached models — never block on huggingface.co
    if "--online" not in _argv:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import settings  # noqa: E402
from app.orchestration import nodes as N  # noqa: E402
from app.orchestration.pipeline import run_pipeline  # noqa: E402

CORPUS_DIR = os.environ.get("MAAHAF_CORPUS_DIR", "/data/corpus")
if not os.path.isdir(CORPUS_DIR):
    CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "corpus")

ALL_PROMPTS = [
    "What is the chemical formula of water and at what temperature does it boil?",
    "A customer bought an annual ACME Cloud plan 20 days ago and wants a full refund. What are they entitled to?",
    "How many litres of water per day should someone with heart failure drink?",
    "What is the safe daily dose of ibuprofen for a 6-year-old child?",
    "Write a two-line poem about a raindrop returning to the sea.",
]
# real (local-model) mode is CPU-bound; run a representative subset unless --all
PROMPTS = ALL_PROMPTS if (_mock or "--all" in _argv) else [
    ALL_PROMPTS[0],  # factual, answerable   -> ANSWER
    ALL_PROMPTS[1],  # policy lookup          -> ANSWER / QUALIFY
    ALL_PROMPTS[3],  # high-stakes, no KB     -> ABSTAIN
    ALL_PROMPTS[4],  # creative               -> creativity-first path
]
BAR = "=" * 90


def _install_local_retrieval() -> None:
    """Swap the DB-backed retrieval node for an in-memory corpus index."""
    from app.retrieval.local_store import LocalCorpus

    corpus = LocalCorpus.from_dir(CORPUS_DIR)

    def n_pre_retrieve(state):
        if not state.policy or state.policy.grounding_intensity < 0.55:
            return state
        state.evidence = corpus.retrieve(state.prompt, k=8, rerank_k=5)
        return state

    def n_retrieve(state):
        want_expansion = state.ambiguity > 0.5
        queries = [state.prompt]
        if want_expansion:
            from app.retrieval.query_expansion import expand

            queries = expand(state.gateway, state.prompt, enabled=True)
        pool = corpus.retrieve_multi(queries, k=8, rerank_k=state.policy.candidates + 4)
        state.evidence = pool
        checkable = [c for c in state.claim_graph.claims if c.claim_type not in ("creative", "opinion")]
        for c in checkable:
            c.evidence_ids = [e.chunk_id for e in pool[:5]]
        state.signals.evidence_coverage = 1.0 if pool else 0.0
        scores = [e.source_score for e in pool] or [0.5]
        state.signals.source_agreement = round(1 - (max(scores) - min(scores)), 3)
        return state

    N.n_retrieve = n_retrieve
    N.n_pre_retrieve = n_pre_retrieve


def show(state) -> None:
    pv = state.policy
    print(BAR)
    print(f"PROMPT       : {state.raw_prompt}")
    print(f"task type    : {state.task_type}   ambiguity={state.ambiguity:.2f}   request risk={state.risk_score:.2f}")
    print(f"policy vec   : grounding={pv.grounding_intensity:.2f} verify={pv.verification_depth:.2f} "
          f"creativity={pv.creativity_allowance:.2f} citation={pv.citation_requirement:.2f} "
          f"abstain_thr={pv.abstention_threshold:.2f} escalate_thr={pv.escalation_threshold:.2f}")
    print(f"\n>>> ACTION   : {state.action.upper()}  —  {state.action_reason}")
    print(f"confidence   : raw={state.confidence:.2f}  calibrated={state.calibrated_confidence:.2f}  "
          f"disagreement={state.agent_disagreement:.2f}  max_claim_risk={state.claim_graph.max_risk():.2f}")

    print("\nRESPONSE:")
    print(textwrap.indent(textwrap.fill(state.final_response, 84), "  "))

    print(f"\nCLAIMS ({len(state.claim_graph.claims)}):")
    for c in state.claim_graph.claims:
        print(f"  - [{c.claim_type:8}] {c.verdict:12} risk={c.risk_score:.2f}({c.risk_level}) "
              f"entail={c.entailment_score:.2f} contra={c.contradiction_score:.2f}")
        print(f"      {textwrap.shorten(c.text, 100)}")

    print(f"\nEVIDENCE ({len(state.evidence)}):")
    for e in state.evidence[:5]:
        print(f"  - {e.document_title[:34]:34} src={e.source_score:.2f} rerank={e.rerank_score:+.2f} "
              f"stance={e.stance}")
        print(f"      {textwrap.shorten(e.text, 100)}")

    print("\nAGENT TIMELINE:")
    for r in state.records:
        print(f"  {r.agent:20} {r.latency_ms:5d}ms {r.tokens:5d}tok  {textwrap.shorten(r.rationale or '', 62)}")

    u = state.__dict__.get("_usage")
    print(f"\ntotals: {state.__dict__.get('_latency_ms')} ms | "
          f"{getattr(u, 'total_tokens', 0)} tokens | {getattr(u, 'calls', 0)} LLM calls")


def main() -> None:
    mode = "MOCK (deterministic)" if settings.llm.provider == "mock" else f"REAL — generator={settings.llm.hf_model}"
    print(f"MA-AHAF demo | mode: {mode} | no DB, no API key")
    print(f"corpus: {os.path.abspath(CORPUS_DIR)}")
    if settings.llm.provider != "mock":
        print("loading models (first run downloads ~2 GB)…\n")
    _install_local_retrieval()

    for p in PROMPTS:
        state = run_pipeline(db=None, tenant_id="demo", prompt=p, persist=False)
        show(state)
    print(BAR)


if __name__ == "__main__":
    main()
