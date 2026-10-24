"""Runtime settings, loaded from environment (see .env.example). No secrets have defaults."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCHOOLSYNC_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    max_upload_bytes: int = 10 * 1024 * 1024
    max_pages: int = 40
    cors_origins: list[str] = ["http://localhost:3000"]
    # When set, every /api request must carry a matching X-API-Key header (health is exempt).
    api_key: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/oauth/google/callback"
    token_encryption_key: str | None = None  # Fernet key; required to store provider tokens
    frontend_url: str = "http://localhost:3000"  # where the OAuth callback sends the browser
    sync_enabled: bool = True  # kill switch: false disables every sync/rollback endpoint


@lru_cache
def get_settings() -> Settings:
    return Settings()
