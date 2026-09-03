"""Build a networkx dependency graph over claims / entities / evidence.

Used for: (a) propagating risk from a claim to claims that depend on it, and
(b) rendering the Claim Risk Graph in the dashboard.
"""

from __future__ import annotations

import networkx as nx

from app.claimgraph.schema import ClaimGraph


def build_nx(cg: ClaimGraph) -> nx.DiGraph:
    g = nx.DiGraph()
    for c in cg.claims:
        g.add_node(c.id, kind="claim", text=c.text, risk=c.risk_score, verdict=c.verdict,
                   claim_type=c.claim_type)
        for ent in c.entities:
            g.add_node(f"e:{ent}", kind="entity", text=ent)
            g.add_edge(c.id, f"e:{ent}", kind="mentions")
        for ev in c.evidence_ids:
            g.add_node(f"v:{ev}", kind="evidence", text=ev)
            g.add_edge(f"v:{ev}", c.id, kind="supports")
    for src, deps in cg.dependencies.items():
        for d in deps:
            g.add_edge(d, src, kind="depends_on")
    return g


def propagate_risk(cg: ClaimGraph, *, decay: float = 0.5) -> ClaimGraph:
    """If claim A depends on B, A cannot be considered *less* risky than a
    decayed fraction of its riskiest dependency.

    This is a bounded floor, not an accumulator: a claim's risk is lifted toward
    ``decay * max(dependency risk)`` but never pushed above it, so a well-grounded
    claim stays low-risk even in a densely connected graph and the propagated
    value can never exceed the true maximum claim risk already present.
    """
    g = build_nx(cg)
    by_id = {c.id: c for c in cg.claims}
    try:
        order = list(nx.topological_sort(g.subgraph([c.id for c in cg.claims])))
    except nx.NetworkXUnfeasible:
        order = [c.id for c in cg.claims]
    base_risk = {c.id: c.risk_score for c in cg.claims}
    for cid in order:
        claim = by_id.get(cid)
        if claim is None:
            continue
        deps = [d for d in cg.dependencies.get(cid, []) if d in by_id]
        if not deps:
            continue
        dep_risk = max(by_id[d].risk_score for d in deps)
        claim.risk_score = round(min(1.0, max(base_risk[cid], decay * dep_risk)), 4)
    return cg


def to_cytoscape(cg: ClaimGraph) -> dict:
    g = build_nx(cg)
    return {
        "nodes": [{"data": {"id": n, **d}} for n, d in g.nodes(data=True)],
        "edges": [{"data": {"source": u, "target": v, **d}} for u, v, d in g.edges(data=True)],
    }
