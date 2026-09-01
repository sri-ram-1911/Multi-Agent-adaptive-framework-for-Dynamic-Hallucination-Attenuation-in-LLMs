"""Local HuggingFace seq2seq adapter (no API key, no network after first download).

Uses an instruction-tuned model (default ``google/flan-t5-base``) for every LLM
role. Quality is well below GPT-4o but it exercises the real pipeline end-to-end
with genuine generated text. Select with ``MAAHAF_LLM__PROVIDER=hf``.
"""

from __future__ import annotations

import re
import threading

from app.config import settings
from app.core.logging import get_logger
from app.llm.base import LLMAdapter, LLMResponse, Message

log = get_logger("hf_adapter")
_lock = threading.Lock()
_pipe = None


def _load():
    global _pipe
    if _pipe is None:
        with _lock:
            if _pipe is None:
                from transformers import pipeline

                model = settings.llm.hf_model
                log.info("hf_adapter.loading", model=model)
                _pipe = pipeline("text2text-generation", model=model)
    return _pipe


def _flatten(messages: list[Message]) -> str:
    sys = " ".join(m["content"] for m in messages if m["role"] == "system")
    user = "\n".join(m["content"] for m in messages if m["role"] != "system")
    if sys:
        return f"{sys.strip()}\n\n{user.strip()}"
    return user.strip()


class HFAdapter(LLMAdapter):
    provider = "hf"

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
        pipe = _load()
        prompt = _flatten(messages)
        do_sample = temperature > 0.35

        def _gen(p: str, *, minlen: int = 1) -> str:
            return pipe(
                p,
                max_new_tokens=min(max_tokens, 320),
                min_new_tokens=minlen,
                do_sample=do_sample,
                temperature=max(0.1, temperature) if do_sample else None,
                num_beams=1 if do_sample else 4,
                no_repeat_ngram_size=3,
            )[0]["generated_text"].strip()

        user_txt = "\n".join(m["content"] for m in messages if m["role"] != "system")
        is_generation = "Context:" in user_txt and "?" in user_txt

        if is_generation:
            # flan-t5 does best with an explicit read-then-answer framing and a
            # minimum length, otherwise it returns a two-word short answer.
            q, _, ctx = user_txt.partition("Context:")
            out = _gen(
                "Using only the context, write a complete 2-4 sentence answer that "
                "addresses every part of the question. Keep each [S#] tag next to the "
                f"fact it supports.\n\ncontext:\n{ctx.strip()[:1800]}\n\nquestion: {q.strip()}",
                minlen=24,
            )
        else:
            out = _gen(prompt)

        # flan-t5 rarely emits valid JSON; nudge obvious cases into shape
        if response_format and response_format.get("type") == "json_object" and not out.startswith("{"):
            out = _coerce_json(prompt, out)

        approx_in = len(prompt) // 4
        approx_out = len(out) // 4
        return LLMResponse(
            text=out,
            model=f"hf:{settings.llm.hf_model}",
            tokens_in=approx_in,
            tokens_out=approx_out,
            avg_logprob=-0.35,  # fixed moderate-uncertainty proxy
        )


def _coerce_json(prompt: str, text: str) -> str:
    import json

    low = prompt.lower()
    if "verdict" in low:
        v = "supported" if re.search(r"\b(support|entail|correct|yes)\b", text, re.I) else (
            "refuted" if re.search(r"\b(refut|contradict|false|no)\b", text, re.I) else "insufficient"
        )
        return json.dumps({"verdict": v, "rationale": text[:200]})
    if "atomic" in low or "claims" in low:
        parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 12]
        return json.dumps({"claims": [{"text": p, "type": "factual"} for p in parts[:6]]})
    if "queries" in low:
        return json.dumps({"queries": [text[:80]]})
    if "task_type" in low or "intent" in low:
        return json.dumps({"task_type": "factual", "ambiguity": 0.3})
    return "{}"
