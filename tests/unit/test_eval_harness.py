"""Unit tests for scripts/eval_enrichment.py — fully offline (fake enrich + fake judge)."""
from __future__ import annotations

from pathlib import Path

from app.core.domain import Category, NewsItem, Sentiment
from app.llm.schema import ItemEnrichment, ProcessingResult
from app.pipeline.eval_schema import DimensionVerdict, EnrichmentVerdict

_REFERENCE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "eval"
    / "fixtures"
    / "enrichment_reference.json"
)


def _dim(passed: bool, score: float) -> DimensionVerdict:
    return DimensionVerdict(passed=passed, score=score, reason="synthetic")


def _verdict_from_expectations(item_id: str, expectations: dict) -> EnrichmentVerdict:
    """Create a synthetic verdict where each dim score is 1.0 if expected=True, 0.0 if False."""
    return EnrichmentVerdict(
        item_id=item_id,
        faithfulness=_dim(expectations["faithfulness"], 1.0 if expectations["faithfulness"] else 0.0),
        category_accuracy=_dim(expectations["category_accuracy"], 1.0 if expectations["category_accuracy"] else 0.0),
        importance_calibration=_dim(expectations["importance_calibration"], 1.0 if expectations["importance_calibration"] else 0.0),
        ar_translation_quality=_dim(expectations["ar_translation_quality"], 1.0 if expectations["ar_translation_quality"] else 0.0),
    )


def test_run_eval_with_fake_enrich_and_fake_judge():
    """run_eval returns a valid EvalReport when given synthetic enrich and judge."""

    from scripts.eval_enrichment import load_reference, run_eval

    reference = load_reference(_REFERENCE_PATH)

    expectations_by_id = {case["item"]["id"]: case["expectations"] for case in reference}

    def fake_enrich(items: list[NewsItem]) -> ProcessingResult:
        """Return gold enrichments for all items."""
        import json as _json
        data = _json.loads(_REFERENCE_PATH.read_text(encoding="utf-8"))
        gold_by_id = {case["gold"]["id"]: case["gold"] for case in data}
        result_items = []
        for item in items:
            gold = gold_by_id.get(item.id)
            if gold:
                result_items.append(
                    ItemEnrichment(
                        id=gold["id"],
                        category=Category(gold["category"]),
                        importance_score=gold["importance_score"],
                        summary_en=gold["summary_en"],
                        summary_ar=gold["summary_ar"],
                        entities=gold.get("entities", []),
                        sentiment=Sentiment(gold["sentiment"]),
                    )
                )
        return ProcessingResult(items=result_items)

    def fake_judge(pairs):
        return [
            _verdict_from_expectations(item.id, expectations_by_id[item.id])
            for item, _ in pairs
            if item.id in expectations_by_id
        ]

    report = run_eval(enrich=fake_enrich, judge=fake_judge, reference=reference)

    # Basic structural assertions
    assert report.n == len(reference)
    assert isinstance(report.passed, bool)
    assert isinstance(report.failures, list)
    assert set(report.dimension_pass_rate.keys()) == {
        "faithfulness", "category_accuracy", "importance_calibration", "ar_translation_quality"
    }
    assert set(report.dimension_mean_score.keys()) == {
        "faithfulness", "category_accuracy", "importance_calibration", "ar_translation_quality"
    }


def test_run_eval_all_perfect_verdicts_passes():
    """When fake judge returns all-perfect verdicts, report should pass."""
    from scripts.eval_enrichment import load_reference, run_eval

    reference = load_reference(_REFERENCE_PATH)

    def fake_enrich(items):
        return ProcessingResult(items=[
            ItemEnrichment(
                id=item.id,
                category=Category.AI_TECH,
                importance_score=0.5,
                summary_en="Test summary.",
                summary_ar="ملخص اختباري.",
                entities=[],
                sentiment=Sentiment.NEUTRAL,
            )
            for item in items
        ])

    def fake_judge_perfect(pairs):
        return [
            EnrichmentVerdict(
                item_id=item.id,
                faithfulness=_dim(True, 1.0),
                category_accuracy=_dim(True, 1.0),
                importance_calibration=_dim(True, 1.0),
                ar_translation_quality=_dim(True, 1.0),
            )
            for item, _ in pairs
        ]

    report = run_eval(enrich=fake_enrich, judge=fake_judge_perfect, reference=reference)
    assert report.passed is True
    assert report.failures == []
    for score in report.dimension_mean_score.values():
        assert score == 1.0


def test_run_eval_all_zero_verdicts_fails():
    """When all verdicts score 0.0, all dimensions fail."""
    from scripts.eval_enrichment import load_reference, run_eval

    reference = load_reference(_REFERENCE_PATH)

    def fake_enrich(items):
        return ProcessingResult(items=[
            ItemEnrichment(
                id=item.id,
                category=Category.AI_TECH,
                importance_score=0.5,
                summary_en="en",
                summary_ar="ar",
                entities=[],
                sentiment=Sentiment.NEUTRAL,
            )
            for item in items
        ])

    def fake_judge_zero(pairs):
        return [
            EnrichmentVerdict(
                item_id=item.id,
                faithfulness=_dim(False, 0.0),
                category_accuracy=_dim(False, 0.0),
                importance_calibration=_dim(False, 0.0),
                ar_translation_quality=_dim(False, 0.0),
            )
            for item, _ in pairs
        ]

    report = run_eval(enrich=fake_enrich, judge=fake_judge_zero, reference=reference)
    assert report.passed is False
    assert set(report.failures) == {
        "faithfulness", "category_accuracy", "importance_calibration", "ar_translation_quality"
    }
    for score in report.dimension_mean_score.values():
        assert score == 0.0


def test_run_eval_dimension_aggregation_matches_expectation():
    """With known synthetic verdicts, verify the exact dimension mean_score values."""
    from scripts.eval_enrichment import load_reference, run_eval

    # Use only two reference cases for precise arithmetic
    reference = load_reference(_REFERENCE_PATH)[:2]

    def fake_enrich(items):
        return ProcessingResult(items=[
            ItemEnrichment(
                id=item.id,
                category=Category.AI_TECH,
                importance_score=0.5,
                summary_en="en",
                summary_ar="ar",
                entities=[],
                sentiment=Sentiment.NEUTRAL,
            )
            for item in items
        ])

    # Verdict 1: faith=0.8, Verdict 2: faith=0.6 → mean = 0.7
    scores = [0.8, 0.6]

    def fake_judge_fixed(pairs):
        return [
            EnrichmentVerdict(
                item_id=item.id,
                faithfulness=_dim(True, scores[i]),
                category_accuracy=_dim(True, 1.0),
                importance_calibration=_dim(True, 1.0),
                ar_translation_quality=_dim(True, 1.0),
            )
            for i, (item, _) in enumerate(pairs)
        ]

    report = run_eval(enrich=fake_enrich, judge=fake_judge_fixed, reference=reference)
    assert abs(report.dimension_mean_score["faithfulness"] - 0.7) < 1e-9
    assert report.dimension_mean_score["category_accuracy"] == 1.0
    # faithfulness 0.7 < threshold 0.9 → should fail
    assert "faithfulness" in report.failures


def test_load_reference_returns_list():
    from scripts.eval_enrichment import load_reference
    data = load_reference(_REFERENCE_PATH)
    assert isinstance(data, list)
    assert len(data) > 0
