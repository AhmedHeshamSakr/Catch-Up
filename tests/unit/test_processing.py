from app.core.config import Settings
from app.core.domain import Category, Entity, Importance, NewsItem, RawItem, Sentiment, SourceType
from app.pipeline import processing
from app.pipeline.schema import ItemEnrichment, ProcessingResult
from app.services.watchlist import Watchlist


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


def _news(url, title):
    raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="S",
                  url=url, title=title)
    return NewsItem.from_raw(raw, run_id="r1")


def test_score_to_importance():
    assert processing.score_to_importance(0.9) == Importance.HIGH
    assert processing.score_to_importance(0.5) == Importance.MEDIUM
    assert processing.score_to_importance(0.1) == Importance.LOW


def test_process_items_merges_enrichment_applies_boost_and_threshold():
    items = [_news("https://a.com/1", "OpenAI launches"), _news("https://a.com/2", "minor note")]

    def fake_enrich(batch):
        out = []
        for it in batch:
            score = 0.7 if "OpenAI" in it.title else 0.1
            out.append(ItemEnrichment(
                id=it.id, category=Category.AI_TECH, importance_score=score,
                summary_en="en", summary_ar="ar",
                entities=[Entity(name="OpenAI", type="org")] if score > 0.5 else [],
                sentiment=Sentiment.NEUTRAL))
        return ProcessingResult(items=out)

    wl = Watchlist(entities=["OpenAI"], keywords=[])
    processing.process_items(items, fake_enrich, wl, threshold=0.33, batch_size=8)

    high, low = items[0], items[1]
    assert high.summary_en == "en" and high.summary_ar == "ar"
    assert high.importance_score == 0.95  # 0.7 + 0.25 boost
    assert high.importance == Importance.HIGH
    assert high.status == "processed"
    assert low.status == "filtered"        # 0.1 < threshold
    assert low.importance == Importance.LOW


def test_process_items_marks_raw_when_enrichment_missing():
    items = [_news("https://a.com/1", "t")]
    processing.process_items(items, lambda b: ProcessingResult(items=[]), Watchlist(), 0.33, 8)
    assert items[0].status == "raw"
