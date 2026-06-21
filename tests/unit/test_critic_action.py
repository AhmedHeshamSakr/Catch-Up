"""Unit tests for apply_verdicts — B3. Fully offline."""
from __future__ import annotations

from app.core.domain import Category, Importance, NewsItem, RawItem, SourceType
from app.pipeline.critic import apply_verdicts
from app.pipeline.eval_schema import FaithfulnessVerdict


def _item(url: str, title: str, score: float = 0.8, status: str = "processed") -> NewsItem:
    raw = RawItem(source_id="s", source_type=SourceType.RSS, source_name="S",
                  url=url, title=title, category_hint=Category.AI_TECH)
    it = NewsItem.from_raw(raw)
    it.importance_score = score
    it.importance = Importance.HIGH
    it.status = status
    it.summary_en = "Original English summary."
    return it


def _faithful(item_id: str) -> FaithfulnessVerdict:
    return FaithfulnessVerdict(item_id=item_id, faithful=True, issues=[])


def _unfaithful(item_id: str, suggested: str | None = None) -> FaithfulnessVerdict:
    return FaithfulnessVerdict(
        item_id=item_id,
        faithful=False,
        issues=["hallucinated statistic"],
        suggested_summary_en=suggested,
    )


THRESHOLD = 0.33


def test_faithful_verdict_leaves_item_untouched():
    item = _item("https://a.com/1", "News 1", score=0.9)
    original_score = item.importance_score
    original_status = item.status
    verdict = _faithful(item.id)
    outcome = apply_verdicts([item], [verdict], "flag", THRESHOLD)
    assert item.status == original_status
    assert item.importance_score == original_score
    assert outcome["flagged"] == 0


def test_no_verdict_fails_closed():
    """A selected item with NO verdict must FAIL CLOSED (flagged), not ship
    unchecked: the critic returned an incomplete response and these items were
    deliberately selected because they are high-risk."""
    item = _item("https://a.com/2", "News 2", score=0.9)
    # Pass an empty verdicts list — item has no verdict
    outcome = apply_verdicts([item], [], "flag", THRESHOLD)
    assert item.status == "flagged"
    assert outcome["flagged"] == 1


def test_flag_action_sets_status_flagged():
    item = _item("https://a.com/3", "News 3", score=0.9)
    verdict = _unfaithful(item.id)
    outcome = apply_verdicts([item], [verdict], "flag", THRESHOLD)
    assert item.status == "flagged"
    assert outcome["flagged"] == 1
    # Score should NOT be changed for plain flag
    assert item.importance_score == 0.9


def test_downrank_sets_score_below_threshold_and_flags():
    item = _item("https://a.com/4", "News 4", score=0.9)
    verdict = _unfaithful(item.id)
    outcome = apply_verdicts([item], [verdict], "downrank", THRESHOLD)
    assert item.status == "flagged"
    assert item.importance_score < THRESHOLD
    assert item.importance_score == THRESHOLD - 0.01
    assert item.importance == Importance.LOW  # 0.32 < 0.33 threshold for LOW
    assert outcome["flagged"] == 1


def test_replace_with_suggestion_swaps_summary_and_does_not_downrank():
    item = _item("https://a.com/5", "News 5", score=0.9)
    verdict = _unfaithful(item.id, suggested="A faithful rewrite from source.")
    outcome = apply_verdicts([item], [verdict], "replace", THRESHOLD)
    # Summary replaced
    assert item.summary_en == "A faithful rewrite from source."
    # NOT downranked — score and importance unchanged
    assert item.importance_score == 0.9
    assert item.importance == Importance.HIGH
    # Status NOT set to flagged
    assert item.status != "flagged"
    assert outcome["flagged"] == 0


def test_replace_without_suggestion_falls_back_to_downrank():
    item = _item("https://a.com/6", "News 6", score=0.9)
    verdict = _unfaithful(item.id, suggested=None)
    outcome = apply_verdicts([item], [verdict], "replace", THRESHOLD)
    assert item.status == "flagged"
    assert item.importance_score < THRESHOLD
    assert outcome["flagged"] == 1


def test_verdicts_dict_in_outcome():
    item = _item("https://a.com/7", "News 7", score=0.9)
    verdict = _unfaithful(item.id)
    outcome = apply_verdicts([item], [verdict], "flag", THRESHOLD)
    assert "verdicts" in outcome
    assert isinstance(outcome["verdicts"], list)
    assert len(outcome["verdicts"]) == 1
    assert outcome["verdicts"][0]["item_id"] == item.id
    assert outcome["verdicts"][0]["faithful"] is False


def test_mixed_faithful_and_unfaithful():
    item_good = _item("https://a.com/8", "Good news", score=0.9)
    item_bad = _item("https://a.com/9", "Bad news", score=0.85)
    verdicts = [_faithful(item_good.id), _unfaithful(item_bad.id)]
    outcome = apply_verdicts([item_good, item_bad], verdicts, "downrank", THRESHOLD)
    assert item_good.status == "processed"
    assert item_good.importance_score == 0.9
    assert item_bad.status == "flagged"
    assert item_bad.importance_score < THRESHOLD
    assert outcome["flagged"] == 1
