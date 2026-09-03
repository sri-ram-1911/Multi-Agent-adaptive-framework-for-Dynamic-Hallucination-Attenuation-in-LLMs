"""Standalone demo server for the dashboard — NO Postgres, NO Redis, NO API key.

Runs the full 13-agent pipeline against the in-memory corpus index and keeps
requests / traces / eval runs in process memory. Everything the React dashboard
needs is served here, so you only need Node.js for the UI.

    # terminal 1
    cd backend
    python -m scripts.serve_demo                 # -> http://localhost:8000
    #   --mock  deterministic, no model downloads
    #   default: local flan-t5-base + real embeddings/NLI (offline if cached)

    # terminal 2
    cd frontend && npm install && npm run dev     # -> http://localhost:5173
"""

from __future__ import annotations

import os
import sys
import time
import uuid

_argv = sys.argv[1:]
_mock = "--mock" in _argv
os.environ["MAAHAF_LLM__PROVIDER"] = "mock" if _mock else os.environ.get("MAAHAF_LLM__PROVIDER", "hf")
os.environ.setdefault("MAAHAF_OTEL_ENABLED", "false")
os.environ.setdefault("MAAHAF_LOG_LEVEL", "INFO")
if not _mock:
    os.environ.setdefault("MAAHAF_LLM__HF_MODEL", "google/flan-t5-base")
    os.environ.setdefault("MAAHAF_ZEROSHOT_MODEL",
                          "MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import PlainTextResponse  # noqa: E402
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest  # noqa: E402

from app.api.schemas import GenerateRequest  # noqa: E402
from app.claimgraph.graph import to_cytoscape  # noqa: E402
from app.controller.risk_model import explain  # noqa: E402
from app.core.logging import get_logger  # noqa: E402
from app.orchestration import nodes as N  # noqa: E402
from app.orchestration.pipeline import run_pipeline  # noqa: E402
from app.retrieval.local_store import LocalCorpus  # noqa: E402

log = get_logger("serve_demo")

CORPUS_DIR = os.environ.get("MAAHAF_CORPUS_DIR", "/data/corpus")
if not os.path.isdir(CORPUS_DIR):
    CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "corpus")

CORPUS = LocalCorpus.from_dir(CORPUS_DIR)
REQUESTS: dict[str, dict] = {}
EVAL_RUNS: dict[str, dict] = {}
ESCALATIONS: list[dict] = []


# ---- wire the pipeline to the in-memory corpus (same as scripts/demo.py) ----
def _pre_retrieve(s):
    if s.policy and s.policy.grounding_intensity >= 0.45:
        s.evidence = CORPUS.retrieve(s.prompt, k=8, rerank_k=5)
    return s


def _retrieve(s):
    pool = CORPUS.retrieve_multi([s.prompt], k=8, rerank_k=6)
    s.evidence = pool
    for c in s.claim_graph.claims:
        if c.claim_type not in ("creative", "opinion"):
            c.evidence_ids = [e.chunk_id for e in pool[:5]]
    s.signals.evidence_coverage = 1.0 if pool else 0.0
    sc = [e.source_score for e in pool] or [0.5]
    s.signals.source_agreement = round(1 - (max(sc) - min(sc)), 3)
    return s


N.n_pre_retrieve = _pre_retrieve
N.n_retrieve = _retrieve


def _state_to_trace(state) -> dict:
    cg = state.claim_graph
    return {
        "trace_id": state.request_id,
        "created_at": state.__dict__.get("_created_at"),
        "prompt": state.prompt,
        "task_type": state.task_type,
        "policy_vector": state.policy.model_dump() if state.policy else {},
        "action": state.action,
        "action_reason": state.action_reason,
        "final_response": state.final_response,
        "segments": [s.model_dump() for s in state.segments],
        "confidence": state.confidence,
        "calibrated_confidence": state.calibrated_confidence,
        "consistency_gap": state.consistency_gap,
        "risk_score": state.risk_score,
        "max_claim_risk": round(cg.max_risk(), 4),
        "agent_disagreement": state.agent_disagreement,
        "latency_ms": state.__dict__.get("_latency_ms", 0),
        "total_tokens": getattr(state.__dict__.get("_usage"), "total_tokens", 0),
        "cost_usd": round(getattr(state.__dict__.get("_usage"), "cost_usd", 0.0), 6),
        "pii_flags": state.pii_flags,
        "claims": [
            {"id": c.id, "text": c.text, "claim_type": c.claim_type, "criticality": c.criticality,
             "verdict": c.verdict, "risk_score": c.risk_score, "risk_level": c.risk_level,
             "risk_contributions": c.risk_contributions,
             "evidence": [{"chunk_id": cid} for cid in c.evidence_ids], "explanation": explain(c)}
            for c in cg.claims
        ],
        "agent_runs": [
            {"agent": r.agent, "ordinal": i, "output": r.output, "rationale": r.rationale,
             "latency_ms": r.latency_ms, "tokens": r.tokens, "model_version": r.model_version}
            for i, r in enumerate(state.records)
        ],
        "claim_graph": to_cytoscape(cg),
        "model_versions": state.model_versions,
        "escalated": state.action == "escalate",
    }


