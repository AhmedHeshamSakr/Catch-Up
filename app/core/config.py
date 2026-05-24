from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.domain import Category, Importance, SourceType

REPO_ROOT = Path(__file__).resolve().parents[2]


class SourceConfig(BaseModel):
    id: str
    type: SourceType
    name: str
    url: str | None = None
    query: str | None = None
    category_hint: Category | None = None
    selector: str | None = None   # CSS selector for scrape sources
    lang: str | None = None       # e.g. "en", "ar" (api sources)
    country: str | None = None    # e.g. "qa", "us" (api sources)
    channel_id: str | None = None  # explicit YouTube channel id (UC…)
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def _reject_dangerous_scheme(cls, value: str | None) -> str | None:
        # url is optional (api/query sources omit it). When present it must be
        # http(s); reject file:/javascript:/etc. to prevent injection/SSRF.
        if value is None:
            return value
        scheme = urlparse(value).scheme
        if scheme not in ("http", "https"):
            raise ValueError(f"url scheme not allowed: {scheme!r}")
        return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("app/.env", ".env"), extra="ignore")

    google_api_key: str = ""
    storage_backend: str = "sqlite"
    sqlite_path: str = str(REPO_ROOT / "data" / "catchup.db")
    config_dir: str = str(REPO_ROOT / "config")
    output_dir: str = str(REPO_ROOT / "output")
    importance_threshold: float = 0.33
    llm_batch_size: int = 8
    llm_model: str = "gemini-flash-latest"
    gnews_api_key: str = ""
    youtube_whisper_enabled: bool = False
    whisper_model: str = "base"
    critic_enabled: bool = True
    critic_min_importance: Importance = Importance.HIGH
    critic_check_watchlisted: bool = True
    critic_action: Literal["flag", "downrank", "replace"] = "downrank"
    # Fail-closed: if the critic errors, protect (flag+redact) the items it was
    # meant to check rather than shipping them unguarded ("open").
    critic_fail_mode: Literal["open", "closed"] = "closed"
    # API security. api_key=None leaves the API open (local/dev default).
    api_key: str | None = None
    # Token-bucket rate limit for POST /runs and POST /sources/resolve.
    rate_limit_burst: int = 30
    rate_limit_refill_per_sec: float = 1.0


def load_sources(config_dir: str | Path) -> list[SourceConfig]:
    path = Path(config_dir) / "sources.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [SourceConfig(**raw) for raw in data.get("sources", [])]
