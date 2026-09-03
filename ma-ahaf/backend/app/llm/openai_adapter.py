"""OpenAI Chat Completions adapter with logprob-based uncertainty."""

from __future__ import annotations

import statistics

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.llm.base import LLMAdapter, LLMResponse, Message


class OpenAIAdapter(LLMAdapter):
    provider = "openai"

    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.openai_api_key,  # falls back to env var if None
            timeout=settings.llm.request_timeout_s,
        )

    @retry(
        stop=stop_after_attempt(settings.llm.max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        reraise=True,
    )
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
        kwargs: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if want_logprobs:
            kwargs["logprobs"] = True
        if response_format:
            kwargs["response_format"] = response_format

        resp = self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        avg_lp: float | None = None
        if want_logprobs and choice.logprobs and choice.logprobs.content:
            lps = [t.logprob for t in choice.logprobs.content if t.logprob is not None]
            if lps:
                avg_lp = statistics.fmean(lps)

        usage = resp.usage
        return LLMResponse(
            text=choice.message.content or "",
            model=model,
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
            avg_logprob=avg_lp,
            finish_reason=choice.finish_reason or "stop",
        )