app = FastAPI(title="MA-AHAF demo server", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok", "mode": os.environ["MAAHAF_LLM__PROVIDER"], "corpus_chunks": len(CORPUS.texts)}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/generate")
async def generate(body: GenerateRequest, request: Request):
    from fastapi.concurrency import run_in_threadpool

    t0 = time.time()
    state = await run_in_threadpool(
        run_pipeline, None,
        tenant_id="demo", prompt=body.prompt, context=body.context,
        policy_profile=body.policy_profile, policy_overrides=body.policy_overrides,
        persist=False,
    )
    state.__dict__["_created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    trace = _state_to_trace(state)
    REQUESTS[state.request_id] = trace
    if state.action == "escalate" or (state.action == "abstain" and state.task_type == "high_stakes"):
        ESCALATIONS.append({
            "id": str(uuid.uuid4()), "request_id": state.request_id,
            "reason": state.action_reason, "status": "pending",
            "created_at": trace["created_at"], "prompt": trace["prompt"][:240],
            "action": state.action, "calibrated_confidence": state.calibrated_confidence,
            "max_claim_risk": trace["max_claim_risk"], "agent_disagreement": state.agent_disagreement,
            "task_type": state.task_type, "decision": None, "reviewed_by": None,
        })
    cg = state.claim_graph
    u = state.__dict__.get("_usage")
    log.info("demo.generate", action=state.action, ms=int((time.time() - t0) * 1000))
    return {
        "trace_id": state.request_id, "response": state.final_response,
        "segments": trace["segments"], "action": state.action,
        "action_reason": state.action_reason, "confidence": state.confidence,
        "calibrated_confidence": state.calibrated_confidence,
        "consistency_gap": state.consistency_gap, "task_type": state.task_type,
        "risk_score": state.risk_score, "max_claim_risk": round(cg.max_risk(), 4),
        "agent_disagreement": state.agent_disagreement,
        "creativity_score": state.creativity_score,
        "policy_vector": state.policy.model_dump() if state.policy else {},
        "claims": trace["claims"],
        "evidence": [
            {"chunk_id": e.chunk_id, "document_title": e.document_title, "source": e.source,
             "text": e.text, "source_score": e.source_score,
             "rerank_score": round(e.rerank_score, 4), "stance": e.stance}
            for e in state.evidence
        ],
        "usage": {"tokens_in": getattr(u, "tokens_in", 0), "tokens_out": getattr(u, "tokens_out", 0),
                  "cost_usd": round(getattr(u, "cost_usd", 0.0), 6), "llm_calls": getattr(u, "calls", 0)},
        "latency_ms": state.__dict__.get("_latency_ms", 0),
    }


@app.get("/v1/traces")
def list_traces(limit: int = 50, action: str | None = None):
    rows = sorted(REQUESTS.values(), key=lambda t: t.get("created_at") or "", reverse=True)
    if action:
        rows = [r for r in rows if r["action"] == action]
    return [
        {"trace_id": r["trace_id"], "created_at": r.get("created_at"), "prompt": r["prompt"][:200],
         "task_type": r["task_type"], "action": r["action"], "risk_score": r["risk_score"],
         "max_claim_risk": r["max_claim_risk"], "agent_disagreement": r["agent_disagreement"],
         "calibrated_confidence": r["calibrated_confidence"], "latency_ms": r["latency_ms"],
         "total_tokens": r["total_tokens"], "cost_usd": r["cost_usd"]}
        for r in rows[:limit]
    ]


@app.get("/v1/traces/{trace_id}")
def get_trace(trace_id: str):
    return REQUESTS.get(trace_id) or {"error": {"message": "trace not found"}}


@app.get("/v1/metrics/summary")
def metrics_summary(hours: int = 168):
    rows = list(REQUESTS.values())
    n = len(rows) or 1
    by_action: dict[str, int] = {}
    for r in rows:
        by_action[r["action"]] = by_action.get(r["action"], 0) + 1
    lat = sorted(r["latency_ms"] for r in rows)
    p = lambda q: lat[min(len(lat) - 1, int(q * len(lat)))] if lat else 0  # noqa: E731
    return {
        "window_hours": hours, "total_requests": len(rows), "by_action": by_action,
        "abstention_rate": round((by_action.get("abstain", 0) + by_action.get("escalate", 0)) / n, 3),
        "avg_calibrated_confidence": round(sum(r["calibrated_confidence"] for r in rows) / n, 3),
        "avg_max_claim_risk": round(sum(r["max_claim_risk"] for r in rows) / n, 3),
        "avg_agent_disagreement": round(sum(r["agent_disagreement"] for r in rows) / n, 3),
        "latency_ms": {"p50": p(0.5), "p90": p(0.9), "p95": p(0.95)},
        "tokens_total": sum(r["total_tokens"] for r in rows),
        "cost_usd_total": round(sum(r["cost_usd"] for r in rows), 4),
        "avg_verification_depth": round(
            sum(r["policy_vector"].get("verification_depth", 0) for r in rows) / n, 3
        ) if rows else None,
        "timeseries": [
            {"t": r.get("created_at"), "latency_ms": r["latency_ms"], "risk": r["max_claim_risk"],
             "confidence": r["calibrated_confidence"], "action": r["action"]}
            for r in sorted(rows, key=lambda x: x.get("created_at") or "")
        ],
    }


@app.get("/v1/metrics/escalations")
def escalations():
    return [e for e in ESCALATIONS if e["status"] == "pending"]


@app.get("/v1/review/queue")
def review_queue(status: str = "pending"):
    return [e for e in ESCALATIONS if status == "all" or e["status"] == status]


@app.get("/v1/review/queue/stats")
def review_stats():
    return {"pending": sum(e["status"] == "pending" for e in ESCALATIONS),
            "reviewed": sum(e["status"] == "reviewed" for e in ESCALATIONS)}


@app.get("/v1/review/queue/{item_id}")
def review_item(item_id: str):
    e = next((x for x in ESCALATIONS if x["id"] == item_id), None)
    if not e:
        return {"error": {"message": "not found"}}
    t = REQUESTS.get(e["request_id"], {})
    return {**e, "final_response": t.get("final_response"), "policy_vector": t.get("policy_vector", {}),
            "claims": t.get("claims", []), "claim_graph": t.get("claim_graph"),
            "model_versions": t.get("model_versions", {}), "review_note": e.get("review_note")}


@app.post("/v1/review/queue/{item_id}/resolve")
def review_resolve(item_id: str, body: dict):
    e = next((x for x in ESCALATIONS if x["id"] == item_id), None)
    if not e:
        return {"error": {"message": "not found"}}
    decision = body.get("decision")
    if decision not in ("approved", "revised", "rejected"):
        return {"error": {"message": "decision must be approved|revised|rejected"}}
    e["status"] = "reviewed"
    e["decision"] = decision
    e["review_note"] = body.get("note", "")
    e["reviewed_by"] = "demo-reviewer"
    t = REQUESTS.get(e["request_id"])
    if t:
        if decision == "revised" and body.get("revised_response"):
            t["final_response"] = body["revised_response"]
            t["action"] = "answer"
        elif decision == "rejected":
            t["final_response"] = "Withheld by human reviewer. " + body.get("note", "")
            t["action"] = "abstain"
        elif decision == "approved":
            t["action"] = "answer"
    return {"id": item_id, "status": "reviewed", "decision": decision}


@app.get("/v1/kb/documents")
def kb_documents():
    docs: dict[str, dict] = {}
    for m in CORPUS.meta:
        d = docs.setdefault(m["document_id"], {"id": m["document_id"], "title": m["document_title"],
                                               "source": m["source"], "authority": m["authority"],
                                               "chunks": 0})
        d["chunks"] += 1
    return list(docs.values())


@app.post("/v1/kb/search")
def kb_search(body: dict):
    evs = CORPUS.retrieve(body.get("query", ""), rerank_k=body.get("k", 6))
    return [
        {"chunk_id": e.chunk_id, "document_title": e.document_title, "text": e.text,
         "vector_score": round(e.vector_score, 4), "keyword_score": round(e.keyword_score, 4),
         "fused_score": round(e.fused_score, 5), "rerank_score": round(e.rerank_score, 4)}
        for e in evs
    ]


@app.post("/v1/kb/documents", status_code=201)
def kb_ingest(body: dict):
    return {"note": "demo server corpus is read-only; use the Docker stack to ingest",
            "title": body.get("title")}


@app.post("/v1/eval/run", status_code=202)
def eval_run(limit: int = 8):
    from app.eval.datasets import load_jsonl
    from app.eval.metrics import creativity_scores, reliability_index, unsupported_claim_rate

    ds = os.path.join(os.path.dirname(CORPUS_DIR), "benchmark", "benchmark.jsonl")
    rows = load_jsonl(ds)[:limit]
    run_id = str(uuid.uuid4())
    pareto: list[dict] = []
    m_rows: list[dict] = []
    for i, row in enumerate(rows):
        st = run_pipeline(None, tenant_id="demo", prompt=row["prompt"], persist=False)
        claims = [c.model_dump() for c in st.claim_graph.claims]
        cr = creativity_scores(st.final_response, st.candidates)
        m = {"unsupported_rate": round(unsupported_claim_rate(claims), 3),
             "citation_precision": round(len([c for c in claims if c["verdict"] == "supported"])
                                         / max(1, len(claims)), 3),
             "entailment": 0.6, "ece": 0.1,
             "creativity": cr["distinct_2"] * 0.5 + cr["diversity"] * 0.5}
        m["reliability"] = round(reliability_index(m), 3)
        m_rows.append(m)
        pareto.append({"system": "ma-ahaf", "id": row.get("id", i), "type": row.get("type"),
                       "creativity": round(m["creativity"], 3), "reliability": m["reliability"]})
    agg = {k: round(sum(r[k] for r in m_rows) / len(m_rows), 4)
           for k in ("unsupported_rate", "citation_precision", "reliability", "creativity")} if m_rows else {}
    EVAL_RUNS[run_id] = {
        "id": run_id, "dataset": "benchmark.jsonl", "status": "done",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {"n": len(rows), "ma_ahaf": agg, "static_rag": {}, "deltas": {},
                    "pareto_frontier_gain": 0.0},
        "pareto": pareto,
    }
    return {"eval_run_id": run_id, "status": "done"}


@app.get("/v1/eval/runs")
def eval_runs():
    return sorted(EVAL_RUNS.values(), key=lambda r: r["created_at"], reverse=True)


@app.get("/v1/eval/runs/{run_id}")
def eval_run_detail(run_id: str):
    return EVAL_RUNS.get(run_id) or {"error": {"message": "not found"}}


@app.get("/v1/graph")
def graph():
    return {"mermaid": (
        "graph TD; intent-->risk-->policy-->pre_retrieve-->generate-->decompose-->retrieve"
        "-->verify-->risk_scoring-->creativity-->decide-->finalize"
    )}


# ---- serve the built dashboard from the same origin, if it exists ----
_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.isdir(_DIST):
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str = ""):
        candidate = os.path.join(_DIST, path)
        if path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_DIST, "index.html"))
    log.info("serve_demo.dashboard_mounted", dist=_DIST)


if __name__ == "__main__":
    import uvicorn

    print(f"\nMA-AHAF demo server  |  mode: {os.environ['MAAHAF_LLM__PROVIDER']}  |  "
          f"corpus: {len(CORPUS.texts)} chunks")
    if os.path.isdir(_DIST):
        print("DASHBOARD -> http://localhost:8000")
    else:
        print("dashboard not built yet — run:  cd frontend && npm install && npm run build")
    print("API docs  -> http://localhost:8000/docs\n")
    # demo server has NO auth — bind to loopback only
    uvicorn.run(app, host="127.0.0.1", port=8000)
