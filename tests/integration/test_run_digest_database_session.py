"""End-to-end: run_digest on the real production runtime path (database session
backend), proving the live code (not a hand-built Runner) works persistently and
creates the local sessions DB."""
from pathlib import Path

from app.core.config import Settings
from app.core.domain import Category, RawItem, RunStatus, SourceType
from app.llm.schema import ItemEnrichment, ProcessingResult
from app.runner import run_digest


def _settings(tmp_path) -> Settings:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text(
        "sources:\n  - id: feed1\n    type: rss\n    name: FakeFeed\n"
        "    url: https://demo/feed\n    category_hint: ai_tech\n    enabled: true\n",
        encoding="utf-8",
    )
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    return Settings(
        _env_file=None,
        session_backend="database",  # init kwarg beats the conftest memory default
        sqlite_path=str(tmp_path / "catchup.db"),
        config_dir=str(cfg),
        output_dir=str(tmp_path / "out"),
    )


def test_run_digest_completes_on_database_session(tmp_path, monkeypatch):
    def fake_collect(source, s, storage=None):
        if source.type == SourceType.RSS:
            return [RawItem(source_id="feed1", source_type=SourceType.RSS,
                            source_name="FakeFeed", url="https://x/1", title="T",
                            category_hint=Category.AI_TECH)]
        return []

    def fake_enrich(items, settings):
        return ProcessingResult(items=[
            ItemEnrichment(id=i.id, category=Category.AI_TECH, importance_score=0.8,
                           summary_en="S.", summary_ar="ملخص.", entities=[],
                           sentiment="neutral") for i in items])

    # build_pipeline binds the module-level _collect inside app.pipeline.agents
    # (imported from app.runner). Patch it THERE, not on app.runner, or the fake
    # is ignored once agents.py is already imported.
    monkeypatch.setattr("app.pipeline.agents._collect", fake_collect)
    settings = _settings(tmp_path)

    run = run_digest(
        settings,
        processor=lambda items: fake_enrich(items, settings),
        narrator=lambda items: "Narrative.",
        critic=lambda items: [],
    )

    assert run.status == RunStatus.SUCCESS
    assert run.collected == 1
    assert run.new == 1
    # The persistent session DB landed next to the app DB.
    assert (Path(settings.sqlite_path).parent / "sessions.db").exists()
