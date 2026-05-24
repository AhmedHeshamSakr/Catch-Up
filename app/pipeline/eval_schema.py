from __future__ import annotations

from pydantic import BaseModel, Field


class DimensionVerdict(BaseModel):
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    reason: str


class EnrichmentVerdict(BaseModel):
    item_id: str
    faithfulness: DimensionVerdict
    category_accuracy: DimensionVerdict
    importance_calibration: DimensionVerdict
    ar_translation_quality: DimensionVerdict


class EnrichmentVerdicts(BaseModel):  # ADK output_schema needs a model, not a bare list
    verdicts: list[EnrichmentVerdict]


class FaithfulnessVerdict(BaseModel):  # used in Phase B; define now for reuse
    item_id: str
    faithful: bool
    issues: list[str] = Field(default_factory=list)
    suggested_summary_en: str | None = None


class FaithfulnessVerdicts(BaseModel):
    verdicts: list[FaithfulnessVerdict]
