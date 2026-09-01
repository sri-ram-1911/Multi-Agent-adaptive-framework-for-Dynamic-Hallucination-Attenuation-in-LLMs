"""Test config — force fully-offline deterministic mode."""

from __future__ import annotations

import os

os.environ.setdefault("MAAHAF_LLM__PROVIDER", "mock")
os.environ.setdefault("MAAHAF_OTEL_ENABLED", "false")
os.environ.setdefault("MAAHAF_PII_REDACTION", "true")
os.environ.setdefault("MAAHAF_REDIS_URL", "redis://localhost:6399/15")  # unlikely to exist -> no-op

import pytest  # noqa: E402


@pytest.fixture
def gateway():
    from app.llm.gateway import Gateway, UsageMeter

    return Gateway(UsageMeter())
