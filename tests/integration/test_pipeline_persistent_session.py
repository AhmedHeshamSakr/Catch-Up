"""Durability guard: run the pipeline tree against a persistent session service.

The pipeline now propagates every cross-stage value via
``EventActions.state_delta`` (run/items/raws as JSON), so it is portable to any
persistent / distributed session service (Firestore / Vertex Agent Engine).
This test proves that against ADK's SQLite-backed ``DatabaseSessionService``
(the closest persistent stand-in available locally), fully offline.

The real guard is the RELOAD assertion: within a single ``run_async`` the
in-memory session masks direct-mutation bugs, so the test reloads the session
through a fresh service instance and asserts the durable ``run`` survived — only
``state_delta``-persisted values do. With the old direct-``ctx.session.state``
mutation this fails (a reload shows only ``run_id``); with the delta-driven tree
it passes. The service-availability probe stays only as a skip safety net for
environments that can't construct the async SQLite engine.
"""
from __future__ import annotations

import pytest
from google.genai import types

from app.core.config import Settings
from app.core.domain import Category, RawItem, RunStatus, SourceType
from app.llm.schema import ItemEnrichment, ProcessingResult
from app.pipeline.agents import build_pipeline
from app.runner import build_storage

# --- Availability probe ----------------------------------------------------
# DatabaseSessionService may import yet still be unusable: its SQLAlchemy async
# engine needs an async sqlite driver (aiosqlite) and greenlet. Detect that up
# front so the test skips cleanly rather than erroring on infrastructure.
try:
    from google.adk.runners import Runner
    from google.adk.sessions import DatabaseSessionService

    _DB_SESSION_IMPORTABLE = True
except Exception:  # pragma: no cover - depends on installed ADK
    _DB_SESSION_IMPORTABLE = False


def _db_url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}"


async def _service_runnable(tmp_path) -> tuple[bool, str]:
    """Try to construct the service and prepare its tables; report usability."""
    if not _DB_SESSION_IMPORTABLE:
        return False, "DatabaseSessionService unavailable in this ADK version"
    try:
        svc = DatabaseSessionService(db_url=_db_url(tmp_path))
        # create_session triggers table preparation against the async engine,
        # which is where a missing aiosqlite driver / greenlet surfaces.
        await svc.create_session(app_name="probe", user_id="system", state={})
    except Exception as exc:  # missing async driver / greenlet / etc.
        return False, f"DatabaseSessionService not runnable here: {exc}"
    return True, ""


def _settings(tmp_path) -> Settings:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text(
        "sources:\n"
        "  - id: feed1\n    type: rss\n    name: FakeFeed\n"
        "    url: https://demo/feed\n    category_hint: ai_tech\n    enabled: true\n",
        encoding="utf-8",
    )
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    return Settings(
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(cfg),
        output_dir=str(tmp_path / "out"),
    )


def _raw(url: str, title: str) -> RawItem:
    return RawItem(
        source_id="feed1",
        source_type=SourceType.RSS,
        source_name="FakeFeed",
        url=url,
        title=title,
        category_hint=Category.AI_TECH,
    )


@pytest.mark.asyncio
async def test_pipeline_tree_against_persistent_session(tmp_path):
    """Run the tree via Runner + DatabaseSessionService (offline), assert a
    SUCCESS DigestRun, then reload the session through a fresh service and assert
    the durable run survived — proving the delta-driven tree is portable to a
    persistent session service."""
    runnable, reason = await _service_runnable(tmp_path)
    if not runnable:
        pytest.skip(reason)

    settings = _settings(tmp_path)
    storage = build_storage(settings)

    def fake_collect(source, s, st=None):
        if source.type == SourceType.RSS:
            return [_raw("https://x.com/1", "Persistent session works")]
        return []

    def fake_processor(items):
        return ProcessingResult(items=[
            ItemEnrichment(
                id=i.id, category=Category.AI_TECH, importance_score=0.8,
                summary_en="Persistent summary.", summary_ar="ملخص.",
                entities=[], sentiment="neutral",
            )
            for i in items
        ])

    run_id = "persistrun001"
    tree = build_pipeline(
        settings, storage,
        collect_fn=fake_collect,
        processor=fake_processor,
        narrator=lambda items: "Narrative.",
        critic=lambda items: [],
    )

    session_service = DatabaseSessionService(db_url=_db_url(tmp_path))
    runner = Runner(agent=tree, app_name="catchup", session_service=session_service)
    session = await session_service.create_session(
        app_name="catchup", user_id="system", state={"run_id": run_id}
    )
    msg = types.Content(role="user", parts=[types.Part.from_text(text="run")])

    async for _ in runner.run_async(
        user_id="system", session_id=session.id, new_message=msg
    ):
        pass
    run = storage.get_run(run_id)
    assert run is not None
    assert run.status == RunStatus.SUCCESS
    assert run.collected == 1
    assert run.new == 1

    # Genuine durability guard: reload the session via a FRESH service instance
    # (forces a DB read). Only state_delta-persisted values survive a reload, so
    # this fails for direct ctx.session.state mutation and passes now that the
    # tree is fully delta-driven. (Within a single run_async the in-memory session
    # masks the gap, so asserting on storage alone is not enough.)
    reload_svc = DatabaseSessionService(db_url=_db_url(tmp_path))
    reloaded = await reload_svc.get_session(
        app_name="catchup", user_id="system", session_id=session.id
    )
    assert reloaded is not None
    assert "run" in reloaded.state
    assert reloaded.state["run"]["run_id"] == run_id
    assert reloaded.state["run"]["status"] == "success"

    # Dispose the per-test async engines so no SQLite connection pools linger.
    await reload_svc.db_engine.dispose()
    await session_service.db_engine.dispose()
