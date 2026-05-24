from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from google.adk.agents import Agent

from app.core.config import Settings
from app.core.domain import Importance, NewsItem
from app.llm.runtime import run_agent_text
from app.pipeline.eval_schema import FaithfulnessVerdict, FaithfulnessVerdicts
from app.pipeline.processing import score_to_importance
from app.services.watchlist import Watchlist, watchlist_matched

_PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
_RUBRIC = (_PROMPTS / "faithfulness_rubric.md").read_text(encoding="utf-8")
_CRITIC_PROMPT = (
    (_PROMPTS / "critic.md").read_text(encoding="utf-8").replace("{{RUBRIC}}", _RUBRIC)
)

CriticFn = Callable[[list[NewsItem]], list[FaithfulnessVerdict]]

# Placeholder substituted for the summary text of items that fail the
# faithfulness check, so unfaithful (possibly hallucinated) text is never
# persisted or served.
WITHHELD_NOTICE = "[Summary withheld: failed faithfulness check]"

# Importance ordering for >= comparisons: LOW < MEDIUM < HIGH
_IMPORTANCE_ORDER: dict[Importance, int] = {
    Importance.LOW: 0,
    Importance.MEDIUM: 1,
    Importance.HIGH: 2,
}


def build_critic_agent(model: str) -> Agent:
    return Agent(
        name="faithfulness_critic",
        model=model,
        instruction=_CRITIC_PROMPT,
        output_schema=FaithfulnessVerdicts,
        output_key="verdicts",
    )


def _critic_payload(items: list[NewsItem]) -> str:
    records = [
        {
            "id": item.id,
            "title": item.title,
            "excerpt": (item.excerpt or ""),
            "summary_en": (item.summary_en or ""),
            "summary_ar": (item.summary_ar or ""),
        }
        for item in items
    ]
    return json.dumps(records, ensure_ascii=False)


def adk_critique(items: list[NewsItem], settings: Settings) -> list[FaithfulnessVerdict]:
    """Real LLM call. Requires GOOGLE_API_KEY."""
    agent = build_critic_agent(settings.llm_model)
    text = run_agent_text(agent, _critic_payload(items), settings)
    return FaithfulnessVerdicts.model_validate_json(text).verdicts


def select_for_critique(
    items: list[NewsItem],
    watchlist: Watchlist,
    settings: Settings,
) -> list[NewsItem]:
    """Return items that should be fact-checked by the critic."""
    if not settings.critic_enabled:
        return []

    min_order = _IMPORTANCE_ORDER.get(settings.critic_min_importance, 2)
    selected = []
    for item in items:
        # Importance rule: item.importance must be >= critic_min_importance
        importance_qualifies = (
            item.importance is not None
            and _IMPORTANCE_ORDER.get(item.importance, -1) >= min_order
        )
        # Watchlist rule
        watchlist_qualifies = (
            settings.critic_check_watchlisted
            and watchlist_matched(item, watchlist)
        )
        if importance_qualifies or watchlist_qualifies:
            selected.append(item)
    return selected


def redact_unfaithful(item: NewsItem) -> None:
    """Replace an item's summary text after it fails the faithfulness check.

    The English summary becomes a withheld notice and the Arabic summary is
    cleared, so unfaithful (possibly hallucinated) text is never persisted or
    served downstream.
    """
    item.summary_en = WITHHELD_NOTICE
    item.summary_ar = None


def apply_verdicts(
    items: list[NewsItem],
    verdicts: list[FaithfulnessVerdict],
    action: Literal["flag", "downrank", "replace"],
    threshold: float,
) -> dict:
    """Apply faithfulness verdicts to items and return outcome stats."""
    verdict_map: dict[str, FaithfulnessVerdict] = {v.item_id: v for v in verdicts}
    flagged_count = 0

    for item in items:
        verdict = verdict_map.get(item.id)
        if verdict is None or verdict.faithful:
            continue  # faithful or no verdict — untouched

        # Item is UNFAITHFUL
        if action == "flag":
            item.status = "flagged"
            redact_unfaithful(item)
            flagged_count += 1

        elif action == "downrank":
            item.status = "flagged"
            item.importance_score = min(item.importance_score or 0.0, threshold - 0.01)
            item.importance = score_to_importance(item.importance_score)
            redact_unfaithful(item)
            flagged_count += 1

        elif action == "replace":
            if verdict.suggested_summary_en:
                # The suggestion is the corrected, faithful text — keep it and
                # do NOT redact or downrank (status stays processed).
                item.summary_en = verdict.suggested_summary_en
            else:
                # Fall back to downrank behavior (and redact the unfaithful text)
                item.status = "flagged"
                item.importance_score = min(item.importance_score or 0.0, threshold - 0.01)
                item.importance = score_to_importance(item.importance_score)
                redact_unfaithful(item)
                flagged_count += 1

    return {
        "flagged": flagged_count,
        "verdicts": [v.model_dump() for v in verdicts],
    }
