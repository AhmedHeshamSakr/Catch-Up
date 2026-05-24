"""Unit tests for tests/eval/fixtures/enrichment_reference.json — fully offline."""
from __future__ import annotations

import json
from pathlib import Path

from app.llm.schema import ItemEnrichment

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "eval"
    / "fixtures"
    / "enrichment_reference.json"
)

_DIMENSIONS = ["faithfulness", "category_accuracy", "importance_calibration", "ar_translation_quality"]


def _load() -> list[dict]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


_CATEGORIES = ["ai_tech", "business_finance", "world_geopolitics", "gulf_mena"]


def test_fixture_file_parses():
    data = _load()
    assert isinstance(data, list)
    assert len(data) >= 30, "Expected at least 30 reference cases (grown from the original 10)"


def test_all_four_categories_represented_and_balanced():
    """Every category must appear, and none should dominate (balance check)."""
    data = _load()
    from collections import Counter
    counts = Counter(case["gold"]["category"] for case in data)
    for cat in _CATEGORIES:
        assert counts.get(cat, 0) >= 4, f"category '{cat}' under-represented: {counts.get(cat, 0)}"


def test_multiple_ar_translation_negatives():
    """Need several distinct Arabic-quality failure modes (bad MSA, dropped/added claim, dialect)."""
    data = _load()
    ar_negatives = [c for c in data if not c["expectations"]["ar_translation_quality"]]
    assert len(ar_negatives) >= 3, "Need >=3 Arabic-quality negative cases"


def test_multiple_faithfulness_negatives_including_injection():
    """Several faithfulness failures (hallucination + multiple injection variants)."""
    data = _load()
    faith_negatives = [c for c in data if not c["expectations"]["faithfulness"]]
    assert len(faith_negatives) >= 4, "Need >=4 faithfulness negative cases"
    # At least two prompt-injection variants (heuristic: injection phrasing in title/excerpt)
    inj_markers = ("ignore", "system override", "system:", "system prompt", "admin mode")
    injections = [
        c for c in faith_negatives
        if any(m in (c["item"]["title"] + " " + c["item"]["excerpt"]).lower() for m in inj_markers)
    ]
    assert len(injections) >= 2, "Need >=2 prompt-injection variants among faithfulness negatives"


def test_importance_miscalibration_both_directions():
    """Need both over- and under-rated importance cases among the negatives."""
    data = _load()
    imp_negatives = [c for c in data if not c["expectations"]["importance_calibration"]]
    overrated = [c for c in imp_negatives if c["gold"]["importance_score"] >= 0.8]
    underrated = [c for c in imp_negatives if c["gold"]["importance_score"] <= 0.2]
    assert overrated, "Need an over-rated importance negative (trivial item scored high)"
    assert underrated, "Need an under-rated importance negative (major item scored low)"


def test_empty_excerpt_case_present():
    data = _load()
    assert any(case["item"]["excerpt"] == "" for case in data), "Need at least one empty-excerpt edge case"


def test_each_case_has_required_keys():
    data = _load()
    for i, case in enumerate(data):
        assert "item" in case, f"case {i} missing 'item'"
        assert "gold" in case, f"case {i} missing 'gold'"
        assert "expectations" in case, f"case {i} missing 'expectations'"


def test_each_item_has_required_keys():
    data = _load()
    for i, case in enumerate(data):
        item = case["item"]
        assert "id" in item, f"case {i} item missing 'id'"
        assert "title" in item, f"case {i} item missing 'title'"
        assert "excerpt" in item, f"case {i} item missing 'excerpt'"


def test_each_gold_validates_as_item_enrichment():
    data = _load()
    for i, case in enumerate(data):
        try:
            ItemEnrichment.model_validate(case["gold"])
        except Exception as exc:
            raise AssertionError(f"case {i} gold failed ItemEnrichment validation: {exc}") from exc


def test_each_expectations_has_all_dimensions():
    data = _load()
    for i, case in enumerate(data):
        expectations = case["expectations"]
        for dim in _DIMENSIONS:
            assert dim in expectations, f"case {i} expectations missing dimension '{dim}'"
            assert isinstance(expectations[dim], bool), (
                f"case {i} expectations['{dim}'] must be bool, got {type(expectations[dim])}"
            )


def test_at_least_one_faithfulness_false():
    data = _load()
    assert any(
        not case["expectations"]["faithfulness"] for case in data
    ), "Need at least one case where faithfulness expectation is False"


def test_at_least_one_category_accuracy_false():
    data = _load()
    assert any(
        not case["expectations"]["category_accuracy"] for case in data
    ), "Need at least one case where category_accuracy expectation is False"


def test_at_least_one_importance_calibration_false():
    data = _load()
    assert any(
        not case["expectations"]["importance_calibration"] for case in data
    ), "Need at least one case where importance_calibration expectation is False"


def test_at_least_one_ar_translation_quality_false():
    data = _load()
    assert any(
        not case["expectations"]["ar_translation_quality"] for case in data
    ), "Need at least one case where ar_translation_quality expectation is False"


def test_ids_are_unique():
    data = _load()
    ids = [case["item"]["id"] for case in data]
    assert len(ids) == len(set(ids)), "All item ids must be unique"


def test_gold_ids_match_item_ids():
    data = _load()
    for i, case in enumerate(data):
        assert case["item"]["id"] == case["gold"]["id"], (
            f"case {i}: item.id={case['item']['id']} != gold.id={case['gold']['id']}"
        )
