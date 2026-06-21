from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from google.adk.agents import Agent
from google.genai import types

from app.core.config import Settings
from app.core.domain import Importance, NewsItem
from app.llm.parse import parse_model_json, truncate_excerpt
from app.llm.runtime import run_agent_text
from app.pipeline.eval_schema import FaithfulnessVerdict, FaithfulnessVerdicts
from app.pipeline.processing import ReprocessFn, _apply_enrichment, score_to_importance
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


def build_critic_agent(model: str, temperature: float = 0.0) -> Agent:
    return Agent(
        name="faithfulness_critic",
        model=model,
        instruction=_CRITIC_PROMPT,
        output_schema=FaithfulnessVerdicts,
        generate_content_config=types.GenerateContentConfig(temperature=temperature),
    )


def _critic_payload(items: list[NewsItem]) -> str:
    records = [
        {
            "id": item.id,
            "title": item.title,
            # Truncate to the SAME EXCERPT_CHARS limit the producer saw, so the
            # critic grades faithfulness against the identical source text.
            "excerpt": truncate_excerpt(item.excerpt),
            "summary_en": (item.summary_en or ""),
            "summary_ar": (item.summary_ar or ""),
        }
        for item in items
    ]
    return json.dumps(records, ensure_ascii=False)


def adk_critique(items: list[NewsItem], settings: Settings) -> list[FaithfulnessVerdict]:
    """Real LLM call. Requires GOOGLE_API_KEY."""
    agent = build_critic_agent(settings.llm_model, settings.llm_temperature)
    text = run_agent_text(agent, _critic_payload(items), settings)
    return parse_model_json(text, FaithfulnessVerdicts).verdicts


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
        if verdict is not None and verdict.faithful:
            continue  # explicitly judged faithful — untouched

        # UNFAITHFUL, or NO verdict at all. A missing verdict is a FAILURE, not a
        # pass: the critic returned an incomplete (but schema-valid) response, and
        # every item here was deliberately selected as high-risk — so we must not
        # ship it unchecked. Fail closed → flag/redact.
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
            if verdict is not None and verdict.suggested_summary_en:
                # The suggestion is the corrected, faithful text — keep it and do
                # NOT redact or downrank (status stays processed). The verdict has
                # no Arabic suggestion, so drop the old (now-unverified) AR summary
                # rather than ship it next to corrected English.
                item.summary_en = verdict.suggested_summary_en
                item.summary_ar = None
            else:
                # No verdict or no suggestion → downrank + redact the unfaithful text.
                item.status = "flagged"
                item.importance_score = min(item.importance_score or 0.0, threshold - 0.01)
                item.importance = score_to_importance(item.importance_score)
                redact_unfaithful(item)
                flagged_count += 1

    return {
        "flagged": flagged_count,
        "verdicts": [v.model_dump() for v in verdicts],
    }


def reflect_and_correct(
    selected: list[NewsItem],
    critic: CriticFn,
    reprocessor: ReprocessFn,
    watchlist: Watchlist,
    settings: Settings,
) -> dict:
    """Bounded faithfulness reflection: detect → re-enrich-with-feedback → re-critique.

    Critiques ``selected``; for items flagged UNFAITHFUL, while reflection budget
    remains, re-enriches them with the critic's feedback in context, re-applies
    the enrichment, and re-critiques ONLY those re-enriched items. Items that are
    faithful after correction are kept (status processed, corrected summary).
    Whatever remains unfaithful when the budget is exhausted is handled by
    ``apply_verdicts`` (flag/downrank/redact per ``critic_action``).

    Returns the same outcome dict shape as ``apply_verdicts`` (``flagged``,
    ``verdicts``) plus a ``corrected`` count, so the run wiring is unchanged.

    ``critic_max_reflections == 0`` reduces to the pre-batch path (a single
    critique + ``apply_verdicts``), so no reprocessor call is made.
    """
    # latest_verdict tracks the most recent verdict per item id so the final
    # apply_verdicts call reflects the post-reflection state.
    latest_verdict: dict[str, FaithfulnessVerdict] = {}
    for v in critic(selected):
        latest_verdict[v.item_id] = v

    items_by_id = {it.id: it for it in selected}
    corrected = 0
    degraded = False
    budget = settings.critic_max_reflections

    # Items still unfaithful after the most recent critique.
    pending = [
        items_by_id[v.item_id]
        for v in latest_verdict.values()
        if not v.faithful and v.item_id in items_by_id
    ]

    while budget > 0 and pending:
        budget -= 1
        feedback = [latest_verdict[it.id] for it in pending]
        try:
            result = reprocessor(pending, feedback)
        except Exception:
            # Re-enrichment failed: keep the existing (unfaithful) verdicts so the
            # items fall through to flag/redact below. Record the degradation (so a
            # down reflection subsystem is observable) and stop reflecting.
            degraded = True
            break

        enrichments = {e.id: e for e in result.items}
        re_enriched: list[NewsItem] = []
        for item in pending:
            enrichment = enrichments.get(item.id)
            if enrichment is None:
                # No corrected enrichment returned — leave the unfaithful verdict
                # in place so it is flagged/redacted below.
                continue
            _apply_enrichment(item, enrichment, watchlist, settings.importance_threshold)
            re_enriched.append(item)

        if not re_enriched:
            break

        # Re-critique ONLY the re-enriched items and refresh their verdicts.
        new_verdicts = {v.item_id: v for v in critic(re_enriched)}
        next_pending: list[NewsItem] = []
        for item in re_enriched:
            v = new_verdicts.get(item.id)
            if v is None:
                continue
            latest_verdict[item.id] = v
            if v.faithful:
                corrected += 1
            else:
                next_pending.append(item)
        pending = next_pending

    final_verdicts = list(latest_verdict.values())
    outcome = apply_verdicts(
        selected,
        final_verdicts,
        settings.critic_action,
        settings.importance_threshold,
    )
    outcome["corrected"] = corrected
    outcome["degraded"] = degraded
    return outcome
