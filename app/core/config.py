from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.domain import Category, SourceType

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


def load_sources(config_dir: str | Path) -> list[SourceConfig]:
    path = Path(config_dir) / "sources.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [SourceConfig(**raw) for raw in data.get("sources", [])]
