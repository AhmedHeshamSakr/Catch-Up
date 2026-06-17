from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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
    # Optional distinct/stronger model for the offline eval JUDGE. Defaults to
    # None → judge falls back to llm_model. Setting a DIFFERENT (ideally
    # stronger) model here reduces self-grading bias: when the judge and the
    # enricher share one model, the judge tends to ratify its own mistakes.
    judge_model: str | None = None
    # LLM-call resilience: per-attempt timeout, retry count, and backoff base.
    llm_timeout: float = 60.0
    llm_max_retries: int = 2
    llm_backoff_base: float = 0.5
    # Optional run-level wall-clock cap (seconds). None = no cap (default; the
    # whole digest run can take as long as it needs). When set, the tree
    # execution is wrapped in asyncio.wait_for so a stuck stage can't hang the
    # run forever; on timeout the run finalizes FAILED and the error re-raises.
    run_timeout: float | None = None
    # ADK session persistence. "database" (default) = persistent
    # DatabaseSessionService (SQLite via aiosqlite) so a run's session survives a
    # restart and the tree is portable to any persistent service. "memory" =
    # in-process InMemorySessionService (fast tests / ephemeral runs).
    session_backend: Literal["database", "memory"] = "database"
    # Session store URL. Empty => derive a local SQLite file next to sqlite_path:
    #   sqlite+aiosqlite:///<dir of sqlite_path>/sessions.db
    # Set explicitly to point at another backend later (e.g. postgresql+asyncpg://).
    session_db_url: str = ""
    # Deterministic generation for structured-output agents.
    llm_temperature: float = 0.0
    gnews_api_key: str = ""
    critic_enabled: bool = True
    critic_min_importance: Importance = Importance.HIGH
    critic_check_watchlisted: bool = True
    critic_action: Literal["flag", "downrank", "replace"] = "downrank"
    # Fail-closed: if the critic errors, protect (flag+redact) the items it was
    # meant to check rather than shipping them unguarded ("open").
    critic_fail_mode: Literal["open", "closed"] = "closed"
    # Bounded self-correction: when the critic flags an item UNFAITHFUL, give the
    # enricher up to this many chances to re-summarize with the critic's feedback
    # before falling back to flag/redact. 0 disables reflection (legacy path).
    critic_max_reflections: int = 1
    # API security. api_key=None leaves the API open (local/dev default).
    api_key: str | None = None
    # Token-bucket rate limit for POST /runs and POST /sources/resolve.
    rate_limit_burst: int = 30
    rate_limit_refill_per_sec: float = 1.0
    # CORS allowlist for the product API. Comma-separated in the ALLOW_ORIGINS
    # env var (e.g. "https://a.example,https://b.example"); defaults to the
    # local console origin.
    # NoDecode: keep pydantic-settings from JSON-decoding the env value so the
    # validator below can comma-split a plain "a,b,c" string.
    allow_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value


def load_sources(config_dir: str | Path) -> list[SourceConfig]:
    path = Path(config_dir) / "sources.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [SourceConfig(**raw) for raw in data.get("sources", [])]
