"""Unit tests for app/pipeline/critic.py — B1. Fully offline, no live model calls."""
from __future__ import annotations

import json

from app.core.config import Settings
from app.core.domain import Category, NewsItem, SourceType
from app.llm.schema import ItemEnrichment, ProcessingResult
from app.pipeline.critic import (
    _CRITIC_PROMPT,
    WITHHELD_NOTICE,
    _critic_payload,
    apply_verdicts,
    build_critic_agent,
    redact_unfaithful,
    reflect_and_correct,
)
from app.pipeline.eval_schema import FaithfulnessVerdict, FaithfulnessVerdicts
from app.services.watchlist import Watchlist


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


def test_redact_unfaithful_helper_clears_summaries():
    item = _make_item("rid", "T", summary_en="Hallucinated.", summary_ar="مهلوس.")
    redact_unfaithful(item)
    assert item.summary_en == WITHHELD_NOTICE
    assert item.summary_ar is None


def test_apply_verdicts_redacts_unfaithful_under_default_action():
    """An unfaithful item under flag/downrank has its summary text redacted."""
    item = _make_item("u1", "T", summary_en="A hallucinated summary.",
                      summary_ar="ملخص مهلوس.")
    item.importance_score = 0.9
    verdicts = [FaithfulnessVerdict(item_id="u1", faithful=False,
                                    issues=["hallucinated"])]
    apply_verdicts([item], verdicts, "downrank", 0.33)
    assert item.status == "flagged"
    assert item.summary_en == WITHHELD_NOTICE
    assert item.summary_ar is None


def test_apply_verdicts_flag_redacts_unfaithful():
    item = _make_item("u2", "T", summary_en="Bad summary.", summary_ar="سيئ.")
    verdicts = [FaithfulnessVerdict(item_id="u2", faithful=False, issues=["x"])]
    apply_verdicts([item], verdicts, "flag", 0.33)
    assert item.status == "flagged"
    assert item.summary_en == WITHHELD_NOTICE
    assert item.summary_ar is None


def test_apply_verdicts_replace_with_suggestion_not_redacted():
    """A replace with a suggested faithful summary keeps the English suggestion,
    but drops the Arabic (the verdict carries no AR suggestion, so the old AR is
    unverified and must not ship next to corrected English)."""
    item = _make_item("r1", "T", summary_en="Original.", summary_ar="أصلي.")
    item.status = "processed"
    verdicts = [FaithfulnessVerdict(item_id="r1", faithful=False, issues=["x"],
                                    suggested_summary_en="A corrected faithful summary.")]
    apply_verdicts([item], verdicts, "replace", 0.33)
    assert item.summary_en == "A corrected faithful summary."
    assert item.summary_ar is None
    assert item.status == "processed"


def test_apply_verdicts_replace_without_suggestion_redacts():
    """Replace fallback (no suggestion) downranks AND redacts."""
    item = _make_item("r2", "T", summary_en="Original.", summary_ar="أصلي.")
    item.importance_score = 0.9
    verdicts = [FaithfulnessVerdict(item_id="r2", faithful=False, issues=["x"],
                                    suggested_summary_en=None)]
    apply_verdicts([item], verdicts, "replace", 0.33)
    assert item.status == "flagged"
    assert item.summary_en == WITHHELD_NOTICE
    assert item.summary_ar is None


def test_apply_verdicts_faithful_item_untouched():
    item = _make_item("f1", "T", summary_en="Good summary.", summary_ar="جيد.")
    verdicts = [FaithfulnessVerdict(item_id="f1", faithful=True, issues=[])]
    apply_verdicts([item], verdicts, "downrank", 0.33)
    assert item.status == "raw"
    assert item.summary_en == "Good summary."
    assert item.summary_ar == "جيد."


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


# ---------------------------------------------------------------------------
# reflect_and_correct — G4a bounded reflection loop. Fully offline.
# ---------------------------------------------------------------------------

_WL = Watchlist()


def _enrichment(item_id: str, summary_en: str, score: float = 0.9) -> ItemEnrichment:
    return ItemEnrichment(
        id=item_id, category=Category.AI_TECH, importance_score=score,
        summary_en=summary_en, summary_ar="ملخص.", entities=[], sentiment="neutral",
    )


