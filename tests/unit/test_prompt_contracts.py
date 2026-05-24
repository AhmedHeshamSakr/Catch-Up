"""G5 prompt-engineering hardening — fully offline contract tests.

Covers:
- Shared excerpt truncation across producer / critic / reprocess / judge payloads.
- Anchored importance bands present in the prompts.
- Governed EntityType (validator behaviour) + allowed values stated in prompt.
- Sentiment governance documented in the rubric.
- First-class Arabic guidance in prompts + rubric + youtube summary.
- Echoed output contract (field/dimension names + thresholds) in judge/critic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.domain import Entity, EntityType, NewsItem, SourceType
from app.llm.parse import EXCERPT_CHARS, truncate_excerpt
from app.llm.schema import ItemEnrichment
from app.pipeline.critic import _critic_payload
from app.pipeline.judge import _judge_payload
from app.pipeline.processing import _items_json, _reprocess_payload

_PROMPTS = Path(__file__).resolve().parents[2] / "app" / "prompts"


def _read(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8")


def _item(excerpt: str, item_id: str = "x1") -> NewsItem:
    return NewsItem(
        id=item_id,
        source_id="s",
        source_type=SourceType.RSS,
        source_name="S",
        url=f"https://t.local/{item_id}",
        title="A headline",
        excerpt=excerpt,
        summary_en="en",
        summary_ar="ar",
    )


# ---------------------------------------------------------------------------
# ITEM 1 — shared excerpt truncation (producer == critic == reprocess == judge)
# ---------------------------------------------------------------------------

def test_truncate_excerpt_helper_clips_to_constant():
    assert truncate_excerpt("a" * (EXCERPT_CHARS + 100)) == "a" * EXCERPT_CHARS
    assert len(truncate_excerpt("a" * 5000)) == EXCERPT_CHARS
    assert truncate_excerpt(None) == ""
    assert truncate_excerpt("short") == "short"


def test_all_payload_builders_truncate_to_same_length():
    over = "x" * (EXCERPT_CHARS + 500)
    item = _item(over)
    enrichment = ItemEnrichment.model_validate(
        {
            "id": "x1",
            "category": "ai_tech",
            "importance_score": 0.5,
            "summary_en": "en",
            "summary_ar": "ar",
            "entities": [],
            "sentiment": "neutral",
        }
    )

    producer = json.loads(_items_json([item]))[0]["excerpt"]
    critic = json.loads(_critic_payload([item]))[0]["excerpt"]
    reprocess = json.loads(_reprocess_payload([item], {}))[0]["excerpt"]
    judge = json.loads(_judge_payload([(item, enrichment)]))[0]["excerpt"]

    assert len(producer) == EXCERPT_CHARS
    assert producer == critic == reprocess == judge
    # All identical to the shared helper's output.
    assert producer == truncate_excerpt(over)


def test_rubric_states_600_char_source_window():
    rubric = _read("faithfulness_rubric.md")
    assert "600" in rubric


# ---------------------------------------------------------------------------
# ITEM 2 — anchored importance bands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prompt", ["processing.md", "reprocess.md", "faithfulness_rubric.md"])
def test_importance_bands_present(prompt):
    text = _read(prompt)
    dash = "\u2013"  # EN DASH (escaped), matching the bands in the prompt files
    for lo, hi in (("0.0", "0.2"), ("0.3", "0.5"), ("0.6", "0.8"), ("0.9", "1.0")):
        band = f"{lo}{dash}{hi}"
        assert band in text, f"{prompt} missing importance band {band}"


# ---------------------------------------------------------------------------
# ITEM 3 — governed entities + sentiment
# ---------------------------------------------------------------------------

def test_entity_type_enum_members():
    assert {t.value for t in EntityType} == {"company", "person", "org", "place", "product"}


def test_entity_default_type_is_org():
    assert Entity(name="X").type is EntityType.ORG


def test_entity_type_accepts_canonical_values():
    for value in ("company", "person", "org", "place", "product"):
        assert Entity(name="X", type=value).type.value == value


def test_entity_type_maps_synonyms():
    assert Entity(name="X", type="organization").type is EntityType.ORG
    assert Entity(name="X", type="Organisation").type is EntityType.ORG
    assert Entity(name="X", type="corporation").type is EntityType.COMPANY
    assert Entity(name="X", type="location").type is EntityType.PLACE
    assert Entity(name="X", type="country").type is EntityType.PLACE


def test_entity_type_unknown_falls_back_to_org():
    # Soft governance: never reject legacy/unknown strings (keeps stored JSON valid).
    assert Entity(name="X", type="gibberish").type is EntityType.ORG


def test_entity_legacy_org_json_deserializes():
    # Stored JSON with the old default must still round-trip.
    e = Entity.model_validate({"name": "OpenAI", "type": "org"})
    assert e.type is EntityType.ORG


def test_processing_prompt_states_allowed_entity_types():
    text = _read("processing.md")
    for value in ("company", "person", "org", "place", "product"):
        assert value in text


def test_rubric_governs_sentiment():
    assert "sentiment" in _read("faithfulness_rubric.md").lower()


# ---------------------------------------------------------------------------
# ITEM 4 — Arabic first-class
# ---------------------------------------------------------------------------

def test_processing_prompt_arabic_independent_msa():
    text = _read("processing.md")
    assert "Modern Standard Arabic" in text
    assert "INDEPENDENT" in text
    assert "dialect" in text.lower()


def test_rubric_has_ar_register_check():
    text = _read("faithfulness_rubric.md")
    assert "Modern Standard Arabic" in text
    assert "dialect" in text.lower()


def test_youtube_summary_handles_arabic():
    text = _read("youtube_summary.md")
    assert "Arabic" in text
    assert "Modern Standard Arabic" in text


# ---------------------------------------------------------------------------
# ITEM 5 — echoed output contract + thresholds in judge/critic prompts
# ---------------------------------------------------------------------------

def test_judge_prompt_echoes_dimension_names_and_thresholds():
    text = _read("judge.md")
    for dim in (
        "faithfulness",
        "category_accuracy",
        "importance_calibration",
        "ar_translation_quality",
    ):
        assert dim in text, f"judge.md missing dimension {dim}"
    assert "item_id" in text
    for bar in ("0.9", "0.85", "0.7", "0.8"):
        assert bar in text, f"judge.md missing threshold {bar}"


def test_critic_prompt_echoes_output_contract():
    text = _read("critic.md")
    for field in ("item_id", "faithful", "issues", "suggested_summary_en"):
        assert field in text, f"critic.md missing field {field}"
    assert "0.9" in text  # faithfulness bar echoed
