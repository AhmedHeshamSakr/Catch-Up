from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class SourceType(StrEnum):
    RSS = "rss"
    SCRAPE = "scrape"
    API = "api"
    SEARCH = "search"
    YOUTUBE = "youtube"


class Category(StrEnum):
    AI_TECH = "ai_tech"
    BUSINESS_FINANCE = "business_finance"
    WORLD_GEOPOLITICS = "world_geopolitics"
    GULF_MENA = "gulf_mena"


class Importance(StrEnum):
    # Importance bands (must stay aligned with app/prompts/processing.md and the
    # importance_score field in app/llm/schema.py):
    #   0.0-0.2 routine/incremental (minor product update, local notice)
    #   0.3-0.5 notable sector news
    #   0.6-0.8 major (large M&A, national policy, significant outage)
    #   0.9-1.0 globally critical (war, major-economy crisis, landmark regulation)
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class EntityType(StrEnum):
    """Allowed kinds of named entity extracted from an item.

    Mirrored in app/prompts/processing.md so the model's output and this code
    agree on the allowed values.
    """

    COMPANY = "company"
    PERSON = "person"
    ORG = "org"
    PLACE = "place"
    PRODUCT = "product"


# Common LLM/stored synonyms mapped onto the canonical EntityType members. Used
# by Entity's validator so a soft, forgiving mapping keeps previously stored
# JSON (e.g. "organization") deserializable instead of a hard enum that would
# reject it. Anything unrecognized falls back to ORG.
_ENTITY_TYPE_SYNONYMS: dict[str, EntityType] = {
    "organization": EntityType.ORG,
    "organisation": EntityType.ORG,
    "org": EntityType.ORG,
    "company": EntityType.COMPANY,
    "corporation": EntityType.COMPANY,
    "corp": EntityType.COMPANY,
    "business": EntityType.COMPANY,
    "firm": EntityType.COMPANY,
    "person": EntityType.PERSON,
    "people": EntityType.PERSON,
    "individual": EntityType.PERSON,
    "place": EntityType.PLACE,
    "location": EntityType.PLACE,
    "country": EntityType.PLACE,
    "city": EntityType.PLACE,
    "region": EntityType.PLACE,
    "product": EntityType.PRODUCT,
    "service": EntityType.PRODUCT,
}


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


def make_item_id(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()[:16]


class Entity(BaseModel):
    name: str
    type: EntityType = EntityType.ORG

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, value: object) -> object:
        """Lowercase + map common synonyms onto an EntityType member.

        Soft governance: unknown/legacy strings (e.g. "organization") are mapped
        rather than rejected, so previously stored JSON still deserializes. Truly
        unrecognized values fall back to ORG.
        """
        if isinstance(value, EntityType):
            return value
        if isinstance(value, str):
            key = value.strip().lower()
            return _ENTITY_TYPE_SYNONYMS.get(key, EntityType.ORG)
        return value


class RawItem(BaseModel):
    source_id: str
    source_type: SourceType
    source_name: str
    url: str
    title: str
    excerpt: str | None = None
    published_at: datetime | None = None
    category_hint: Category | None = None
    # Optional thumbnail; stored only, never server-side fetched (browser loads
    # it directly). Collectors validate it as http(s) before setting it.
    image_url: str | None = None


class NewsItem(BaseModel):
    id: str
    source_id: str
    source_type: SourceType
    source_name: str
    url: str
    title: str
    excerpt: str | None = None
    image_url: str | None = None
    published_at: datetime | None = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    category: Category | None = None
    summary_en: str | None = None
    summary_ar: str | None = None
    importance: Importance | None = None
    importance_score: float | None = None
    entities: list[Entity] = Field(default_factory=list)
    sentiment: Sentiment | None = None
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
            image_url=raw.image_url,
            published_at=raw.published_at,
            category=raw.category_hint,
            digest_run_id=run_id,
        )


class DigestRun(BaseModel):
    run_id: str
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
    flagged: int = 0
    critic_verdicts: list[dict] = Field(default_factory=list)
