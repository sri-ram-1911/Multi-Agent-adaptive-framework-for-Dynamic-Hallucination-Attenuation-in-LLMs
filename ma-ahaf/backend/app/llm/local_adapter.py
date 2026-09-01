"""Local / open-weight adapter via an OpenAI-compatible endpoint (Ollama, vLLM, TGI).

Used for *verifier diversity* — running verification on a different model family
than generation reduces shared-bias failure modes (proposal §2, "verifier
dependence").
"""

from __future__ import annotations

import statistics

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.llm.base import LLMAdapter, LLMResponse, Message


class LocalAdapter(LLMAdapter):
    provider = "local"

    def __init__(self) -> None:
        self._client = OpenAI(
            base_url=settings.llm.local_base_url,
            api_key="local",
            timeout=settings.llm.request_timeout_s,
        )

    @retry(stop=stop_after_attempt(settings.llm.max_retries),
           wait=wait_exponential(multiplier=1, min=1, max=20), reraise=True)
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
        resp = self._client.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
        )
        choice = resp.choices[0]
        avg_lp = None
        lp = getattr(choice, "logprobs", None)
        if lp and getattr(lp, "content", None):
            vals = [t.logprob for t in lp.content if t.logprob is not None]
            avg_lp = statistics.fmean(vals) if vals else None
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=choice.message.content or "",
            model=f"local:{model}",
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
            avg_logprob=avg_lp,
            finish_reason=choice.finish_reason or "stop",
        )
