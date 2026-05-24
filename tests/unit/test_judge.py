"""Unit tests for app/pipeline/judge.py — fully offline, no live model calls."""
from __future__ import annotations

import json

from app.core.domain import Category, NewsItem, Sentiment, SourceType
from app.llm.schema import ItemEnrichment
from app.pipeline.eval_schema import (
    DimensionVerdict,
    EnrichmentVerdict,
    EnrichmentVerdicts,
)
from app.pipeline.judge import _judge_payload, build_judge_agent


def _make_news_item(item_id: str, title: str, excerpt: str = "") -> NewsItem:
    return NewsItem(
        id=item_id,
        source_id="test",
        source_type=SourceType.RSS,
        source_name="Test",
        url=f"https://test.local/{item_id}",
        title=title,
        excerpt=excerpt,
    )


def _make_enrichment(item_id: str) -> ItemEnrichment:
    return ItemEnrichment(
        id=item_id,
        category=Category.AI_TECH,
        importance_score=0.75,
        summary_en="OpenAI released GPT-5 with improved reasoning.",
        summary_ar="أطلقت OpenAI نموذج GPT-5 بقدرات استدلال محسّنة.",
        entities=[],
        sentiment=Sentiment.POSITIVE,
    )


def test_build_judge_agent_output_schema_and_name():
    agent = build_judge_agent("gemini-flash-latest")
    assert agent.name == "enrichment_judge"
    assert agent.output_schema is EnrichmentVerdicts


def test_judge_payload_structure():
    item = _make_news_item("item-1", "OpenAI releases model", "OpenAI announced a new model today.")
    enrichment = _make_enrichment("item-1")
    payload = _judge_payload([(item, enrichment)])

    records = json.loads(payload)
    assert len(records) == 1
    rec = records[0]
    assert rec["id"] == "item-1"
    assert rec["title"] == "OpenAI releases model"
    assert rec["excerpt"] == "OpenAI announced a new model today."
    assert "enrichment" in rec
    assert rec["enrichment"]["category"] == "ai_tech"
    assert rec["enrichment"]["importance_score"] == 0.75
    assert rec["enrichment"]["summary_en"] == "OpenAI released GPT-5 with improved reasoning."
    assert rec["enrichment"]["summary_ar"] == "أطلقت OpenAI نموذج GPT-5 بقدرات استدلال محسّنة."


def test_judge_payload_multiple_pairs():
    pairs = [
        (_make_news_item(f"id-{i}", f"Title {i}"), _make_enrichment(f"id-{i}"))
        for i in range(3)
    ]
    payload = _judge_payload(pairs)
    records = json.loads(payload)
    assert len(records) == 3
    assert [r["id"] for r in records] == ["id-0", "id-1", "id-2"]


def test_judge_payload_empty_excerpt():
    item = _make_news_item("no-excerpt", "Title with no excerpt")
    # excerpt is None on NewsItem; _judge_payload should coerce to ""
    enrichment = _make_enrichment("no-excerpt")
    payload = _judge_payload([(item, enrichment)])
    records = json.loads(payload)
    assert records[0]["excerpt"] == ""


def test_enrichment_verdicts_round_trip():
    """EnrichmentVerdicts must serialise and deserialise correctly (ADK output_schema pattern)."""
    ev = EnrichmentVerdicts(
        verdicts=[
            EnrichmentVerdict(
                item_id="x1",
                faithfulness=DimensionVerdict(passed=True, score=0.95, reason="All facts match."),
                category_accuracy=DimensionVerdict(passed=True, score=1.0, reason="Correct category."),
                importance_calibration=DimensionVerdict(passed=True, score=0.8, reason="Reasonable score."),
                ar_translation_quality=DimensionVerdict(passed=True, score=0.9, reason="Fluent MSA."),
            )
        ]
    )
    json_str = ev.model_dump_json()
    restored = EnrichmentVerdicts.model_validate_json(json_str)
    assert len(restored.verdicts) == 1
    assert restored.verdicts[0].item_id == "x1"
    assert restored.verdicts[0].faithfulness.passed is True
    assert restored.verdicts[0].faithfulness.score == 0.95
    assert restored.verdicts[0].category_accuracy.score == 1.0
