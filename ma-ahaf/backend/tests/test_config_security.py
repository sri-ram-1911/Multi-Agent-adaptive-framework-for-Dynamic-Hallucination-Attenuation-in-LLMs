from __future__ import annotations

from app.config import Settings


def test_prod_rejects_weak_jwt_secret():
    s = Settings(env="prod", jwt_secret="change-me", database_url="postgresql://h/db")
    problems = s.validate_for_runtime()
    assert any("JWT_SECRET" in p for p in problems)


def test_prod_rejects_dev_api_key_and_mock_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    s = Settings(env="prod", jwt_secret="x" * 40, dev_api_key="dev-key",
                 database_url="postgresql://h/db")
    problems = s.validate_for_runtime()
    assert any("DEV_API_KEY" in p for p in problems)


def test_openai_provider_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    s = Settings(env="dev", openai_api_key=None)
    s.llm.provider = "openai"
    assert any("OPENAI_API_KEY" in p for p in s.validate_for_runtime())


def test_clean_prod_config_passes(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real")
    s = Settings(
        env="prod", jwt_secret="a" * 48, dev_api_key="",
        database_url="postgresql+psycopg://maahaf:pw@db.internal:5432/maahaf",
    )
    s.llm.provider = "openai"
    assert s.validate_for_runtime() == []


def test_cors_is_locked_down_outside_dev():
    assert Settings(env="prod").cors_origin_list != ["*"]
    assert Settings(env="dev").cors_origin_list == ["*"]


def test_verifier_llm_toggle_default_on():
    assert Settings().verifier_llm_enabled is True
    assert Settings(verifier_llm_enabled=False).verifier_llm_enabled is False


def test_openai_key_read_from_unprefixed_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-plain-env")
    s = Settings()
    assert s.openai_api_key == "sk-from-plain-env"
    s.llm.provider = "openai"
    assert s.validate_for_runtime() == []
