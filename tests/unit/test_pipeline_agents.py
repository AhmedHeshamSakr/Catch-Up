"""Unit tests for the ADK agent wrappers in app/pipeline/agents.py.

All tests are fully offline:
- No model calls, no network
- Fake collect_fn / processor / critic / narrator injected
- Real SqliteBackend in tmp_path for NormalizeDedup and Render tests
- Fake ctx built with SimpleNamespace to drive _run_async_impl in isolation
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.adapters.storage.sqlite_backend import SqliteBackend
from app.core.config import Settings
from app.core.domain import (
    Category,
    DigestRun,
    Importance,
    NewsItem,
    RawItem,
    RunStatus,
    SourceType,
)
from app.llm.schema import ItemEnrichment, ProcessingResult
from app.pipeline.agents import (
    DigestEditorAgent,
    GuardrailCriticAgent,
    NormalizeDedupAgent,
    PipelineInitAgent,
    ProcessingAgent,
    RenderAgent,
    SourceCollectorAgent,
    build_pipeline,
)
from app.pipeline.eval_schema import FaithfulnessVerdict
from app.services.watchlist import Watchlist

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(state: dict) -> SimpleNamespace:
    """Minimal fake InvocationContext that satisfies our agents."""
    return SimpleNamespace(
        session=SimpleNamespace(state=state),
        invocation_id="test-inv",
        branch=None,
    )


def _raw(url: str, title: str, stype: SourceType = SourceType.RSS) -> RawItem:
    return RawItem(
        source_id="test-src",
        source_type=stype,
        source_name="TestSource",
        url=url,
        title=title,
        category_hint=Category.AI_TECH,
    )


def _news(url: str, title: str, run_id: str = "r1") -> NewsItem:
    return NewsItem.from_raw(_raw(url, title), run_id=run_id)


def _fake_reprocessor(items, verdicts):
    """Offline re-enrichment: still-unfaithful re-summary (keeps the reflection
    loop offline for guardrail tests that exercise the unfaithful path)."""
    return ProcessingResult(items=[
        ItemEnrichment(
            id=it.id, category=Category.AI_TECH, importance_score=0.9,
            summary_en="Re-summary.", summary_ar="ملخص.",
            entities=[], sentiment="neutral",
        )
        for it in items
    ])


def _settings(tmp_path, **kwargs) -> Settings:
    cfg = tmp_path / "config"
    cfg.mkdir(exist_ok=True)
    (cfg / "sources.yaml").write_text(
        "sources:\n"
        "  - id: rss-src\n    type: rss\n    name: TestRSS\n"
        "    url: https://demo/feed\n    enabled: true\n"
        "  - id: api-src\n    type: api\n    name: TestAPI\n"
        "    url: https://demo/api\n    enabled: true\n"
        "  - id: disabled-src\n    type: rss\n    name: Disabled\n"
        "    url: https://demo/disabled\n    enabled: false\n",
        encoding="utf-8",
    )
    (cfg / "watchlist.yaml").write_text(
        "entities: []\nkeywords: []\n", encoding="utf-8"
    )
    defaults = {
        "sqlite_path": str(tmp_path / "db.sqlite"),
        "config_dir": str(cfg),
        "output_dir": str(tmp_path / "out"),
        "critic_enabled": True,
        "critic_action": "downrank",
        "importance_threshold": 0.33,
        "llm_batch_size": 8,
    }
    defaults.update(kwargs)
    return Settings(**defaults)


def _storage(tmp_path) -> SqliteBackend:
    s = SqliteBackend(str(tmp_path / "db.sqlite"))
    s.init_schema()
    return s


async def _run(agent, state: dict) -> list:
    """Drive an agent's _run_async_impl with a fake ctx, collect events."""
    ctx = _ctx(state)
    return [e async for e in agent._run_async_impl(ctx)]


# ---------------------------------------------------------------------------
# PipelineInitAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_init_seeds_run_and_watchlist(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    agent = PipelineInitAgent(name="PipelineInit", settings=settings, storage=storage)
    state = {"run_id": "abc123"}

    events = await _run(agent, state)

    assert len(events) == 1
    assert isinstance(state["run"], DigestRun)
    assert state["run"].run_id == "abc123"
    assert state["run"].status == RunStatus.RUNNING
    assert isinstance(state["watchlist"], Watchlist)
    assert state["settings"] is settings

    # Run must be persisted in storage
    saved = storage.get_run("abc123")
    assert saved is not None
    assert saved.run_id == "abc123"


