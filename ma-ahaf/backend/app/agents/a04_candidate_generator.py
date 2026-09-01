"""Agent 4 — Candidate Generator (proposal §7).

Generates one or more candidate responses under policy constraints. Temperature
and the system prompt are derived from the policy vector (grounding intensity,
creativity allowance, citation requirement).
"""

from __future__ import annotations

from app.agents.base import Agent
from app.orchestration.state import RequestState


def _system_prompt(state: RequestState) -> str:
    pv = state.policy
    parts = ["You are a careful assistant inside a hallucination-attenuation framework."]
    if pv.grounding_intensity > 0.6:
        parts.append("Ground every factual statement in verifiable knowledge; avoid speculation.")
    if pv.citation_requirement > 0.6:
        parts.append("Attach bracketed source hints like [S1], [S2] to factual claims.")
    if pv.creativity_allowance > 0.6:
        parts.append("Creative or speculative content is welcome; clearly label it as such.")
    elif pv.creativity_allowance < 0.3:
        parts.append("Do not add creative flourishes; be precise and literal.")
    if state.task_type == "mixed":
        parts.append("Separate factual claims, assumptions, and creative proposals into labelled parts.")
    parts.append("If evidence is likely insufficient, say so rather than guessing.")
    return " ".join(parts)


class CandidateGenerator(Agent):
    name = "candidate_generator"
    number = 4

    def _run(self, state: RequestState):
        pv = state.policy
        n = max(1, min(pv.candidates, state.policy_overrides.get("candidates", pv.candidates)))
        temperature = round(0.15 + 0.7 * pv.creativity_allowance, 2)

        sys = _system_prompt(state)
        ctx_parts = []
        if state.context:
            ctx_parts.append(state.context)
        if state.evidence:  # grounding-first retrieval already ran
            ctx_parts.append(
                "\n".join(f"[S{i + 1}] {e.text}" for i, e in enumerate(state.evidence[:5]))
            )
        context = "\n\n".join(ctx_parts)
        user = (
            f"{state.prompt}\n\nContext:\n{context}" if context else state.prompt
        )
        if context:
            sys = (
                "Answer the question in 2-4 sentences using ONLY the context. "
                "Cite each fact with its [S#] tag. If the context does not answer it, "
                "say 'The available sources do not cover this.'"
            )
        candidates: list[str] = []
        for i in range(int(n)):
            resp = state.gateway.complete(
                "generator",
                [{"role": "system", "content": sys}, {"role": "user", "content": user}],
                temperature=temperature + 0.1 * i,
                max_tokens=700,
                want_logprobs=True,
            )
            candidates.append(resp.text.strip())
            if i == 0 and resp.avg_logprob is not None:
                state.signals.model_confidence = round(1.0 - resp.uncertainty, 3)

        state.candidates = candidates
        # pick the most grounded-sounding candidate as the working draft (longest
        # with most citation markers is a cheap proxy; verification decides later)
        state.chosen_candidate = max(candidates, key=lambda c: (c.count("[S"), len(c)))
        return (
            {"n": len(candidates), "temperature": temperature,
             "model_confidence": state.signals.model_confidence,
             "candidates": [c[:400] for c in candidates]},
            f"generated {len(candidates)} candidate(s) @ temp {temperature}",
            state.gateway.model_for("generator"),
        )
