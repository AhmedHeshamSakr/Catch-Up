from __future__ import annotations

import asyncio
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from google.adk.runners import Runner
from google.adk.sessions import (
    BaseSessionService,
    DatabaseSessionService,
    InMemorySessionService,
)
from google.genai import types

from app.adapters.storage.sqlite_backend import SqliteBackend
from app.core.config import Settings
from app.core.domain import DigestRun, RunStatus
from app.core.ports.storage import StorageBackend
from app.pipeline.agents import build_pipeline
from app.services import (  # noqa: F401 — monkeypatch targets (runner.rss etc.)
    newsapi,
    normalize,
    rss,
    scrape,
    search,
    youtube,
)
from app.services.render import excel, markdown  # noqa: F401 — monkeypatch targets
from app.services.render import html as html_render  # noqa: F401 — monkeypatch target


def _firestore_client(settings: Settings):
    """Construct a real Firestore client; clear error if the extra is missing."""
    try:
        from google.cloud import firestore
    except ImportError as exc:  # optional [firestore] extra not installed
        raise RuntimeError(
            "storage_backend='firestore' requires the [firestore] extra: "
            "uv pip install '.[firestore]'"
        ) from exc
    return firestore.Client(project=settings.google_cloud_project or None)


# Cache one Firestore backend (and its client) per project per process: the API
# calls build_storage() on every request, and constructing a real
# firestore.Client each time is expensive. SQLite stays per-call (cheap).
_firestore_cache: dict[tuple[str, str], StorageBackend] = {}
_firestore_cache_lock = threading.Lock()


def build_storage(settings: Settings) -> StorageBackend:
    backend = settings.storage_backend
    if backend == "sqlite":
        store: StorageBackend = SqliteBackend(settings.sqlite_path)
        store.init_schema()
        return store
    if backend == "firestore":
        key = ("firestore", settings.google_cloud_project)
        cached = _firestore_cache.get(key)
        if cached is None:
            with _firestore_cache_lock:  # double-checked: avoid a concurrent double-build
                cached = _firestore_cache.get(key)
                if cached is None:
                    from app.adapters.storage.firestore_backend import FirestoreBackend
                    cached = FirestoreBackend(_firestore_client(settings))
                    cached.init_schema()
                    _firestore_cache[key] = cached
        return cached
    raise ValueError(f"unknown storage_backend: {backend!r}")


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


async def _run_tree(tree, run_id: str, session_service) -> None:
    runner = Runner(agent=tree, app_name="catchup", session_service=session_service)
    session = await session_service.create_session(
        app_name="catchup", user_id="system", state={"run_id": run_id}
    )
    msg = types.Content(role="user", parts=[types.Part.from_text(text="run")])
    async for _ in runner.run_async(user_id="system", session_id=session.id, new_message=msg):
        pass


async def _run_tree_with_timeout(tree, run_id: str, session_service, timeout: float | None) -> None:
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
        await _run_tree(tree, run_id, session_service)
    else:
        await asyncio.wait_for(_run_tree(tree, run_id, session_service), timeout=timeout)


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
    settings = settings or Settings()
    storage = storage or build_storage(settings)
    # Caller (e.g. POST /api/runs) may inject the run_id so it can be returned
    # to the client before the run finishes; otherwise generate one.
    run_id = run_id or uuid.uuid4().hex[:12]
    tree = build_pipeline(
        settings, storage,
        processor=processor,
        narrator=narrator,
        critic=critic,
        reprocessor=reprocessor,
    )
    session_service = make_session_service(settings)

    async def _run_and_close() -> None:
        # Dispose the session service's DB engine in the SAME loop it was used in
        # (DatabaseSessionService opens a SQLAlchemy async engine per run); without
        # this the long-running API process would accumulate connection pools.
        try:
            await _run_tree_with_timeout(
                tree, run_id, session_service, settings.run_timeout
            )
        finally:
            engine = getattr(session_service, "db_engine", None)
            if engine is not None:
                await engine.dispose()

    try:
        asyncio.run(_run_and_close())
    except Exception as exc:
        run = storage.get_run(run_id)
        if run is not None:
            run.status = RunStatus.FAILED
            run.finished_at = datetime.now(UTC)
            run.source_errors.append({"error": str(exc), "ts": datetime.now(UTC).isoformat()})
            storage.finalize_run(run)
        raise
    return storage.get_run(run_id)
