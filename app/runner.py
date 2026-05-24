from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from google.adk.runners import InMemoryRunner
from google.genai import types

from app.adapters.storage.sqlite_backend import SqliteBackend
from app.core.config import Settings, SourceConfig
from app.core.domain import (
    DigestRun,
    NewsItem,
    RawItem,
    RunStatus,
    SourceType,
)
from app.core.ports.storage import StorageBackend
from app.pipeline import critic as critic_module
from app.pipeline import digest_editor, processing
from app.services import (  # noqa: F401 — monkeypatch targets
    newsapi,
    normalize,
    rss,
    scrape,
    search,
    youtube,
)
from app.services.render import excel, markdown  # noqa: F401 — monkeypatch targets
from app.services.render import html as html_render  # noqa: F401 — monkeypatch target


def build_storage(settings: Settings) -> StorageBackend:
    backend = SqliteBackend(settings.sqlite_path)
    backend.init_schema()
    return backend


def _collect(source: SourceConfig, settings: Settings, storage: StorageBackend | None = None) -> list[RawItem]:
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


def select_rendered(items: list[NewsItem]) -> list[NewsItem]:
    """Select items to render: processed items, or all non-flagged if none processed."""
    return [i for i in items if i.status == "processed"] or [i for i in items if i.status != "flagged"]


async def _run_tree(tree, run_id: str) -> None:
    runner = InMemoryRunner(agent=tree, app_name="catchup")
    session = await runner.session_service.create_session(
        app_name="catchup", user_id="system", state={"run_id": run_id}
    )
    msg = types.Content(role="user", parts=[types.Part.from_text(text="run")])
    async for _ in runner.run_async(user_id="system", session_id=session.id, new_message=msg):
        pass


def run_digest(
    settings: Settings | None = None,
    storage: StorageBackend | None = None,
    processor=None,
    narrator=None,
    critic=None,
) -> DigestRun:
    # Deferred: app.pipeline.agents imports this module at top level, so
    # importing it here at module scope would reintroduce a load-time cycle.
    from app.pipeline.agents import build_pipeline

    settings = settings or Settings()
    storage = storage or build_storage(settings)
    run_id = uuid.uuid4().hex[:12]
    tree = build_pipeline(
        settings, storage,
        run_id=run_id,
        processor=processor,
        narrator=narrator,
        critic=critic,
    )
    try:
        asyncio.run(_run_tree(tree, run_id))
    except Exception as exc:
        run = storage.get_run(run_id)
        if run is not None:
            run.status = RunStatus.FAILED
            run.finished_at = datetime.now(UTC)
            run.source_errors.append({"error": str(exc), "ts": datetime.now(UTC).isoformat()})
            storage.finalize_run(run)
        raise
    return storage.get_run(run_id)
