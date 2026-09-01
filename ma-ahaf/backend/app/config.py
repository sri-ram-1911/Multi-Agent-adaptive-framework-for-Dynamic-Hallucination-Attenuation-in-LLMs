"""Central configuration (pydantic-settings). All env vars are prefixed ``MAAHAF_``."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseModel):
    """Model-agnostic gateway configuration: one model per *role*."""

    provider: Literal["openai", "local", "hf", "mock"] = "openai"
    local_base_url: str = "http://localhost:11434/v1"
    hf_model: str = "google/flan-t5-base"  # used when provider == "hf"

    generator_model: str = "gpt-4o-mini"
    verifier_model: str = "gpt-4o-mini"
    decomposer_model: str = "gpt-4o-mini"
    reviser_model: str = "gpt-4o-mini"
    judge_model: str = "gpt-4o"
    expander_model: str = "gpt-4o-mini"

    request_timeout_s: float = 60.0
    max_retries: int = 3
    # USD per 1M tokens, (input, output) — used for cost accounting only.
    price_table: dict[str, tuple[float, float]] = {
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
    }


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MAAHAF_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    env: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://maahaf:maahaf@localhost:5432/maahaf"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 720
    dev_api_key: str = "dev-key"

    allow_external_retrieval: bool = False
    pii_redaction: bool = True

    # ML / DL model ids (HuggingFace)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    nli_model: str = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
    zeroshot_model: str = "facebook/bart-large-mnli"
    artifacts_dir: str = "app/ml/artifacts"

    max_revision_loops: int = 2
    default_candidates: int = 2
    retrieval_k: int = 8
    rerank_k: int = 5

    otel_enabled: bool = True
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    service_name: str = "ma-ahaf-api"

    llm: LLMSettings = Field(default_factory=LLMSettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
