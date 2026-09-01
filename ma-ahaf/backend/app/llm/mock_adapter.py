"""Deterministic mock adapter — offline dev + reproducible tests.

It produces plausible, structured outputs for each agent role so the whole
orchestration graph can run end-to-end with no network access.
"""

from __future__ import annotations

import hashlib
import json
import re

from app.llm.base import LLMAdapter, LLMResponse, Message


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest(), 16)


class MockAdapter(LLMAdapter):
    provider = "mock"

    def generate(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
        want_logprobs: bool = False,
        response_format: dict | None = None,
    ) -> LLMResponse:
        system = " ".join(m["content"] for m in messages if m["role"] == "system").lower()
        user = " ".join(m["content"] for m in messages if m["role"] == "user")
        s = _seed(system + user)

        if "decompose" in system or "atomic claim" in system:
            sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", user) if len(x.strip()) > 12]
            claims = sentences[:5] or [user[:120]]
            text = json.dumps({"claims": [{"text": c, "type": "factual"} for c in claims]})
        elif "verify" in system or "entail" in system:
            verdict = ["supported", "insufficient", "refuted"][s % 3]
            text = json.dumps({"verdict": verdict, "rationale": "mock NLI judgement"})
        elif "revise" in system:
            text = user.replace(" clearly", "").replace(" obviously", "") + "\n\n(Revised for evidential support.)"
        elif "expand" in system or "query" in system:
            text = json.dumps({"queries": [user, f"{user} definition", f"{user} evidence"]})
        elif "classify" in system or "intent" in system:
            t = ["factual", "analytical", "creative", "mixed", "high_stakes"][s % 5]
            text = json.dumps({"task_type": t, "ambiguity": (s % 100) / 100})
        else:  # generator
            text = (
                f"Based on available evidence, here is a response to: {user[:80]}.\n"
                "Key facts are grounded in the knowledge base; uncertain points are flagged."
            )

        return LLMResponse(
            text=text,
            model=f"mock:{model}",
            tokens_in=sum(len(m["content"]) for m in messages) // 4,
            tokens_out=len(text) // 4,
            avg_logprob=-0.2 - (s % 30) / 100,
        )
