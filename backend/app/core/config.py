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

    # Object storage for rendered section documents (P04) — same provider-
    # abstraction rule as embedding_provider above: "memory" runs fully
    # offline for dev/test (no MinIO needed), "s3" points at the real
    # MinIO/S3-compatible endpoint configured above.
    storage_provider: str = "memory"

    # "gemini" (real, needs LLM_API_KEY -- Google's free tier is generous
    # enough for this project's volume) or "fake" (deterministic offline
    # stub for dev/test, no network/key needed, same rule as
    # embedding_provider below).
    llm_provider: str = "gemini"
    llm_model: str = "gemini-2.5-flash"
    llm_api_key: str | None = None

    # Embedding provider for the knowledge base (P03) — same provider-
    # abstraction rule as the LLM client above: backend and model name are
    # config-selected, never hard-coded in services/knowledge/*.
    embedding_provider: str = "voyage"
    embedding_model: str = "voyage-3-lite"
    embedding_api_key: str | None = None

    # Browser origins allowed to call this API (P11 -- the frontend is a
    # separate origin, so without this every request from it fails CORS
    # preflight). Comma-separated in the environment
    # (CORS_ALLOW_ORIGINS=http://localhost:3000,https://app.example.com).
    #
    # WHY an explicit allowlist rather than "*": this API is
    # bearer-token authenticated, and a wildcard origin is exactly the
    # configuration that lets any site a logged-in user visits call it
    # with their credentials. Dev convenience is not worth that default.
    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_allow_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    # External eCTD validator (P10) -- "null" (default) means no real
    # agency-recognized validator (e.g. an eValidator-class tool) is wired
    # up in this environment; the report says so explicitly rather than
    # silently omitting that layer. Swap in a real adapter the same way
    # llm_provider/embedding_provider get swapped: change this one value.
    ectd_external_validator_provider: str = "null"

    # Knowledge base (P03): chunk size and default search breadth are config
    # knobs, not magic numbers buried in the chunker/retriever, per AGENTS.md
    # §5 ("config over hard-coding").
    kb_chunk_max_chars: int = 1200
    kb_search_default_k: int = 5

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
