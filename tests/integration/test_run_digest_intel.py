from app import runner
from app.core.config import Settings
from app.core.domain import Category, RawItem, RunStatus, SourceType
from app.pipeline.schema import ItemEnrichment, ProcessingResult


def _raw(url, title):
    return RawItem(source_id="techcrunch", source_type=SourceType.RSS,
                   source_name="TC", url=url, title=title, category_hint=Category.AI_TECH)


def _settings(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text(
        "sources:\n  - id: techcrunch\n    type: rss\n    name: TC\n"
        "    url: https://demo/feed\n    category_hint: ai_tech\n    enabled: true\n",
        encoding="utf-8")
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    return Settings(sqlite_path=str(tmp_path / "db.sqlite"),
                    config_dir=str(cfg), output_dir=str(tmp_path / "out"))


def test_run_digest_enriches_and_writes_narrative(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr(runner.rss, "collect",
                        lambda s: [_raw("https://x.com/1", "OpenAI launches new model")])

    def fake_processor(items):
        return ProcessingResult(items=[ItemEnrichment(
            id=items[0].id, category=Category.AI_TECH, importance_score=0.9,
            summary_en="A summary.", summary_ar="ملخص.", entities=[], sentiment="neutral")])

    run = runner.run_digest(settings=settings, processor=fake_processor,
                            narrator=lambda items: "What matters most today.")

    assert run.status == RunStatus.SUCCESS
    assert run.new == 1
    assert run.high_importance == 1
    assert run.narrative == "What matters most today."
    from pathlib import Path
    md = Path(run.outputs["md"]).read_text(encoding="utf-8")
    assert "A summary." in md and "What matters most" in md


def test_run_digest_degrades_when_processing_fails(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setattr(runner.rss, "collect",
                        lambda s: [_raw("https://x.com/1", "headline")])

    def boom(items):
        raise RuntimeError("LLM quota exhausted")

    run = runner.run_digest(settings=settings, processor=boom, narrator=lambda i: "x")
    # Collection still succeeded; processing degraded → run not FAILED, items stored raw, error logged
    assert run.status in (RunStatus.SUCCESS, RunStatus.PARTIAL)
    assert any(e.get("stage") == "processing" for e in run.source_errors)
    from app.adapters.storage.sqlite_backend import SqliteBackend
    items = SqliteBackend(settings.sqlite_path).get_items_for_run(run.run_id)
    assert items and items[0].status == "raw"
