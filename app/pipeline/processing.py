from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from google.adk.agents import Agent
from google.genai import types

from app.core.config import Settings
from app.core.domain import Importance, NewsItem
from app.llm.parse import parse_model_json
from app.llm.runtime import run_agent_text
from app.llm.schema import ProcessingResult
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


def build_processing_agent(model: str, temperature: float = 0.0) -> Agent:
    return Agent(
        name="news_processor",
        model=model,
        instruction=_PROMPT,
        output_schema=ProcessingResult,
        output_key="processing_result",
        generate_content_config=types.GenerateContentConfig(temperature=temperature),
    )


def adk_enrich(items: list[NewsItem], settings: Settings) -> ProcessingResult:
    """Real LLM call. Validated by the live smoke (needs GOOGLE_API_KEY)."""
    agent = build_processing_agent(settings.llm_model, settings.llm_temperature)
    text = run_agent_text(agent, _items_json(items), settings)
    return parse_model_json(text, ProcessingResult)


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
        item.category = e.category
        item.importance_score = e.importance_score
        item.summary_en = e.summary_en
        item.summary_ar = e.summary_ar
        item.entities = e.entities
        item.sentiment = e.sentiment
        apply_boost(item, watchlist)
        item.importance = score_to_importance(item.importance_score)
        item.status = "processed" if item.importance_score >= threshold else "filtered"
    return errors
