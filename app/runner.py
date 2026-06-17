from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

from google.adk.runners import InMemoryRunner
from google.adk.sessions import (
    BaseSessionService,
    DatabaseSessionService,
    InMemorySessionService,
)
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


def _resolve_session_db_url(settings: Settings) -> str:
    """Effective ADK session DB URL. Empty session_db_url => a local SQLite file
    next to sqlite_path (separate from the app DB; ADK owns its own schema)."""
    if settings.session_db_url:
        return settings.session_db_url
    db_path = Path(settings.sqlite_path).resolve().parent / "sessions.db"
    return f"sqlite+aiosqlite:///{db_path}"


def make_session_service(settings: Settings) -> BaseSessionService:
    """Build the ADK session service for a run from settings.session_backend."""
    if settings.session_backend == "memory":
        return InMemorySessionService()
    return DatabaseSessionService(db_url=_resolve_session_db_url(settings))


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


def _default_reprocessor(settings: Settings):
    return lambda items, verdicts: processing.adk_reprocess(items, verdicts, settings)


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


async def _run_tree_with_timeout(tree, run_id: str, timeout: float | None) -> None:
    """Run the tree, optionally capped by a run-level wall-clock timeout.

    On timeout, ``asyncio.wait_for`` raises ``TimeoutError`` — caught by
    run_digest's FAILED-path so the run is finalized FAILED and re-raised.

    SOFT cap: the LLM stages run their blocking calls via ``asyncio.to_thread``,
    so the timeout fires on schedule (the loop stays responsive) and the run is
    marked FAILED at the right wall-clock time — but ``asyncio.run`` waits for
    the in-flight worker thread to finish before ``run_digest`` returns (Python
    can't force-kill a thread). The hard per-call bound is ``llm_timeout`` inside
    ``run_agent_text``. Any item mutated by a worker after cancellation is on the
    FAILED path and never persisted (RenderAgent doesn't run), so it's discarded.
    """
    if timeout is None:
        await _run_tree(tree, run_id)
    else:
        await asyncio.wait_for(_run_tree(tree, run_id), timeout=timeout)


def run_digest(
    settings: Settings | None = None,
    storage: StorageBackend | None = None,
    processor=None,
    narrator=None,
    critic=None,
    reprocessor=None,
    *,
    run_id: str | None = None,
) -> DigestRun:
    # Deferred: app.pipeline.agents imports this module at top level, so
    # importing it here at module scope would reintroduce a load-time cycle.
    from app.pipeline.agents import build_pipeline

    settings = settings or Settings()
    storage = storage or build_storage(settings)
    # Caller (e.g. POST /api/runs) may inject the run_id so it can be returned
    # to the client before the run finishes; otherwise generate one.
    run_id = run_id or uuid.uuid4().hex[:12]
    tree = build_pipeline(
        settings, storage,
        run_id=run_id,
        processor=processor,
        narrator=narrator,
        critic=critic,
        reprocessor=reprocessor,
    )
    try:
        asyncio.run(_run_tree_with_timeout(tree, run_id, settings.run_timeout))
    except Exception as exc:
        run = storage.get_run(run_id)
        if run is not None:
            run.status = RunStatus.FAILED
            run.finished_at = datetime.now(UTC)
            run.source_errors.append({"error": str(exc), "ts": datetime.now(UTC).isoformat()})
            storage.finalize_run(run)
        raise
    return storage.get_run(run_id)
