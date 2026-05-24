from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.domain import Category, Entity, Sentiment


class ItemEnrichment(BaseModel):
    id: str = Field(description="The id of the news item this enrichment is for.")
    category: Category
    importance_score: float = Field(ge=0.0, le=1.0, description="0=trivial, 1=critical.")
    summary_en: str = Field(description="Concise 1-2 sentence English summary.")
    summary_ar: str = Field(description="Concise 1-2 sentence Arabic summary.")
    entities: list[Entity] = Field(default_factory=list)
    sentiment: Sentiment


class ProcessingResult(BaseModel):
    items: list[ItemEnrichment]


class DigestNarrative(BaseModel):
    narrative: str = Field(description="A short 'what matters most' editorial, grouped by theme.")
