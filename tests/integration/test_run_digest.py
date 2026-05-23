from app.adapters.storage.sqlite_backend import SqliteBackend
from app.core.config import Settings
from app.core.domain import Category, RawItem, RunStatus, SourceType
from app import runner


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

    run = runner.run_digest(settings=settings)

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
    run = runner.run_digest(settings=settings)

    assert run.status == RunStatus.PARTIAL
    assert run.collected == 0
    assert len(run.source_errors) == 1
    assert run.source_errors[0]["source_id"] == "techcrunch"
