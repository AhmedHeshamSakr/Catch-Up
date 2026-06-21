"""Default pipeline wiring: the per-source collector dispatch and the default
LLM stage factories.

These live in the pipeline package (next to their only consumer,
``app/pipeline/agents.py:build_pipeline``) so the pipeline no longer imports
from ``app.runner`` — that was a layering inversion that forced ``runner.py`` to
defer its ``build_pipeline`` import to dodge a load-time cycle.

This module must NOT import ``app.runner`` or ``build_storage`` (that would
recreate the cycle). The collector/render modules are referenced through their
own packages so tests can monkeypatch the shared module objects (e.g.
``runner.rss.collect`` patches ``app.services.rss`` for every caller).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings, SourceConfig
from app.core.domain import NewsItem, RawItem, SourceType
from app.pipeline import critic as critic_module
from app.pipeline import digest_editor, processing
from app.services import newsapi, rss, scrape, search, youtube

if TYPE_CHECKING:
    from app.core.ports.storage import StorageBackend


def _collect(
    source: SourceConfig, settings: Settings, storage: StorageBackend | None = None
) -> list[RawItem]:
    if source.type == SourceType.RSS:
        return rss.collect(source)
    if source.type == SourceType.API:
        return newsapi.collect(source, settings.gnews_api_key)
    if source.type == SourceType.SCRAPE:
        return scrape.collect(source)
    if source.type == SourceType.SEARCH:
        return search.collect(source, settings)
    if source.type == SourceType.YOUTUBE:
        return youtube.collect(source, settings, storage=storage)
    return []


def _default_processor(settings: Settings):
    return lambda items: processing.adk_enrich(items, settings)


def _default_narrator(settings: Settings):
    return lambda items: digest_editor.adk_narrate(items, settings)


def _default_critic(settings: Settings):
    return lambda items: critic_module.adk_critique(items, settings)


def _default_reprocessor(settings: Settings):
    return lambda items, verdicts: processing.adk_reprocess(items, verdicts, settings)


def select_rendered(items: list[NewsItem]) -> list[NewsItem]:
    """Select items to render: processed items, or — if none are processed — any
    that are neither flagged nor still ``raw``. Rendering ``raw`` items would ship
    un-enriched content (missing/stale summaries) as if it were a real digest, so
    a total enrichment failure yields an empty digest, not fabricated narration."""
    return [i for i in items if i.status == "processed"] or [
        i for i in items if i.status not in ("flagged", "raw")
    ]
