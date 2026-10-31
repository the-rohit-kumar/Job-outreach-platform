"""Application settings. Secrets come from .env / environment only."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
_ROOT_ENV = REPO_ROOT / ".env"


class Settings(BaseSettings):
    app_name: str = "OutreachHub"
    app_secret: str = "dev-secret-change-me"
    environment: str = "development"

    database_url: str = "sqlite:///./data/outreach.db"

    app_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    session_cookie: str = "outreach_session"
    session_max_age: int = 60 * 60 * 24 * 30
    min_password_length: int = 8

    # File cache for feeds/robots + fixtures. Relative paths are from the backend dir.
    cache_dir: str = "data/cache"

    # LLM (wired up in step 4)
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    llm_fast_model: str = "claude-haiku-4-5-20251001"
    llm_strong_model: str = "claude-sonnet-4-5-20250929"
    llm_daily_spend_cap_usd: float = 5.0

    # Search API used by the search-dork collector (step 8).
    search_provider: str = "brave"
    brave_api_key: str = ""
    serpapi_key: str = ""

    # Reddit official API (step 8)
    reddit_client_id: str = ""
    reddit_client_secret: str = ""

    # Gmail OAuth - the app never sees your Google password.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8000/api/gmail/oauth/callback"

    model_config = SettingsConfigDict(
        env_file=(".env", str(_ROOT_ENV)),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def load_sources_config() -> dict:
    """Collector overrides from config/sources.yaml (YAML wins over code defaults)."""
    import yaml

    path = REPO_ROOT / "config" / "sources.yaml"
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return dict(data.get("collectors") or {})


sources_config: dict = load_sources_config()
