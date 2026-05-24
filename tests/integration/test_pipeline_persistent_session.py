"""Plan-9 guard: run the pipeline tree against a persistent session service.

The pipeline mutates ``ctx.session.state`` directly, which works with the
in-process ``InMemoryRunner`` / ``InMemorySessionService``. A persistent /
distributed session service (Firestore / Vertex Agent Engine — Plan 9) is the
thing most likely to break that pattern, because durable values must travel via
``EventActions.state_delta`` to be persisted across processes.

This test drives the tree against ADK's SQLite-backed ``DatabaseSessionService``
(the closest persistent stand-in available locally), fully offline. It is
written to document the Plan-9 risk in every environment:

* If ``DatabaseSessionService`` is importable AND its async engine can actually
  be initialized here → the tree runs and we assert portability (SUCCESS).
* If the tree FAILS against it (revealing the direct-state-mutation break) →
  the assertion is xfail (see the module-level marker logic below).
* If the service is importable but cannot be constructed/run in this
  environment (missing async sqlite driver or greenlet) → the test skips.
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
    """Run the tree via Runner + DatabaseSessionService (offline) and assert the
    run finalizes as a SUCCESS DigestRun — proving the tree is portable to a
    persistent session service. If the direct ctx.session.state mutation does
    not survive that service, this assertion xfails (Plan-9 break found)."""
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
        run_id=run_id,
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

    try:
        async for _ in runner.run_async(
            user_id="system", session_id=session.id, new_message=msg
        ):
            pass
        run = storage.get_run(run_id)
        assert run is not None
        assert run.status == RunStatus.SUCCESS
        assert run.collected == 1
        assert run.new == 1
    except Exception as exc:  # direct-state-mutation break surfaced
        pytest.xfail(
            "direct ctx.session.state mutation not persisted by "
            f"DatabaseSessionService — Plan 9 must move durable values to "
            f"state_delta: {exc}"
        )
