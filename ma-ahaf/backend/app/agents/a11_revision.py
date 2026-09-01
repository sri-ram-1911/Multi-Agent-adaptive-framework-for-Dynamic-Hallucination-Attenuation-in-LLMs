"""Agent 11 — Revision Agent (proposal §7).

Rewrites unsupported or overconfident content while a Creativity Preservation
Gate protects explicitly creative spans from factual rewriting (proposal §5).
Returns a revised draft; the orchestrator may loop back to verification.
"""

from __future__ import annotations

from app.agents.base import Agent
from app.orchestration.state import RequestState

_SYS = (
    "You revise an assistant answer to remove hallucination risk. Rules:\n"
    "- Remove or hedge claims marked UNSUPPORTED/REFUTED; never invent new facts.\n"
    "- Soften overconfident phrasing where evidence is weak (add 'according to', "
    "'evidence suggests', or explicit uncertainty).\n"
    "- Keep well-supported claims and their [S#] markers intact.\n"
    "- Do NOT alter text inside <keep>...</keep> — it is intentionally creative.\n"
    "- Preserve the original structure and usefulness. Return only the revised answer."
)


class Revision(Agent):
    name = "revision"
    number = 11

    def _run(self, state: RequestState):
        cg = state.claim_graph
        problems = [
            c for c in cg.claims
            if c.verdict in ("refuted", "insufficient") or c.risk_level == "high"
            or (c.contradiction_score > 0.5)
        ]
        if not problems:
            return ({"revised": False, "problem_claims": 0}, "no revision needed", None)

        draft = state.chosen_candidate
        # wrap creative spans so the model leaves them alone
        for start, end in sorted(state.creative_spans, reverse=True):
            draft = draft[:start] + "<keep>" + draft[start:end] + "</keep>" + draft[end:]

        problem_list = "\n".join(
            f"- [{c.verdict.upper()}/{c.risk_level}] {c.text}" for c in problems
        )
        supported_list = "\n".join(
            f"- {c.text}" for c in cg.claims if c.verdict == "supported"
        ) or "(none)"

        resp = state.gateway.complete(
            "reviser",
            [
                {"role": "system", "content": _SYS},
                {"role": "user", "content":
                    f"ANSWER:\n{draft}\n\nPROBLEM CLAIMS:\n{problem_list}\n\n"
                    f"SUPPORTED CLAIMS (keep):\n{supported_list}"},
            ],
            temperature=0.1, max_tokens=800,
        )
        revised = resp.text.replace("<keep>", "").replace("</keep>", "").strip()

        state.chosen_candidate = revised
        state.revised = True
        state.revision_loops += 1
        return (
            {"revised": True, "problem_claims": len(problems),
             "revision_loop": state.revision_loops, "preview": revised[:400]},
            f"revised {len(problems)} problem claim(s), loop {state.revision_loops}",
            state.gateway.model_for("reviser"),
        )
