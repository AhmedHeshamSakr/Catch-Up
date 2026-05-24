import asyncio

import pytest

from app import runner
from app.adapters.storage.sqlite_backend import SqliteBackend
from app.core.config import Settings
from app.core.domain import Category, RawItem, RunStatus, SourceType
from app.llm.schema import ProcessingResult


def _raw(url: str, title: str) -> RawItem:
    return RawItem(
        source_id="techcrunch", source_type=SourceType.RSS, source_name="TechCrunch",
        url=url, title=title, category_hint=Category.AI_TECH,
    )


def test_run_digest_end_to_end(tmp_path, monkeypatch):
    # Config dir with a single enabled RSS source
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "sources.yaml").write_text(
        "sources:\n"
        "  - id: techcrunch\n    type: rss\n    name: TechCrunch\n"
        "    url: https://demo/feed\n    category_hint: ai_tech\n    enabled: true\n",
        encoding="utf-8",
    )
    settings = Settings(
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(config_dir),
        output_dir=str(tmp_path / "out"),
    )

    monkeypatch.setattr(
        runner.rss, "collect",
        lambda source: [_raw("https://x.com/1", "A"), _raw("https://x.com/2", "B")],
    )

    run = runner.run_digest(
        settings=settings,
        processor=lambda items: ProcessingResult(items=[]),
        narrator=lambda items: "",
        critic=lambda items: [],
    )

    assert run.status == RunStatus.SUCCESS
    assert run.collected == 2
    assert run.new == 2
    assert run.outputs["md"].endswith(f"digest-{run.run_id}.md")

    from pathlib import Path
    assert Path(run.outputs["md"]).exists()

    storage = SqliteBackend(settings.sqlite_path)
    assert len(storage.get_items_for_run(run.run_id)) == 2
    assert storage.get_run(run.run_id).status == RunStatus.SUCCESS


def test_run_digest_isolates_source_failure(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "sources.yaml").write_text(
        "sources:\n"
        "  - id: techcrunch\n    type: rss\n    name: TechCrunch\n"
        "    url: https://demo/feed\n    category_hint: ai_tech\n    enabled: true\n",
        encoding="utf-8",
    )
    settings = Settings(
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(config_dir),
        output_dir=str(tmp_path / "out"),
    )

    def boom(source):
        raise RuntimeError("feed down")

    monkeypatch.setattr(runner.rss, "collect", boom)
    run = runner.run_digest(
        settings=settings,
        processor=lambda items: ProcessingResult(items=[]),
        narrator=lambda items: "",
        critic=lambda items: [],
    )

    assert run.status == RunStatus.PARTIAL
    assert run.collected == 0
    assert len(run.source_errors) == 1
    assert run.source_errors[0]["source_id"] == "techcrunch"


def test_run_digest_failed_run_finalized_on_unexpected_error(tmp_path, monkeypatch):
    """Unexpected errors (outside per-source isolation) must finalize the run as FAILED."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "sources.yaml").write_text(
        "sources:\n"
        "  - id: techcrunch\n    type: rss\n    name: TechCrunch\n"
        "    url: https://demo/feed\n    category_hint: ai_tech\n    enabled: true\n",
        encoding="utf-8",
    )
    settings = Settings(
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(config_dir),
        output_dir=str(tmp_path / "out"),
    )

    # Patch rss.collect to return items (passes per-source stage)
    monkeypatch.setattr(
        runner.rss, "collect",
        lambda source: [_raw("https://x.com/1", "A")],
    )
    # Patch write_markdown to raise an unexpected error AFTER create_run
    monkeypatch.setattr(
        runner.markdown, "write_markdown",
        lambda run, items, output_dir: (_ for _ in ()).throw(RuntimeError("render boom")),
    )

    with pytest.raises(RuntimeError, match="render boom"):
        runner.run_digest(
            settings=settings,
            processor=lambda items: ProcessingResult(items=[]),
            narrator=lambda items: "",
            critic=lambda items: [],
        )

    # The run must exist in storage and be marked FAILED
    storage = SqliteBackend(settings.sqlite_path)
    storage.init_schema()
    # Fetch all runs — we need the one that was created
    with storage._conn() as conn:
        rows = conn.execute("SELECT data FROM digest_runs").fetchall()
    assert len(rows) == 1
    from app.core.domain import DigestRun
    saved_run = DigestRun.model_validate_json(rows[0]["data"])
    assert saved_run.status == RunStatus.FAILED
    assert saved_run.finished_at is not None
    assert any("render boom" in e.get("error", "") for e in saved_run.source_errors)


def test_run_digest_times_out_finalizes_failed(tmp_path, monkeypatch):
    """With a tiny run_timeout and a deliberately slow tree, the run must
    finalize FAILED and raise (TimeoutError) rather than hang forever."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "sources.yaml").write_text(
        "sources:\n"
        "  - id: techcrunch\n    type: rss\n    name: TechCrunch\n"
        "    url: https://demo/feed\n    category_hint: ai_tech\n    enabled: true\n",
        encoding="utf-8",
    )
    settings = Settings(
        sqlite_path=str(tmp_path / "db.sqlite"),
        config_dir=str(config_dir),
        output_dir=str(tmp_path / "out"),
        run_timeout=0.05,
    )

    storage = runner.build_storage(settings)

    # Slow tree: create the run (so the FAILED path can find+finalize it),
    # then sleep well past run_timeout so asyncio.wait_for fires.
    async def slow_run_tree(tree, run_id):
        from app.core.domain import DigestRun
        storage.create_run(DigestRun(run_id=run_id))
        await asyncio.sleep(5.0)

    monkeypatch.setattr(runner, "_run_tree", slow_run_tree)

    with pytest.raises(asyncio.TimeoutError):
        runner.run_digest(
            settings=settings,
            storage=storage,
            processor=lambda items: ProcessingResult(items=[]),
            narrator=lambda items: "",
            critic=lambda items: [],
        )

    runs = []
    fresh = SqliteBackend(settings.sqlite_path)
    fresh.init_schema()
    with fresh._conn() as conn:
        rows = conn.execute("SELECT data FROM digest_runs").fetchall()
    from app.core.domain import DigestRun
    runs = [DigestRun.model_validate_json(r["data"]) for r in rows]
    assert len(runs) == 1
    assert runs[0].status == RunStatus.FAILED
    assert runs[0].finished_at is not None
