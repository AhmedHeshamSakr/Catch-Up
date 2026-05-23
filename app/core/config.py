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
    enabled: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_api_key: str = ""
    storage_backend: str = "sqlite"
    sqlite_path: str = str(REPO_ROOT / "data" / "catchup.db")
    config_dir: str = str(REPO_ROOT / "config")
    output_dir: str = str(REPO_ROOT / "output")


def load_sources(config_dir: str | Path) -> list[SourceConfig]:
    path = Path(config_dir) / "sources.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [SourceConfig(**raw) for raw in data.get("sources", [])]
