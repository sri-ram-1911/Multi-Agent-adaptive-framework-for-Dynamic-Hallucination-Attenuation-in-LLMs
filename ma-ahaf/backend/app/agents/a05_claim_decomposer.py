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


_VALID_TYPES = {"factual", "numeric", "causal", "temporal", "opinion", "creative"}
# labels an LLM commonly returns that aren't in our enum -> nearest valid type
_TYPE_ALIASES = {
    "assumption": "opinion", "speculation": "opinion", "belief": "opinion",
    "prediction": "causal", "hypothesis": "causal", "conclusion": "causal",
    "recommendation": "opinion", "proposal": "creative", "statistic": "numeric",
    "quantitative": "numeric", "date": "temporal", "fact": "factual",
}


def _classify_type(text: str, llm_type: str) -> str:
    model = registry.load("claim_type.joblib")
    if model is not None:
        try:
            pred = str(model.predict([text])[0]).lower()
            if pred in _VALID_TYPES:
                return pred
        except Exception:  # pragma: no cover
            pass
    t = (llm_type or "").strip().lower()
    if t in _VALID_TYPES:
        return t
    return _TYPE_ALIASES.get(t, "factual")


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
        def _sentence_claims() -> list[dict]:
            return [
                {"text": s.strip()}
                for s in re.split(r"(?<=[.!?])\s+", draft)
                if len(s.strip()) > 15
            ]

        raw_claims = data.get("claims", []) or _sentence_claims()

        claims: list[Claim] = []
        for i, rc in enumerate(raw_claims[:12]):
            if not isinstance(rc, dict):
                rc = {"text": str(rc)}
            text = str(rc.get("text", "")).strip()
            if not text:
                continue
            ctype = _classify_type(text, str(rc.get("type", "")))
            lower = text.lower()
            if any(m in lower for m in _CREATIVE_MARKERS):
                ctype = "creative"
            # on an explicitly creative request everything is creative latitude —
            # a poem/story line is not a checkable proposition — UNLESS it states
            # a hard, verifiable specific (a number, year, or measurement), which
            # we still fact-check even inside creative output.
            if state.task_type == "creative" and not re.search(r"\d", text):
                ctype = "creative"
            temporal = 0.8 if _TEMPORAL_RE.search(text) else (0.3 if ctype == "temporal" else 0.0)
            try:
                crit = float(rc.get("criticality", 0.6 if ctype in ("factual", "numeric", "causal") else 0.3))
            except (TypeError, ValueError):
                crit = 0.5
            span = None
            idx = draft.find(text[:40])
            if idx >= 0:
                span = (idx, idx + len(text))
            try:
                claims.append(
                    Claim(
                        id=str(uuid.uuid4()),
                        ordinal=i,
                        text=text,
                        claim_type=ctype,  # type: ignore[arg-type]
                        criticality=round(min(1.0, max(0.0, crit)), 3),
                        temporal_sensitivity=temporal,
                        entities=[e for e in rc.get("entities", []) if isinstance(e, str)][:6],
                        span=span,
                    )
                )
            except Exception:  # never let a single malformed claim abort decomposition
                claims.append(Claim(id=str(uuid.uuid4()), ordinal=i, text=text,
                                    claim_type="factual", criticality=0.5))

        # last-resort: LLM returned claims but none survived -> split the draft
        if not claims and len(draft.split()) >= 4 and state.task_type != "creative":
            for i, s in enumerate(_sentence_claims()[:12]):
                claims.append(Claim(id=str(uuid.uuid4()), ordinal=i, text=s["text"],
                                    claim_type="factual", criticality=0.5))

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
