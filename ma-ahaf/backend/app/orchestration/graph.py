"""LangGraph state machine implementing the proposal §6 flow:

intent → risk → policy → generate → decompose → retrieve(+source quality)
      → verify(+contradiction) → risk-scoring → creativity
      → [revise → verify ...]  (conditional, bounded loop)
      → decide → finalize(+audit)
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.orchestration import nodes as N
from app.orchestration.nodes import needs_revision as _needs_revision
from app.orchestration.state import RequestState


def build_graph():
    g = StateGraph(RequestState)
    g.add_node("intent", N.n_intent)
    g.add_node("risk", N.n_risk)
    g.add_node("policy", N.n_policy)
    g.add_node("pre_retrieve", N.n_pre_retrieve)
    g.add_node("generate", N.n_generate)
    g.add_node("decompose", N.n_decompose)
    g.add_node("retrieve", N.n_retrieve)
    g.add_node("verify", N.n_verify)
    g.add_node("risk_scoring", N.n_risk_scoring)
    g.add_node("creativity", N.n_creativity)
    g.add_node("revise", N.n_revise)
    g.add_node("decide", N.n_decide)
    g.add_node("finalize", N.n_finalize)

    g.add_edge(START, "intent")
    g.add_edge("intent", "risk")
    g.add_edge("risk", "policy")
    g.add_edge("policy", "pre_retrieve")
    g.add_edge("pre_retrieve", "generate")
    g.add_edge("generate", "decompose")
    g.add_edge("decompose", "retrieve")
    g.add_edge("retrieve", "verify")
    g.add_edge("verify", "risk_scoring")
    g.add_edge("risk_scoring", "creativity")
    g.add_conditional_edges("creativity", _needs_revision, {"revise": "revise", "decide": "decide"})
    g.add_edge("revise", "decompose")   # re-decompose + re-retrieve + re-verify the revised draft
    g.add_edge("decide", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


_compiled = None


def get_compiled_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled
