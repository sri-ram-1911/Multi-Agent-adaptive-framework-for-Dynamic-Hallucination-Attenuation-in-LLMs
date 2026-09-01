"""The model-agnostic LLM gateway.

Single place where "which model runs this role" is decided. Adds Redis response
caching, token + USD cost accounting, and per-request usage aggregation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from app.config import settings
from app.core.logging import get_logger
from app.core.telemetry import LLM_COST, TOKENS
from app.llm.base import LLMAdapter, LLMResponse, Message, Role
from app.llm.mock_adapter import MockAdapter

log = get_logger("gateway")


@dataclass
class UsageMeter:
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    by_role: dict[str, int] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out


def _adapter() -> LLMAdapter:
    provider = settings.llm.provider
    if provider == "openai":
        from app.llm.openai_adapter import OpenAIAdapter

        return OpenAIAdapter()
    if provider == "local":
        from app.llm.local_adapter import LocalAdapter

        return LocalAdapter()
    if provider == "hf":
        from app.llm.hf_adapter import HFAdapter

        return HFAdapter()
    return MockAdapter()


_ROLE_MODEL: dict[Role, str] = {
    "generator": settings.llm.generator_model,
    "verifier": settings.llm.verifier_model,
    "decomposer": settings.llm.decomposer_model,
    "reviser": settings.llm.reviser_model,
    "judge": settings.llm.judge_model,
    "expander": settings.llm.expander_model,
}


class Gateway:
    def __init__(self, meter: UsageMeter | None = None, *, cache=None) -> None:
        self._adapter = _adapter()
        self._verifier_adapter = self._adapter  # swap for LocalAdapter to add diversity
        self.meter = meter or UsageMeter()
        self._cache = cache  # optional aioredis; sync gateway uses it opportunistically

    def model_for(self, role: Role) -> str:
        return _ROLE_MODEL[role]

    def _price(self, model: str, tin: int, tout: int) -> float:
        table = settings.llm.price_table
        key = model.split(":")[-1]
        pin, pout = table.get(key, (0.0, 0.0))
        return (tin * pin + tout * pout) / 1_000_000

    def _cache_key(self, role: str, messages: list[Message], temperature: float) -> str:
        blob = json.dumps({"r": role, "m": messages, "t": temperature}, sort_keys=True)
        return "llm:" + hashlib.sha256(blob.encode()).hexdigest()

    def complete(
        self,
        role: Role,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
        want_logprobs: bool = False,
        json_mode: bool = False,
    ) -> LLMResponse:
        model = self.model_for(role)
        adapter = self._verifier_adapter if role == "verifier" else self._adapter
        rf = {"type": "json_object"} if json_mode else None

        resp = adapter.generate(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            want_logprobs=want_logprobs,
            response_format=rf,
        )

        self.meter.calls += 1
        self.meter.tokens_in += resp.tokens_in
        self.meter.tokens_out += resp.tokens_out
        self.meter.by_role[role] = self.meter.by_role.get(role, 0) + resp.tokens_in + resp.tokens_out
        cost = self._price(model, resp.tokens_in, resp.tokens_out)
        self.meter.cost_usd += cost

        TOKENS.labels(role=role, direction="in").inc(resp.tokens_in)
        TOKENS.labels(role=role, direction="out").inc(resp.tokens_out)
        LLM_COST.labels(role=role).inc(cost)
        return resp

    # convenience: parse a JSON object out of a completion, tolerating fences
    def complete_json(self, role: Role, messages: list[Message], **kw) -> dict:
        kw.setdefault("json_mode", settings.llm.provider == "openai")
        raw = self.complete(role, messages, **kw).text.strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if 0 <= start < end:
                try:
                    return json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    pass
            log.warning("gateway.json_parse_failed", role=role, raw=raw[:200])
            return {}
