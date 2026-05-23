from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

DEFAULT_ORG = "default"
DEFAULT_USER = "default"


class SourceType(StrEnum):
    RSS = "rss"
    SCRAPE = "scrape"
    API = "api"
    SEARCH = "search"


class Category(StrEnum):
    AI_TECH = "ai_tech"
    BUSINESS_FINANCE = "business_finance"
    WORLD_GEOPOLITICS = "world_geopolitics"
    GULF_MENA = "gulf_mena"


class Importance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


def make_item_id(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()[:16]


class Entity(BaseModel):
    name: str
    type: str = "org"


class RawItem(BaseModel):
    source_id: str
    source_type: SourceType
    source_name: str
    url: str
    title: str
    excerpt: str | None = None
    published_at: datetime | None = None
    category_hint: Category | None = None


class NewsItem(BaseModel):
    id: str
    org_id: str = DEFAULT_ORG
    user_id: str = DEFAULT_USER
    source_id: str
    source_type: SourceType
    source_name: str
    url: str
    title: str
    excerpt: str | None = None
    published_at: datetime | None = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    category: Category | None = None
    summary_en: str | None = None
    summary_ar: str | None = None
    importance: Importance | None = None
    importance_score: float | None = None
    entities: list[Entity] = Field(default_factory=list)
    sentiment: Sentiment | None = None
    language: str | None = None
    status: str = "raw"
    digest_run_id: str | None = None

    @classmethod
    def from_raw(cls, raw: RawItem, run_id: str | None = None) -> NewsItem:
        return cls(
            id=make_item_id(raw.url),
            source_id=raw.source_id,
            source_type=raw.source_type,
            source_name=raw.source_name,
            url=raw.url,
            title=raw.title,
            excerpt=raw.excerpt,
            published_at=raw.published_at,
            category=raw.category_hint,
            digest_run_id=run_id,
        )


class DigestRun(BaseModel):
    run_id: str
    org_id: str = DEFAULT_ORG
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    status: RunStatus = RunStatus.RUNNING
    collected: int = 0
    new: int = 0
    processed: int = 0
    high_importance: int = 0
    outputs: dict[str, str] = Field(default_factory=dict)
    source_errors: list[dict] = Field(default_factory=list)
    narrative: str | None = None