def _make_high_item(item_id: str, summary_en: str = "Original summary.") -> NewsItem:
    item = _make_item(item_id, "A title", excerpt="Source excerpt text.",
                      summary_en=summary_en, summary_ar="ملخص.")
    item.importance_score = 0.9
    item.status = "processed"
    return item


def test_reflect_and_correct_fixes_unfaithful_after_one_reprocess():
    """Item unfaithful then faithful after one reprocess → kept, corrected, not flagged."""
    item = _make_high_item("c1")
    settings = Settings(critic_max_reflections=1, critic_action="downrank",
                        importance_threshold=0.33)

    calls = {"critic": 0, "reprocess": 0}

    def fake_critic(items):
        calls["critic"] += 1
        # First pass: unfaithful. Re-critique after correction: faithful.
        faithful = calls["critic"] > 1
        return [FaithfulnessVerdict(item_id=it.id, faithful=faithful,
                                    issues=[] if faithful else ["hallucinated stat"])
                for it in items]

    def fake_reprocess(items, verdicts):
        calls["reprocess"] += 1
        return ProcessingResult(items=[_enrichment(it.id, "Corrected faithful summary.")
                                       for it in items])

    outcome = reflect_and_correct([item], fake_critic, fake_reprocess, _WL, settings)

    assert calls["reprocess"] == 1
    assert outcome["flagged"] == 0
    assert outcome.get("corrected") == 1
    assert item.status == "processed"
    assert item.summary_en == "Corrected faithful summary."


def test_reflect_and_correct_flags_when_still_unfaithful_after_budget():
    """Item stays unfaithful after the budget → flagged + redacted."""
    item = _make_high_item("c2")
    settings = Settings(critic_max_reflections=1, critic_action="downrank",
                        importance_threshold=0.33)

    def always_unfaithful(items):
        return [FaithfulnessVerdict(item_id=it.id, faithful=False, issues=["bad"])
                for it in items]

    def fake_reprocess(items, verdicts):
        return ProcessingResult(items=[_enrichment(it.id, "Still wrong summary.")
                                       for it in items])

    outcome = reflect_and_correct([item], always_unfaithful, fake_reprocess, _WL, settings)

    assert outcome["flagged"] == 1
    assert item.status == "flagged"
    assert item.summary_en == WITHHELD_NOTICE
    assert item.summary_ar is None


def test_reflect_and_correct_disabled_behaves_like_apply_verdicts():
    """critic_max_reflections=0 → no reprocess call; legacy apply_verdicts behavior."""
    item = _make_high_item("c3")
    settings = Settings(critic_max_reflections=0, critic_action="downrank",
                        importance_threshold=0.33)

    reprocess_called = {"n": 0}

    def fake_critic(items):
        return [FaithfulnessVerdict(item_id=it.id, faithful=False, issues=["bad"])
                for it in items]

    def fake_reprocess(items, verdicts):
        reprocess_called["n"] += 1
        return ProcessingResult(items=[])

    outcome = reflect_and_correct([item], fake_critic, fake_reprocess, _WL, settings)

    assert reprocess_called["n"] == 0
    assert outcome["flagged"] == 1
    assert item.status == "flagged"
    assert item.summary_en == WITHHELD_NOTICE


def test_reflect_and_correct_reprocessor_raises_falls_back_to_flag():
    """Reprocessor raising must not crash — fall back to flag + redact."""
    item = _make_high_item("c4")
    settings = Settings(critic_max_reflections=1, critic_action="downrank",
                        importance_threshold=0.33)

    def fake_critic(items):
        return [FaithfulnessVerdict(item_id=it.id, faithful=False, issues=["bad"])
                for it in items]

    def boom_reprocess(items, verdicts):
        raise RuntimeError("reprocess quota exhausted")

    outcome = reflect_and_correct([item], fake_critic, boom_reprocess, _WL, settings)

    assert outcome["flagged"] == 1
    assert item.status == "flagged"
    assert item.summary_en == WITHHELD_NOTICE
    assert item.summary_ar is None
