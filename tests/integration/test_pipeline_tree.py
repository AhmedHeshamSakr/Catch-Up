"""Integration test: drive NewsCatchUpPipeline via InMemoryRunner directly.

Fully offline — no LLM calls, all collaborators injected as fakes.
"""
from __future__ import annotations

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.core.config import Settings
from app.core.domain import Category, RawItem, RunStatus, SourceType
from app.llm.schema import ItemEnrichment, ProcessingResult
from app.pipeline.agents import build_pipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _raw(url: str, title: str, source_id: str = "feed1", source_type: SourceType = SourceType.RSS) -> RawItem:
    return RawItem(
        source_id=source_id,
        source_type=source_type,
        source_name="FakeFeed",
        url=url,
        title=title,
        category_hint=Category.AI_TECH,
    )


def _settings(tmp_path):
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


async def _drive(tree, run_id: str) -> None:
    runner = InMemoryRunner(agent=tree, app_name="catchup")
    session = await runner.session_service.create_session(
        app_name="catchup", user_id="system", state={"run_id": run_id}
    )
    msg = types.Content(role="user", parts=[types.Part.from_text(text="run")])
    async for _ in runner.run_async(user_id="system", session_id=session.id, new_message=msg):
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_tree_success(tmp_path):
    """Happy path: one RSS item → tree runs → run finalized SUCCESS, outputs written."""
    from app.runner import build_storage

    settings = _settings(tmp_path)
    storage = build_storage(settings)

    item_returned: list[RawItem] = [_raw("https://x.com/1", "ADK tree works")]

    def fake_collect(source, s, st=None):
        if source.type == SourceType.RSS:
            return list(item_returned)
        return []

    def fake_processor(items):
        return ProcessingResult(items=[
            ItemEnrichment(
                id=items[0].id, category=Category.AI_TECH, importance_score=0.8,
                summary_en="Tree summary.", summary_ar="ملخص.", entities=[], sentiment="neutral",
            )
            for items in [items] if items
        ])

    run_id = "testrun000001"
    tree = build_pipeline(
        settings, storage,
        collect_fn=fake_collect,
        processor=fake_processor,
        narrator=lambda items: "Narrative text.",
        critic=lambda items: [],
    )

    await _drive(tree, run_id)

    run = storage.get_run(run_id)
    assert run is not None
    assert run.status == RunStatus.SUCCESS
    assert run.collected == 1
    assert run.new == 1

    saved_items = storage.get_items_for_run(run_id)
    assert len(saved_items) == 1

    from pathlib import Path
    # Lock the exact output-key set: the frontend (output-links.tsx) reads these
    # literal keys, so a rename here silently breaks the UI badges.
    assert set(run.outputs) == {"md", "xlsx", "html"}
    assert Path(run.outputs["md"]).exists()
    assert Path(run.outputs["xlsx"]).exists()
    assert Path(run.outputs["html"]).exists()


@pytest.mark.asyncio
async def test_pipeline_tree_partial_on_collect_error(tmp_path):
    """When collect_fn raises for one source → run finalizes PARTIAL, source_errors populated."""
    from app.runner import build_storage

    settings = _settings(tmp_path)
    storage = build_storage(settings)

    def boom_collect(source, s, st=None):
        raise RuntimeError("feed unreachable")

    run_id = "testrun000002"
    tree = build_pipeline(
        settings, storage,
        collect_fn=boom_collect,
        processor=lambda items: ProcessingResult(items=[]),
        narrator=lambda items: "",
        critic=lambda items: [],
    )

    await _drive(tree, run_id)

    run = storage.get_run(run_id)
    assert run is not None
    assert run.status == RunStatus.PARTIAL
    assert run.collected == 0
    assert len(run.source_errors) >= 1
    assert any("feed unreachable" in e.get("error", "") for e in run.source_errors)
