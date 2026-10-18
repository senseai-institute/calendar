"""Runtime configuration, read from environment variables / `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{REPO_ROOT / 'data' / 'calendar.db'}"
    skycal_ephe_path: str = str(REPO_ROOT / "data" / "ephe")
    public_base_url: str = "http://localhost:8000"
    app_timezone: str = "America/New_York"
    scheduler_enabled: bool = True
    default_user_email: str = "me@example.com"
    # How far ahead the nightly job computes, and how far back it refreshes.
    recompute_days_ahead: int = 90
    recompute_days_behind: int = 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
