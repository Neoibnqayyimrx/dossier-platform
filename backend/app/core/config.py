from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central place every config value is read from. No secrets in code —
    everything here comes from the environment (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    app_version: str = "0.1.0"

    database_url: str = "postgresql+psycopg://dossier:dossier@localhost:5432/dossier"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "dossier-artifacts"

    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-5"
    llm_api_key: str | None = None

    # Embedding provider for the knowledge base (P03) — same provider-
    # abstraction rule as the LLM client above: backend and model name are
    # config-selected, never hard-coded in services/knowledge/*.
    embedding_provider: str = "voyage"
    embedding_model: str = "voyage-3-lite"
    embedding_api_key: str | None = None

    # WHY a default here (unlike llm_api_key): dev/test need a working secret
    # out of the box; production must override via the environment. Never
    # generated at import time (that would invalidate every token on restart).
    jwt_secret_key: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    """Cached so Settings is parsed from the environment once per process,
    not on every request that depends on it."""
    return Settings()
