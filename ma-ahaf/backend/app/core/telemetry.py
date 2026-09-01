"""OpenTelemetry tracing + Prometheus metrics."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

from prometheus_client import Counter, Gauge, Histogram

from app.config import settings
from app.core.logging import get_logger

log = get_logger("telemetry")

# ---- Prometheus metrics ----
REQUESTS = Counter("maahaf_requests_total", "Generate requests", ["action"])
REQUEST_LATENCY = Histogram(
    "maahaf_request_latency_seconds", "End-to-end /v1/generate latency",
    buckets=(0.5, 1, 2, 3, 5, 8, 13, 21, 34),
)
AGENT_LATENCY = Histogram(
    "maahaf_agent_latency_seconds", "Per-agent latency", ["agent"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8),
)
TOKENS = Counter("maahaf_tokens_total", "LLM tokens", ["role", "direction"])
LLM_COST = Counter("maahaf_llm_cost_usd_total", "Estimated LLM cost (USD)", ["role"])
VERIFICATION_DEPTH = Histogram(
    "maahaf_verification_depth", "Chosen verification depth (0=light,1=std,2=deep)",
    buckets=(0, 1, 2),
)
ABSTENTIONS = Counter("maahaf_abstentions_total", "Abstain/escalate decisions", ["kind"])
AGENT_DISAGREEMENT = Gauge("maahaf_agent_disagreement", "Last request agent disagreement [0,1]")
HALLUCINATION_RISK = Histogram(
    "maahaf_max_claim_risk", "Max claim-level hallucination risk per request",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

_tracer = None


def init_telemetry(app=None) -> None:  # noqa: ANN001
    global _tracer
    if not settings.otel_enabled:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": settings.service_name}))
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True))
        )
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("maahaf")
        if app is not None:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        log.info("otel.initialised", endpoint=settings.otel_exporter_otlp_endpoint)
    except Exception as exc:  # pragma: no cover - telemetry must never break the app
        log.warning("otel.init_failed", error=str(exc))


@contextlib.contextmanager
def span(name: str, **attrs: object) -> Iterator[None]:
    if _tracer is None:
        yield
        return
    with _tracer.start_as_current_span(name) as s:  # pragma: no cover
        for k, v in attrs.items():
            s.set_attribute(k, v if isinstance(v, (str, int, float, bool)) else str(v))
        yield
