"""Server settings from environment variables (MASTER_GUIDE §7.4)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """API configuration. The private data path comes *only* from here, never from requests."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gravanom_private_data_dir: str | None = None
    gravanom_artifacts_dir: Path = REPO_ROOT / "artifacts"
    gravanom_public_mode: bool = False
    api_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: str = "INFO"
    max_body_bytes: int = Field(default=1_000_000, ge=1024)
    job_workers: int = Field(default=2, ge=1, le=8)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def api_artifacts(self) -> Path:
        return self.gravanom_artifacts_dir / "api"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
