"""Unit tests for tests/eval/fixtures/enrichment_reference.json — fully offline."""
from __future__ import annotations

import json
from pathlib import Path

from app.pipeline.schema import ItemEnrichment

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


def test_fixture_file_parses():
    data = _load()
    assert isinstance(data, list)
    assert len(data) >= 8, "Expected at least 8 reference cases (5 happy-path + adversarial)"


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
