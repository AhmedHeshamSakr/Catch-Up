"""Integration tests for the faithfulness guardrail wired into run_digest — B4.
Fully offline: processor and critic are injected fakes; no model, no quota.
"""
from __future__ import annotations

from pathlib import Path

from app import runner
from app.core.config import Settings
from app.core.domain import Category, RawItem, RunStatus, SourceType
from app.llm.schema import ItemEnrichment, ProcessingResult
from app.pipeline.eval_schema import FaithfulnessVerdict


def _raw(url, title):
    return RawItem(
        source_id="techcrunch", source_type=SourceType.RSS,
        source_name="TC", url=url, title=title, category_hint=Category.AI_TECH,
    )


def _settings(tmp_path, **extra):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text(
        "sources:\n  - id: techcrunch\n    type: rss\n    name: TC\n"
        "    url: https://demo/feed\n    category_hint: ai_tech\n    enabled: true\n",
        encoding="utf-8",
    )
    (cfg / "watchlist.yaml").write_text("entities: []\nkeywords: []\n", encoding="utf-8")
    kwargs = {
        "sqlite_path": str(tmp_path / "db.sqlite"),
        "config_dir": str(cfg),
        "output_dir": str(tmp_path / "out"),
        "critic_enabled": True,
        "critic_action": "downrank",
    }
    kwargs.update(extra)
    return Settings(**kwargs)


def _fake_processor_high(items):
    """Enrich all items as HIGH importance (score=0.9)."""
    return ProcessingResult(items=[
        ItemEnrichment(
            id=it.id, category=Category.AI_TECH, importance_score=0.9,
            summary_en="A detailed summary.", summary_ar="ملخص.",
            entities=[], sentiment="neutral",
        )
        for it in items
    ])


def test_unfaithful_item_is_flagged_excluded_from_render(tmp_path, monkeypatch):
    """HIGH item with faithful=False verdict → status==flagged, excluded from MD output, run.flagged==1."""
    settings = _settings(tmp_path)
    monkeypatch.setattr(runner.rss, "collect",
                        lambda s: [_raw("https://x.com/1", "OpenAI launches new model")])

    # Capture the item id after processing so we can build the verdict
    captured_id: list[str] = []

    def fake_processor(items):
        captured_id.append(items[0].id)
        return _fake_processor_high(items)

    def fake_critic(items):
        assert len(items) >= 1
        return [FaithfulnessVerdict(
            item_id=items[0].id,
            faithful=False,
            issues=["hallucinated statistic"],
            suggested_summary_en=None,
        )]

    run = runner.run_digest(
        settings=settings,
        processor=fake_processor,
        narrator=lambda items: "Today's digest.",
        critic=fake_critic,
    )

    assert run.status in (RunStatus.SUCCESS, RunStatus.PARTIAL)
    assert run.flagged == 1

    # Verify item was saved as flagged in storage (flagged items need the flag).
    from app.adapters.storage.sqlite_backend import SqliteBackend
    items = SqliteBackend(settings.sqlite_path).get_items_for_run(
        run.run_id, include_flagged=True
    )
    assert items and items[0].status == "flagged"

    # Verify flagged item is excluded from rendered markdown
    md = Path(run.outputs["md"]).read_text(encoding="utf-8")
    assert "A detailed summary." not in md


def test_faithful_verdict_item_untouched(tmp_path, monkeypatch):
    """HIGH item with faithful=True verdict → item untouched, not flagged."""
    settings = _settings(tmp_path)
    monkeypatch.setattr(runner.rss, "collect",
                        lambda s: [_raw("https://x.com/2", "OpenAI launches new model")])

    def fake_critic(items):
        return [FaithfulnessVerdict(
            item_id=items[0].id,
            faithful=True,
            issues=[],
        )]

    run = runner.run_digest(
        settings=settings,
        processor=_fake_processor_high,
        narrator=lambda items: "Digest.",
        critic=fake_critic,
    )

    assert run.status == RunStatus.SUCCESS
    assert run.flagged == 0

    from app.adapters.storage.sqlite_backend import SqliteBackend
    items = SqliteBackend(settings.sqlite_path).get_items_for_run(run.run_id)
    assert items and items[0].status == "processed"

    # Item appears in rendered output
    md = Path(run.outputs["md"]).read_text(encoding="utf-8")
    assert "A detailed summary." in md


