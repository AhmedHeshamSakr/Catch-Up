"""Unit tests for app/pipeline/critic.py — B1. Fully offline, no live model calls."""
from __future__ import annotations

import json

from app.core.domain import NewsItem, SourceType
from app.pipeline.critic import _CRITIC_PROMPT, _critic_payload, build_critic_agent
from app.pipeline.eval_schema import FaithfulnessVerdict, FaithfulnessVerdicts


def _make_item(item_id: str, title: str, excerpt: str = "",
               summary_en: str = "", summary_ar: str = "") -> NewsItem:
    return NewsItem(
        id=item_id,
        source_id="test",
        source_type=SourceType.RSS,
        source_name="Test",
        url=f"https://test.local/{item_id}",
        title=title,
        excerpt=excerpt,
        summary_en=summary_en,
        summary_ar=summary_ar,
    )


def test_build_critic_agent_output_schema_and_name():
    agent = build_critic_agent("gemini-flash-latest")
    assert agent.name == "faithfulness_critic"
    assert agent.output_schema is FaithfulnessVerdicts


def test_critic_instruction_contains_rubric():
    # The rubric marker word "UNFAITHFUL" must appear in the composed instruction
    assert "UNFAITHFUL" in _CRITIC_PROMPT


def test_critic_agent_has_no_tools():
    agent = build_critic_agent("gemini-flash-latest")
    # No tools attached to the agent
    assert not agent.tools


def test_critic_payload_shape():
    item = _make_item("id-1", "OpenAI launches GPT-5", "OpenAI announced GPT-5 today.",
                      summary_en="GPT-5 was released.", summary_ar="أُطلق GPT-5.")
    payload = _critic_payload([item])
    records = json.loads(payload)
    assert len(records) == 1
    rec = records[0]
    assert rec["id"] == "id-1"
    assert rec["title"] == "OpenAI launches GPT-5"
    assert rec["excerpt"] == "OpenAI announced GPT-5 today."
    assert rec["summary_en"] == "GPT-5 was released."
    assert rec["summary_ar"] == "أُطلق GPT-5."


def test_critic_payload_none_fields_coerced_to_empty():
    item = _make_item("id-2", "Headline")
    # excerpt, summary_en, summary_ar are None
    payload = _critic_payload([item])
    records = json.loads(payload)
    assert records[0]["excerpt"] == ""
    assert records[0]["summary_en"] == ""
    assert records[0]["summary_ar"] == ""


def test_critic_payload_multiple_items():
    items = [_make_item(f"id-{i}", f"Title {i}") for i in range(3)]
    payload = _critic_payload(items)
    records = json.loads(payload)
    assert len(records) == 3
    assert [r["id"] for r in records] == ["id-0", "id-1", "id-2"]


def test_faithfulness_verdicts_round_trip():
    fv = FaithfulnessVerdicts(
        verdicts=[
            FaithfulnessVerdict(item_id="x1", faithful=True, issues=[]),
            FaithfulnessVerdict(item_id="x2", faithful=False,
                                issues=["hallucinated date"],
                                suggested_summary_en="A correct summary."),
        ]
    )
    json_str = fv.model_dump_json()
    restored = FaithfulnessVerdicts.model_validate_json(json_str)
    assert len(restored.verdicts) == 2
    assert restored.verdicts[0].faithful is True
    assert restored.verdicts[1].faithful is False
    assert restored.verdicts[1].issues == ["hallucinated date"]
    assert restored.verdicts[1].suggested_summary_en == "A correct summary."
