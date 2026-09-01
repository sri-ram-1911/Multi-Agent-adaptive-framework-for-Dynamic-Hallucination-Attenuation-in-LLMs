"""Model-agnostic LLM adapter contract (proposal §12)."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["generator", "verifier", "decomposer", "reviser", "judge", "expander"]

Message = dict[str, str]  # {"role": "system"|"user"|"assistant", "content": str}


@dataclass
class LLMResponse:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    # Mean token log-probability of the completion, when available. Used as a
    # model-uncertainty signal by the hallucination risk model.
    avg_logprob: float | None = None
    finish_reason: str = "stop"
    raw: dict = field(default_factory=dict)

    @property
    def uncertainty(self) -> float:
        """0 (confident) .. 1 (uncertain), derived from avg_logprob."""
        if self.avg_logprob is None:
            return 0.5
        # perplexity -> squashed to [0, 1]
        ppl = math.exp(-self.avg_logprob)
        return max(0.0, min(1.0, (ppl - 1.0) / 9.0))


class LLMAdapter(ABC):
    provider: str = "base"

    @abstractmethod
    def generate(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
        want_logprobs: bool = False,
        response_format: dict | None = None,
    ) -> LLMResponse: ...
