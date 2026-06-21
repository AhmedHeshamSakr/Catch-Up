from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from google.adk.agents import Agent
from google.genai import types

from app.core.config import Settings
from app.core.domain import Importance, NewsItem
from app.llm.parse import parse_model_json, truncate_excerpt
from app.llm.runtime import run_agent_text
from app.llm.schema import ItemEnrichment, ProcessingResult
from app.pipeline.eval_schema import FaithfulnessVerdict
from app.services.watchlist import Watchlist, apply_boost

EnrichFn = Callable[[list[NewsItem]], ProcessingResult]
# Re-enrich flagged items USING the critic's per-item feedback. Returns a
# ProcessingResult shaped exactly like the enricher's output so the guardrail
# stage can reuse the same field-mapping (_apply_enrichment).
ReprocessFn = Callable[[list[NewsItem], list[FaithfulnessVerdict]], ProcessingResult]

_PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
_PROMPT = (_PROMPTS / "processing.md").read_text(encoding="utf-8")
_REPROCESS_PROMPT = (_PROMPTS / "reprocess.md").read_text(encoding="utf-8")


def score_to_importance(score: float) -> Importance:
    if score >= 0.66:
        return Importance.HIGH
    if score >= 0.33:
        return Importance.MEDIUM
    return Importance.LOW


def _batches(items: list[NewsItem], size: int) -> list[list[NewsItem]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _items_json(items: list[NewsItem]) -> str:
    return json.dumps(
        [
            {"id": it.id, "title": it.title, "excerpt": truncate_excerpt(it.excerpt)}
            for it in items
        ],
        ensure_ascii=False,
    )


def build_processing_agent(model: str, temperature: float = 0.0) -> Agent:
    return Agent(
        name="news_processor",
        model=model,
        instruction=_PROMPT,
        output_schema=ProcessingResult,
        generate_content_config=types.GenerateContentConfig(temperature=temperature),
    )


def adk_enrich(items: list[NewsItem], settings: Settings) -> ProcessingResult:
    """Real LLM call. Validated by the live smoke (needs GOOGLE_API_KEY)."""
    agent = build_processing_agent(settings.llm_model, settings.llm_temperature)
    text = run_agent_text(agent, _items_json(items), settings)
    return parse_model_json(text, ProcessingResult)


def _reprocess_payload(
    items: list[NewsItem], verdict_map: dict[str, FaithfulnessVerdict]
) -> str:
    """Augment each flagged item with the critic's feedback and prior summary.

    The critic feedback and prior summary are carried as DATA fields (not
    instructions) so the reprocess agent can avoid repeating the flagged error
    while staying anti-injection (see reprocess.md).
    """
    records = []
    for it in items:
        verdict = verdict_map.get(it.id)
        feedback = "; ".join(verdict.issues) if verdict and verdict.issues else ""
        records.append(
            {
                "id": it.id,
                "title": it.title,
                "excerpt": truncate_excerpt(it.excerpt),
                "prior_summary_en": (it.summary_en or ""),
                "critic_feedback": feedback,
            }
        )
    return json.dumps(records, ensure_ascii=False)


def build_reprocess_agent(model: str, temperature: float = 0.0) -> Agent:
    return Agent(
        name="news_reprocessor",
        model=model,
        instruction=_REPROCESS_PROMPT,
        output_schema=ProcessingResult,
        generate_content_config=types.GenerateContentConfig(temperature=temperature),
    )


def adk_reprocess(
    items: list[NewsItem],
    verdicts: list[FaithfulnessVerdict],
    settings: Settings,
) -> ProcessingResult:
    """Real LLM call. Re-summarize critic-flagged items with feedback in context."""
    verdict_map = {v.item_id: v for v in verdicts}
    agent = build_reprocess_agent(settings.llm_model, settings.llm_temperature)
    text = run_agent_text(agent, _reprocess_payload(items, verdict_map), settings)
    return parse_model_json(text, ProcessingResult)


def _apply_enrichment(
    item: NewsItem,
    enrichment: ItemEnrichment,
    watchlist: Watchlist,
    threshold: float,
) -> None:
    """Map an ItemEnrichment onto a NewsItem (shared by enrich + re-enrich)."""
    item.category = enrichment.category
    item.importance_score = enrichment.importance_score
    item.summary_en = enrichment.summary_en
    item.summary_ar = enrichment.summary_ar
    item.entities = enrichment.entities
    item.sentiment = enrichment.sentiment
    apply_boost(item, watchlist)
    item.importance = score_to_importance(item.importance_score)
    item.status = "processed" if item.importance_score >= threshold else "filtered"


def process_items(
    items: list[NewsItem],
    enrich: EnrichFn,
    watchlist: Watchlist,
    threshold: float,
    batch_size: int,
    errors: list[dict] | None = None,
) -> list[dict]:
    """Enrich items batch by batch with per-batch isolation.

    A batch that raises does not abort the stage: the error is recorded and the
    failed batch's items fall through to ``status="raw"``. Returns the list of
    per-batch error dicts (the same object as ``errors`` when one is passed in).
    """
    if errors is None:
        errors = []
    if not items:
        return errors
    enrichments = {}
    for i, batch in enumerate(_batches(items, batch_size)):
        try:
            result = enrich(batch)
        except Exception as exc:  # isolate one batch's failure from the stage
            errors.append({"batch": i, "error": str(exc)})
            continue
        for e in result.items:
            enrichments[e.id] = e
    for item in items:
        e = enrichments.get(item.id)
        if e is None:
            item.status = "raw"
            continue
        _apply_enrichment(item, e, watchlist, threshold)
    return errors
