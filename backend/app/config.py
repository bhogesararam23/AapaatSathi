"""Application configuration.

Every value can be overridden by an environment variable or a `.env` file
next to the backend entrypoint. Defaults are chosen so that `uvicorn app.main:app`
works with **zero** configuration on a laptop (SQLite + console notifications).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_ROOT / "data"
MEDIA_DIR = DATA_DIR / "uploads"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- metadata
    app_name: str = "AapaatSathi API"
    app_tagline: str = "Ward-level landslide & flood early warning for hill districts"
    version: str = "1.0.0"
    environment: str = "development"
    docs_enabled: bool = True

    # ------------------------------------------------------------------- paths
    database_url: str = f"sqlite+aiosqlite:///{(DATA_DIR / 'aapaatsathi.db').as_posix()}"
    media_dir: str = str(MEDIA_DIR)

    # -------------------------------------------------------------------- auth
    secret_key: str = "dev-only-change-me-aapaatsathi-2026-please-set-SECRET_KEY"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 12
    refresh_token_minutes: int = 60 * 24 * 14

    # -------------------------------------------------------------------- CORS
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173"
    )

    # ---------------------------------------------------------- notifications
    # console | twilio | msg91  (console keeps the MVP runnable without keys)
    sms_provider: str = "console"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    msg91_auth_key: str = ""
    msg91_sender_id: str = "AAPATH"

    # ---------------------------------------------------------- external feeds
    # When true the ingest service polls Open-Meteo for live rainfall. When
    # false (default) a deterministic monsoon simulator drives the engine so
    # demos are reproducible and offline-safe.
    use_live_weather: bool = False
    open_meteo_url: str = "https://api.open-meteo.com/v1/forecast"
    ingest_interval_seconds: int = 900

    # ------------------------------------------------------------ risk engine
    # Crowd corroboration cannot lift a score by more than this multiplier.
    crowd_uplift_cap: float = 1.25
    alert_eval_interval_seconds: int = 300
    dedupe_window_minutes: int = 90

    # ------------------------------------------------------------------- demo
    seed_on_startup: bool = True
    reset_database: bool = False
    demo_api_key: str = "aapaatsathi-demo"

    @field_validator("environment", "sms_provider")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def secret(self) -> Path:
        return BACKEND_ROOT / ".env"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.media_dir).mkdir(parents=True, exist_ok=True)
    if settings.is_sqlite:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
