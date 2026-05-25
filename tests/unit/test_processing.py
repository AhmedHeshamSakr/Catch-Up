from app.core.config import Settings
from app.core.domain import (
    Category,
    Entity,
    Importance,
    NewsItem,
    RawItem,
    Sentiment,
    SourceType,
)
from app.llm.schema import ItemEnrichment, ProcessingResult
from app.pipeline import processing
from app.services.watchlist import Watchlist


def test_settings_has_intelligence_defaults():
    # _env_file=None isolates the assertion from a developer's local app/.env
    # (e.g. an LLM_MODEL override) so it verifies the source-code defaults.
    s = Settings(_env_file=None)
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


def test_process_items_isolates_failed_batch():
    # 3 items, batch_size=1 -> 3 batches. The 2nd batch's enrich raises.
    items = [
        _news("https://a.com/1", "first"),
        _news("https://a.com/2", "second"),
        _news("https://a.com/3", "third"),
    ]
    seen: list[str] = []

    def flaky_enrich(batch):
        title = batch[0].title
        seen.append(title)
        if title == "second":
            raise RuntimeError("batch blew up")
        return ProcessingResult(items=[
            ItemEnrichment(
                id=it.id, category=Category.AI_TECH, importance_score=0.8,
                summary_en="en", summary_ar="ar", entities=[],
                sentiment=Sentiment.NEUTRAL,
            ) for it in batch
        ])

    errors: list[dict] = []
    out = processing.process_items(
        items, flaky_enrich, Watchlist(), threshold=0.33, batch_size=1, errors=errors
    )

    # All 3 batches were attempted (failure did not abort the stage).
    assert seen == ["first", "second", "third"]
    # Batches 1 and 3 enriched; batch 2's item fell through to raw.
    assert items[0].status == "processed"
    assert items[1].status == "raw"
    assert items[2].status == "processed"
    # The error was recorded (in the passed sink and in the return value).
    assert len(errors) == 1
    assert errors[0]["batch"] == 1
    assert "batch blew up" in errors[0]["error"]
    assert out == errors
