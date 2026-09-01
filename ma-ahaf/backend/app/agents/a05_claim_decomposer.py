"""Agent 5 — Claim Decomposer (proposal §5, §7).

Extracts atomic claims from the working candidate, classifies claim type (DL/ML
claim-type model), estimates criticality + temporal sensitivity, extracts
entities, and seeds the Claim Risk Graph with simple dependency edges.
"""

from __future__ import annotations

import re
import uuid

from app.agents.base import Agent
from app.claimgraph.schema import Claim, ClaimGraph
from app.ml import registry
from app.orchestration.state import RequestState

_SYS = (
    "You decompose an assistant answer into atomic, independently checkable claims. "
    "Return JSON {\"claims\": [{\"text\": str, \"type\": one of "
    "factual|numeric|causal|temporal|opinion|creative, \"criticality\": 0..1, "
    "\"entities\": [str]}]}. Exclude pure stylistic text. Keep each claim one sentence."
)
_TEMPORAL_RE = re.compile(r"\b(19|20)\d{2}\b|\b(today|now|currently|as of|latest|recent)\b", re.I)
_CREATIVE_MARKERS = ("imagine", "story", "poem", "metaphor", "fictional", "let's pretend")


def _classify_type(text: str, llm_type: str) -> str:
    model = registry.load("claim_type.joblib")
    if model is not None:
        try:
            return str(model.predict([text])[0])
        except Exception:  # pragma: no cover
            pass
    return llm_type or "factual"


class ClaimDecomposer(Agent):
    name = "claim_decomposer"
    number = 5

    def _run(self, state: RequestState):
        draft = state.chosen_candidate
        data = state.gateway.complete_json(
            "decomposer",
            [{"role": "system", "content": _SYS}, {"role": "user", "content": draft}],
            temperature=0.0,
            max_tokens=800,
        )
        raw_claims = data.get("claims", [])
        if not raw_claims:  # fallback: sentence split
            raw_claims = [
                {"text": s.strip()}
                for s in re.split(r"(?<=[.!?])\s+", draft)
                if len(s.strip()) > 15
            ]

        claims: list[Claim] = []
        for i, rc in enumerate(raw_claims[:12]):
            text = str(rc.get("text", "")).strip()
            if not text:
                continue
            ctype = _classify_type(text, str(rc.get("type", "")))
            lower = text.lower()
            if any(m in lower for m in _CREATIVE_MARKERS):
                ctype = "creative"
            # on an explicitly creative request, only keep a claim as factual when
            # the LLM itself flagged it as such — the rest is creative latitude.
            if state.task_type == "creative" and str(rc.get("type", "")) not in ("factual", "numeric"):
                ctype = "creative"
            temporal = 0.8 if _TEMPORAL_RE.search(text) else (0.3 if ctype == "temporal" else 0.0)
            crit = float(rc.get("criticality", 0.6 if ctype in ("factual", "numeric", "causal") else 0.3))
            span = None
            idx = draft.find(text[:40])
            if idx >= 0:
                span = (idx, idx + len(text))
            claims.append(
                Claim(
                    id=str(uuid.uuid4()),
                    ordinal=i,
                    text=text,
                    claim_type=ctype,  # type: ignore[arg-type]
                    criticality=round(min(1.0, crit), 3),
                    temporal_sensitivity=temporal,
                    entities=[e for e in rc.get("entities", []) if isinstance(e, str)][:6],
                    span=span,
                )
            )

        # naive dependency edges: a claim depends on earlier claims sharing an entity
        deps: dict[str, list[str]] = {}
        for c in claims:
            for earlier in claims:
                if earlier.ordinal < c.ordinal and set(earlier.entities) & set(c.entities):
                    deps.setdefault(c.id, []).append(earlier.id)

        state.claim_graph = ClaimGraph(claims=claims, dependencies=deps)
        return (
            {"n_claims": len(claims),
             "claims": [{"text": c.text, "type": c.claim_type, "criticality": c.criticality}
                        for c in claims]},
            f"decomposed into {len(claims)} atomic claims",
            state.gateway.model_for("decomposer"),
        )
