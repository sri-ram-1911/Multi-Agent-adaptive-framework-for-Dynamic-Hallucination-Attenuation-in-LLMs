"""Agent base class. Orchestration only ever calls `Agent.run(state)`."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from app.core.logging import get_logger
from app.core.telemetry import AGENT_LATENCY
from app.orchestration.state import AgentRecord, RequestState

log = get_logger("agent")


class Agent(ABC):
    name: str = "agent"
    #: proposal §7 agent number
    number: int = 0

    @abstractmethod
    def _run(self, state: RequestState) -> tuple[dict, str, str | None]:
        """Return (output_dict, rationale, model_version). Mutate `state` in place."""

    def run(self, state: RequestState) -> RequestState:
        t0 = time.perf_counter()
        tokens_before = state.gateway.meter.total_tokens if state.gateway else 0
        try:
            output, rationale, model_version = self._run(state)
        except Exception as exc:  # pragma: no cover - defensive; agents must not crash the graph
            log.error("agent.error", agent=self.name, error=str(exc))
            output, rationale, model_version = {"error": str(exc)}, f"failed: {exc}", None
        dt_ms = int((time.perf_counter() - t0) * 1000)
        tokens = (state.gateway.meter.total_tokens if state.gateway else 0) - tokens_before
        AGENT_LATENCY.labels(agent=self.name).observe(dt_ms / 1000)
        state.add_record(
            AgentRecord(
                agent=self.name,
                output=output,
                rationale=rationale,
                latency_ms=dt_ms,
                tokens=tokens,
                model_version=model_version,
            )
        )
        log.info("agent.done", agent=self.name, latency_ms=dt_ms, tokens=tokens)
        return state
