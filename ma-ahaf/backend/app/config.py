"""Central configuration (pydantic-settings). All env vars are prefixed ``MAAHAF_``."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field
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

    # provider API keys — read the conventional un-prefixed names too
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MAAHAF_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )

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
    # when False, verification uses the NLI model only (skips the independent LLM
    # verifier + counterfactual probe) — much cheaper, useful for weak/local
    # generators or cost-sensitive tenants.
    verifier_llm_enabled: bool = True
    # entailment backend: "local" = DeBERTa-v3 NLI (CPU); "llm" = the gateway
    # verifier model scores claim<->evidence in one batched call; "auto" picks
    # "llm" when the LLM provider is openai/local (fast) else "local".
    nli_backend: Literal["auto", "local", "llm"] = "auto"

    @property
    def effective_nli_backend(self) -> str:
        if self.nli_backend != "auto":
            return self.nli_backend
        return "llm" if self.llm.provider in ("openai", "local") else "local"
    retrieval_k: int = 8
    rerank_k: int = 5

    otel_enabled: bool = True
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    service_name: str = "ma-ahaf-api"

    # request limits
    max_prompt_chars: int = 8000
    max_context_chars: int = 20000
    rate_limit_per_min: int = 60

    # CORS (comma-separated origins; "*" only honoured when env == dev)
    cors_origins: str = "http://localhost:5173,http://localhost:8000"

    llm: LLMSettings = Field(default_factory=LLMSettings)

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def cors_origin_list(self) -> list[str]:
        if self.env == "dev":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def validate_for_runtime(self) -> list[str]:
        """Return a list of fatal misconfigurations. Empty == safe to start."""
        problems: list[str] = []
        weak_secrets = {"change-me", "change-me-in-production", "CHANGE-ME-64-random-hex-chars",
                        "local-dev-only-not-for-production", ""}
        if self.is_prod:
            if self.jwt_secret in weak_secrets or len(self.jwt_secret) < 32:
                problems.append("MAAHAF_JWT_SECRET must be a strong (>=32 char) random value in prod")
            if self.dev_api_key and self.dev_api_key == "dev-key":
                problems.append("MAAHAF_DEV_API_KEY 'dev-key' must be unset/changed in prod")
            if self.llm.provider == "mock":
                problems.append("MAAHAF_LLM__PROVIDER=mock is not allowed in prod")
            if "localhost" in self.database_url:
                problems.append("MAAHAF_DATABASE_URL points at localhost in prod")
        if self.llm.provider == "openai" and not (self.openai_api_key or _env_openai_key()):
            problems.append("MAAHAF_LLM__PROVIDER=openai but OPENAI_API_KEY is not set")
        return problems


def _env_openai_key() -> bool:
    import os

    return bool(os.environ.get("OPENAI_API_KEY"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
