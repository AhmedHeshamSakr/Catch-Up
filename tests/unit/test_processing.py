from app.core.config import Settings
from app.core.domain import Category, Sentiment
from app.pipeline.schema import ItemEnrichment, ProcessingResult


def test_settings_has_intelligence_defaults():
    s = Settings()
    assert 0.0 <= s.importance_threshold <= 1.0
    assert s.llm_batch_size >= 1
    assert s.llm_model == "gemini-flash-latest"


def test_item_enrichment_validates_score_range():
    e = ItemEnrichment(
        id="abc", category=Category.AI_TECH, importance_score=0.9,
        summary_en="en", summary_ar="ar", entities=[], sentiment=Sentiment.NEUTRAL,
    )
    assert e.importance_score == 0.9
    result = ProcessingResult(items=[e])
    assert result.items[0].id == "abc"
