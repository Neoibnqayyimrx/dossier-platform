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


@lru_cache
def get_settings() -> Settings:
    """Cached so Settings is parsed from the environment once per process,
    not on every request that depends on it."""
    return Settings()
