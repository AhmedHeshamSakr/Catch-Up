from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from google.adk.agents import Agent

from app.core.config import Settings
from app.core.domain import Importance, NewsItem
from app.pipeline.adk_runtime import run_agent_text
from app.pipeline.schema import ProcessingResult
from app.services.watchlist import Watchlist, apply_boost

EnrichFn = Callable[[list[NewsItem]], ProcessingResult]

_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "processing.md").read_text(
    encoding="utf-8"
)


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
        [{"id": it.id, "title": it.title, "excerpt": (it.excerpt or "")[:600]} for it in items],
        ensure_ascii=False,
    )


def build_processing_agent(model: str) -> Agent:
    return Agent(
        name="news_processor",
        model=model,
        instruction=_PROMPT,
        output_schema=ProcessingResult,
        output_key="processing_result",
    )


def adk_enrich(items: list[NewsItem], settings: Settings) -> ProcessingResult:
    """Real LLM call. Validated by the live smoke (needs GOOGLE_API_KEY)."""
    agent = build_processing_agent(settings.llm_model)
    text = run_agent_text(agent, _items_json(items), settings)
    return ProcessingResult.model_validate_json(text)


def process_items(
    items: list[NewsItem],
    enrich: EnrichFn,
    watchlist: Watchlist,
    threshold: float,
    batch_size: int,
) -> None:
    if not items:
        return
    enrichments = {}
    for batch in _batches(items, batch_size):
        for e in enrich(batch).items:
            enrichments[e.id] = e
    for item in items:
        e = enrichments.get(item.id)
        if e is None:
            item.status = "raw"
            continue
        item.category = e.category
        item.importance_score = e.importance_score
        item.summary_en = e.summary_en
        item.summary_ar = e.summary_ar
        item.entities = e.entities
        item.sentiment = e.sentiment
        apply_boost(item, watchlist)
        item.importance = score_to_importance(item.importance_score)
        item.status = "processed" if item.importance_score >= threshold else "filtered"