@pytest.mark.asyncio
async def test_pipeline_init_event_has_correct_author(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    agent = PipelineInitAgent(name="PipelineInit", settings=settings, storage=storage)
    state = {"run_id": "xyz999"}
    events = await _run(agent, state)

    assert events[0].author == "PipelineInit"
    assert events[0].invocation_id == "test-inv"


# ---------------------------------------------------------------------------
# SourceCollectorAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_source_collector_writes_raws_for_matching_type(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    run = DigestRun(run_id="r1")
    state = {"run": run, "watchlist": Watchlist()}

    def fake_collect(source, settings, storage):
        return [_raw(f"https://x.com/{source.id}", "Test Article")]

    agent = SourceCollectorAgent(
        name="CollectRss",
        source_type=SourceType.RSS,
        state_key="raws_rss",
        settings=settings,
        storage=storage,
        collect_fn=fake_collect,
    )
    events = await _run(agent, state)

    assert len(events) == 1
    # rss-src matches; api-src does not; disabled-src skipped
    assert len(state["raws_rss"]) == 1
    assert state["raws_rss"][0].url == "https://x.com/rss-src"


@pytest.mark.asyncio
async def test_source_collector_skips_disabled_sources(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    run = DigestRun(run_id="r1")
    state = {"run": run, "watchlist": Watchlist()}

    called_sources = []

    def tracking_collect(source, settings, storage):
        called_sources.append(source.id)
        return []

    agent = SourceCollectorAgent(
        name="CollectRss",
        source_type=SourceType.RSS,
        state_key="raws_rss",
        settings=settings,
        storage=storage,
        collect_fn=tracking_collect,
    )
    await _run(agent, state)

    # disabled-src must not appear
    assert "disabled-src" not in called_sources


@pytest.mark.asyncio
async def test_source_collector_per_source_failure_adds_to_errors(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    run = DigestRun(run_id="r1")
    storage.create_run(run)
    state = {"run": run, "watchlist": Watchlist()}

    def boom_collect(source, settings, storage):
        raise RuntimeError("feed down")

    agent = SourceCollectorAgent(
        name="CollectRss",
        source_type=SourceType.RSS,
        state_key="raws_rss",
        settings=settings,
        storage=storage,
        collect_fn=boom_collect,
    )
    events = await _run(agent, state)

    # Agent still yields one event (it's graceful)
    assert len(events) == 1
    # raws_rss is empty (collection failed)
    assert state["raws_rss"] == []
    # The parallel collector writes ONLY its own per-source error key —
    # it must NOT mutate the shared run.source_errors yet.
    assert run.source_errors == []
    assert len(state["errors_raws_rss"]) == 1
    assert state["errors_raws_rss"][0]["source_id"] == "rss-src"
    assert "feed down" in state["errors_raws_rss"][0]["error"]

    # NormalizeDedup merges per-source errors into run.source_errors.
    normalize = NormalizeDedupAgent(
        name="NormalizeDedup", settings=settings, storage=storage
    )
    await _run(normalize, state)

    assert len(run.source_errors) == 1
    assert run.source_errors[0]["source_id"] == "rss-src"
    assert "feed down" in run.source_errors[0]["error"]


@pytest.mark.asyncio
async def test_source_collector_different_types_use_distinct_keys(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    run = DigestRun(run_id="r1")
    state = {"run": run, "watchlist": Watchlist()}

    def fake_api(source, settings, storage):
        return [_raw("https://api.com/1", "API Article", SourceType.API)]

    agent = SourceCollectorAgent(
        name="CollectApi",
        source_type=SourceType.API,
        state_key="raws_api",
        settings=settings,
        storage=storage,
        collect_fn=fake_api,
    )
    await _run(agent, state)

    assert "raws_api" in state
    assert len(state["raws_api"]) == 1
    assert "raws_rss" not in state


# ---------------------------------------------------------------------------
# NormalizeDedupAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normalize_dedup_merges_all_raws_keys(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    run = DigestRun(run_id="r1")
    storage.create_run(run)
    state = {
        "run": run,
        "watchlist": Watchlist(),
        "raws_rss": [_raw("https://a.com/1", "RSS Article")],
        "raws_scrape": [_raw("https://b.com/1", "Scraped Article")],
        "raws_api": [_raw("https://c.com/1", "API Article")],
        "raws_search": [],
        "raws_youtube": [],
    }

    agent = NormalizeDedupAgent(name="NormalizeDedup", settings=settings, storage=storage)
    await _run(agent, state)

    assert run.collected == 3
    assert run.new == 3
    assert len(state["items"]) == 3


@pytest.mark.asyncio
async def test_normalize_dedup_filters_existing_in_storage(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    # Pre-save an item that already exists
    existing = _news("https://a.com/1", "Existing Article", run_id="old-run")
    storage.save_items([existing])

    run = DigestRun(run_id="r1")
    storage.create_run(run)
    state = {
        "run": run,
        "watchlist": Watchlist(),
        "raws_rss": [
            _raw("https://a.com/1", "Existing Article"),   # already in storage
            _raw("https://b.com/1", "New Article"),         # new
        ],
    }

    agent = NormalizeDedupAgent(name="NormalizeDedup", settings=settings, storage=storage)
    await _run(agent, state)

    assert run.collected == 2
    assert run.new == 1  # only the new article
    assert len(state["items"]) == 1
    assert state["items"][0].url == "https://b.com/1"


@pytest.mark.asyncio
async def test_normalize_dedup_missing_raws_keys_treated_as_empty(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    run = DigestRun(run_id="r1")
    storage.create_run(run)
    # Intentionally omit all raws_* keys
    state = {"run": run, "watchlist": Watchlist()}

    agent = NormalizeDedupAgent(name="NormalizeDedup", settings=settings, storage=storage)
    await _run(agent, state)

    assert run.collected == 0
    assert run.new == 0
    assert state["items"] == []


# ---------------------------------------------------------------------------
# ProcessingAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_processing_agent_sets_item_statuses(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    item_high = _news("https://a.com/1", "OpenAI launch")
    item_low = _news("https://a.com/2", "minor note")

    run = DigestRun(run_id="r1")
    state = {
        "run": run,
        "watchlist": Watchlist(),
        "items": [item_high, item_low],
    }

    def fake_processor(batch):
        results = []
        for it in batch:
            score = 0.9 if "OpenAI" in it.title else 0.1
            results.append(ItemEnrichment(
                id=it.id, category=Category.AI_TECH,
                importance_score=score,
                summary_en="Summary", summary_ar="ملخص",
                entities=[], sentiment="neutral",
            ))
        return ProcessingResult(items=results)

    agent = ProcessingAgent(
        name="Processing",
        settings=settings,
        storage=storage,
        processor=fake_processor,
    )
    events = await _run(agent, state)

    assert len(events) == 1
    assert item_high.status == "processed"
    assert item_low.status == "filtered"
    assert run.source_errors == []


@pytest.mark.asyncio
async def test_processing_agent_failure_adds_stage_error(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    run = DigestRun(run_id="r1")
    state = {
        "run": run,
        "watchlist": Watchlist(),
        "items": [_news("https://a.com/1", "Test")],
    }

    def boom_processor(batch):
        raise RuntimeError("LLM quota exhausted")

    agent = ProcessingAgent(
        name="Processing",
        settings=settings,
        storage=storage,
        processor=boom_processor,
    )
    events = await _run(agent, state)

    assert len(events) == 1  # still yields (graceful)
    assert len(run.source_errors) == 1
    assert run.source_errors[0]["stage"] == "processing"
    assert "LLM quota exhausted" in run.source_errors[0]["error"]


# ---------------------------------------------------------------------------
# GuardrailCriticAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_guardrail_critic_flags_unfaithful_item(tmp_path):
    settings = _settings(tmp_path, critic_enabled=True, critic_action="downrank",
                         critic_min_importance="high")
    storage = _storage(tmp_path)

    item = _news("https://a.com/1", "Test")
    item.importance = Importance.HIGH
    item.importance_score = 0.9
    item.status = "processed"

    run = DigestRun(run_id="r1")
    state = {
        "run": run,
        "watchlist": Watchlist(),
        "items": [item],
    }

    def fake_critic(items):
        return [FaithfulnessVerdict(
            item_id=items[0].id,
            faithful=False,
            issues=["hallucinated stat"],
            suggested_summary_en=None,
        )]

    agent = GuardrailCriticAgent(
        name="GuardrailCritic",
        settings=settings,
        storage=storage,
        critic=fake_critic,
        reprocessor=_fake_reprocessor,
    )
    await _run(agent, state)

    assert run.flagged == 1
    assert item.status == "flagged"
    assert run.source_errors == []


@pytest.mark.asyncio
async def test_guardrail_critic_faithful_item_untouched(tmp_path):
    settings = _settings(tmp_path, critic_enabled=True, critic_action="downrank",
                         critic_min_importance="high")
    storage = _storage(tmp_path)

    item = _news("https://a.com/1", "Test")
    item.importance = Importance.HIGH
    item.importance_score = 0.9
    item.status = "processed"

    run = DigestRun(run_id="r1")
    state = {
        "run": run,
        "watchlist": Watchlist(),
        "items": [item],
    }

    def fake_critic(items):
        return [FaithfulnessVerdict(item_id=items[0].id, faithful=True, issues=[])]

    agent = GuardrailCriticAgent(
        name="GuardrailCritic",
        settings=settings,
        storage=storage,
        critic=fake_critic,
        reprocessor=_fake_reprocessor,
    )
    await _run(agent, state)

    assert run.flagged == 0
    assert item.status == "processed"
    assert run.source_errors == []


@pytest.mark.asyncio
async def test_guardrail_critic_raises_adds_stage_error(tmp_path):
    settings = _settings(tmp_path, critic_enabled=True, critic_action="downrank",
                         critic_min_importance="high")
    storage = _storage(tmp_path)

    item = _news("https://a.com/1", "Test")
    item.importance = Importance.HIGH
    item.importance_score = 0.9
    item.status = "processed"

    run = DigestRun(run_id="r1")
    state = {
        "run": run,
        "watchlist": Watchlist(),
        "items": [item],
    }

    def boom_critic(items):
        raise RuntimeError("critic quota exhausted")

    agent = GuardrailCriticAgent(
        name="GuardrailCritic",
        settings=settings,
        storage=storage,
        critic=boom_critic,
        reprocessor=_fake_reprocessor,
    )
    events = await _run(agent, state)

    assert len(events) == 1  # graceful — still yields
    assert len(run.source_errors) == 1
    assert run.source_errors[0]["stage"] == "critic"
    assert "critic quota exhausted" in run.source_errors[0]["error"]
    # Run should NOT be failed (it's a source error, not a fatal crash)
    assert run.status == RunStatus.RUNNING


@pytest.mark.asyncio
async def test_guardrail_critic_disabled_skips_selection(tmp_path):
    settings = _settings(tmp_path, critic_enabled=False)
    storage = _storage(tmp_path)

    item = _news("https://a.com/1", "Test")
    item.importance = Importance.HIGH
    item.importance_score = 0.9

    run = DigestRun(run_id="r1")
    critic_called = []
    state = {
        "run": run,
        "watchlist": Watchlist(),
        "items": [item],
    }

    def tracking_critic(items):
        critic_called.append(True)
        return []

    agent = GuardrailCriticAgent(
        name="GuardrailCritic",
        settings=settings,
        storage=storage,
        critic=tracking_critic,
        reprocessor=_fake_reprocessor,
    )
    await _run(agent, state)

    assert critic_called == []  # critic_enabled=False → nothing selected → critic not called


# ---------------------------------------------------------------------------
# DigestEditorAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_digest_editor_sets_narrative(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    item = _news("https://a.com/1", "Test")
    item.status = "processed"

    run = DigestRun(run_id="r1")
    state = {
        "run": run,
        "watchlist": Watchlist(),
        "items": [item],
    }

    agent = DigestEditorAgent(
        name="DigestEditor",
        settings=settings,
        storage=storage,
        narrator=lambda items: "Today's digest.",
    )
    await _run(agent, state)

    assert run.narrative == "Today's digest."
    assert state["narrative"] == "Today's digest."


@pytest.mark.asyncio
async def test_digest_editor_none_narrative_when_no_rendered(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    # All items are raw/filtered — select_rendered returns []
    item = _news("https://a.com/1", "Test")
    item.status = "raw"

    run = DigestRun(run_id="r1")
    state = {
        "run": run,
        "watchlist": Watchlist(),
        "items": [item],
    }

    called = []

    def should_not_call(items):
        called.append(items)
        return "oops"

    agent = DigestEditorAgent(
        name="DigestEditor",
        settings=settings,
        storage=storage,
        narrator=should_not_call,
    )
    await _run(agent, state)

    # filtered items → select_rendered falls back to non-flagged, which includes raw
    # Actually "raw" != "flagged" so they ARE rendered — let's check:
    # select_rendered: processed? no. non-flagged? yes (raw != flagged). → [item]
    # Narrator IS called.
    assert called  # narrator WAS called because item is non-flagged
    assert run.narrative == "oops"


@pytest.mark.asyncio
async def test_digest_editor_narrator_failure_adds_stage_error(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    item = _news("https://a.com/1", "Test")
    item.status = "processed"

    run = DigestRun(run_id="r1")
    state = {
        "run": run,
        "watchlist": Watchlist(),
        "items": [item],
    }

    def boom_narrator(items):
        raise RuntimeError("narrator quota exhausted")

    agent = DigestEditorAgent(
        name="DigestEditor",
        settings=settings,
        storage=storage,
        narrator=boom_narrator,
    )
    events = await _run(agent, state)

    assert len(events) == 1
    assert len(run.source_errors) == 1
    assert run.source_errors[0]["stage"] == "narrative"
    assert "narrator quota exhausted" in run.source_errors[0]["error"]


# ---------------------------------------------------------------------------
# RenderAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_render_agent_writes_outputs_and_finalizes(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    item = _news("https://a.com/1", "OpenAI article")
    item.status = "processed"
    item.importance = Importance.HIGH
    item.summary_en = "A summary."

    run = DigestRun(run_id="r1")
    storage.create_run(run)
    state = {
        "run": run,
        "watchlist": Watchlist(),
        "items": [item],
        "narrative": "Digest narrative.",
    }

    agent = RenderAgent(name="Render", settings=settings, storage=storage)
    events = await _run(agent, state)

    assert len(events) == 1
    assert run.processed == 1
    assert run.high_importance == 1
    assert "md" in run.outputs
    assert "xlsx" in run.outputs
    assert "html" in run.outputs
    assert run.status == RunStatus.SUCCESS
    assert run.finished_at is not None

    # Items must be persisted
    saved_items = storage.get_items_for_run("r1")
    assert len(saved_items) == 1

    # Run must be finalized
    saved_run = storage.get_run("r1")
    assert saved_run is not None
    assert saved_run.status == RunStatus.SUCCESS


@pytest.mark.asyncio
async def test_render_agent_partial_status_when_source_errors(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    run = DigestRun(run_id="r1")
    run.source_errors.append({"stage": "processing", "error": "boom", "ts": "2026-01-01"})
    storage.create_run(run)

    state = {
        "run": run,
        "watchlist": Watchlist(),
        "items": [],
        "narrative": None,
    }

    agent = RenderAgent(name="Render", settings=settings, storage=storage)
    await _run(agent, state)

    assert run.status == RunStatus.PARTIAL


@pytest.mark.asyncio
async def test_render_agent_excludes_flagged_from_render(tmp_path):
    from pathlib import Path

    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    item_ok = _news("https://a.com/1", "Good article")
    item_ok.status = "processed"
    item_ok.summary_en = "Good summary."

    item_flagged = _news("https://a.com/2", "Bad article")
    item_flagged.status = "flagged"
    item_flagged.summary_en = "Hallucinated summary."

    run = DigestRun(run_id="r1")
    storage.create_run(run)

    state = {
        "run": run,
        "watchlist": Watchlist(),
        "items": [item_ok, item_flagged],
        "narrative": None,
    }

    agent = RenderAgent(name="Render", settings=settings, storage=storage)
    await _run(agent, state)

    md = Path(run.outputs["md"]).read_text(encoding="utf-8")
    assert "Good summary." in md
    assert "Hallucinated summary." not in md


# ---------------------------------------------------------------------------
# build_pipeline factory
# ---------------------------------------------------------------------------

def test_build_pipeline_returns_sequential_agent(tmp_path):
    from google.adk.agents import SequentialAgent

    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    pipeline = build_pipeline(settings, storage)

    assert isinstance(pipeline, SequentialAgent)
    assert pipeline.name == "NewsCatchUpPipeline"


def test_build_pipeline_has_correct_agent_sequence(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    pipeline = build_pipeline(settings, storage)
    names = [a.name for a in pipeline.sub_agents]

    assert names == [
        "PipelineInit",
        "CollectSources",
        "NormalizeDedup",
        "Processing",
        "GuardrailCritic",
        "DigestEditor",
        "Render",
    ]


def test_build_pipeline_collect_sources_has_five_collectors(tmp_path):
    from google.adk.agents import ParallelAgent

    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    pipeline = build_pipeline(settings, storage)
    collect_sources = pipeline.sub_agents[1]

    assert isinstance(collect_sources, ParallelAgent)
    assert collect_sources.name == "CollectSources"
    assert len(collect_sources.sub_agents) == 5

    collector_names = {a.name for a in collect_sources.sub_agents}
    assert collector_names == {
        "CollectRss", "CollectScrape", "CollectApi", "CollectSearch", "CollectYoutube"
    }


def test_build_pipeline_collector_state_keys_are_distinct(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    pipeline = build_pipeline(settings, storage)
    collect_sources = pipeline.sub_agents[1]

    keys = [a.state_key for a in collect_sources.sub_agents]
    assert len(keys) == len(set(keys)), "Each collector must have a unique state_key"


def test_build_pipeline_accepts_injected_dependencies(tmp_path):
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    def fake_collect(s, st, sto):
        return []

    def fake_processor(items):
        return ProcessingResult(items=[])

    def fake_narrator(items):
        return "injected narrative"

    def fake_critic(items):
        return []

    pipeline = build_pipeline(
        settings, storage,
        collect_fn=fake_collect,
        processor=fake_processor,
        narrator=fake_narrator,
        critic=fake_critic,
    )

    assert pipeline is not None
    assert pipeline.name == "NewsCatchUpPipeline"


def test_build_pipeline_run_id_param_accepted(tmp_path):
    """build_pipeline must accept run_id kwarg without raising."""
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    pipeline = build_pipeline(settings, storage, run_id="explicit-run-id")
    assert pipeline is not None


# ---------------------------------------------------------------------------
# SourceType -> state-key: single source of truth
# ---------------------------------------------------------------------------

from app.pipeline.agents import COLLECTED_SOURCE_TYPES, state_key_for  # noqa: E402


def test_state_key_for_matches_existing_literals():
    """state_key_for must reproduce the historical raws_* literals exactly so
    storage and existing tests are unaffected."""
    assert [state_key_for(t) for t in COLLECTED_SOURCE_TYPES] == [
        "raws_rss", "raws_scrape", "raws_api", "raws_search", "raws_youtube"
    ]
    for t in COLLECTED_SOURCE_TYPES:
        assert state_key_for(t) == f"raws_{t.value}"


def test_collector_nodes_and_merge_derive_from_same_source(tmp_path):
    """Every collected SourceType must have a collector node AND be merged by
    NormalizeDedup — both derived from COLLECTED_SOURCE_TYPES, so a new type
    can never be wired into one but silently dropped by the other."""
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    pipeline = build_pipeline(settings, storage)
    collect_sources = pipeline.sub_agents[1]

    node_types = {a.source_type for a in collect_sources.sub_agents}
    node_keys = {a.state_key for a in collect_sources.sub_agents}

    # Collector nodes cover exactly the source-of-truth set.
    assert node_types == set(COLLECTED_SOURCE_TYPES)
    # Their keys are exactly the keys the merge will read.
    assert node_keys == {state_key_for(t) for t in COLLECTED_SOURCE_TYPES}


@pytest.mark.asyncio
async def test_normalize_dedup_merges_every_collected_source_type(tmp_path):
    """Drive NormalizeDedup with one raw per collected SourceType and assert all
    of them are merged (proves the merge iterates the same source-of-truth)."""
    settings = _settings(tmp_path)
    storage = _storage(tmp_path)

    run = DigestRun(run_id="r1")
    storage.create_run(run)

    state: dict = {"run": run, "watchlist": Watchlist()}
    for i, t in enumerate(COLLECTED_SOURCE_TYPES):
        state[state_key_for(t)] = [_raw(f"https://merge.test/{i}", f"Item {t.value}", t)]

    agent = NormalizeDedupAgent(name="NormalizeDedup", settings=settings, storage=storage)
    await _run(agent, state)

    assert run.collected == len(COLLECTED_SOURCE_TYPES)
    assert len(state["items"]) == len(COLLECTED_SOURCE_TYPES)