def test_critic_failure_fails_closed_by_default(tmp_path, monkeypatch):
    """Default fail-closed: a critic exception flags + redacts the selected HIGH items."""
    from app.pipeline.critic import WITHHELD_NOTICE

    settings = _settings(tmp_path)  # default critic_fail_mode == "closed"
    monkeypatch.setattr(runner.rss, "collect",
                        lambda s: [_raw("https://x.com/closed", "OpenAI launches new model")])

    def boom_critic(items):
        raise RuntimeError("critic quota exhausted")

    run = runner.run_digest(
        settings=settings,
        processor=_fake_processor_high,
        narrator=lambda items: "Digest.",
        critic=boom_critic,
    )

    # Run is PARTIAL (critic failed) and the error is marked degraded.
    assert run.status == RunStatus.PARTIAL
    critic_errs = [e for e in run.source_errors if e.get("stage") == "critic"]
    assert critic_errs and critic_errs[0].get("degraded") is True
    assert run.flagged == 1

    from app.adapters.storage.sqlite_backend import SqliteBackend
    items = SqliteBackend(settings.sqlite_path).get_items_for_run(
        run.run_id, include_flagged=True
    )
    assert items and items[0].status == "flagged"
    assert items[0].summary_en == WITHHELD_NOTICE
    assert items[0].summary_ar is None


def test_critic_failure_fails_open_when_configured(tmp_path, monkeypatch):
    """critic_fail_mode='open' keeps legacy pass-through: items unflagged."""
    settings = _settings(tmp_path, critic_fail_mode="open")
    monkeypatch.setattr(runner.rss, "collect",
                        lambda s: [_raw("https://x.com/open", "OpenAI launches new model")])

    def boom_critic(items):
        raise RuntimeError("critic quota exhausted")

    run = runner.run_digest(
        settings=settings,
        processor=_fake_processor_high,
        narrator=lambda items: "Digest.",
        critic=boom_critic,
    )

    assert run.status == RunStatus.PARTIAL
    assert run.flagged == 0

    from app.adapters.storage.sqlite_backend import SqliteBackend
    items = SqliteBackend(settings.sqlite_path).get_items_for_run(run.run_id)
    assert items and items[0].status == "processed"
    assert items[0].summary_en == "A detailed summary."


def test_critic_raises_source_error_run_is_not_failed(tmp_path, monkeypatch):
    """When critic raises, run.source_errors has stage==critic; run is PARTIAL/SUCCESS not FAILED; items still saved.

    Uses fail-open so the saved item keeps its processed status (the fail-closed
    path is covered by test_critic_failure_fails_closed_by_default).
    """
    settings = _settings(tmp_path, critic_fail_mode="open")
    monkeypatch.setattr(runner.rss, "collect",
                        lambda s: [_raw("https://x.com/3", "OpenAI launches new model")])

    def boom_critic(items):
        raise RuntimeError("critic quota exhausted")

    run = runner.run_digest(
        settings=settings,
        processor=_fake_processor_high,
        narrator=lambda items: "Digest.",
        critic=boom_critic,
    )

    # Run should be PARTIAL (processing succeeded, critic failed) not FAILED
    assert run.status in (RunStatus.SUCCESS, RunStatus.PARTIAL)
    assert any(e.get("stage") == "critic" for e in run.source_errors)

    # Items should still be saved
    from app.adapters.storage.sqlite_backend import SqliteBackend
    items = SqliteBackend(settings.sqlite_path).get_items_for_run(run.run_id)
    assert items and items[0].status == "processed"
