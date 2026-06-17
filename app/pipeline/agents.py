"""ADK agent wrappers for the NewsCatchUp pipeline.

Each wrapper is a thin BaseAgent subclass that reads state from
ctx.session.state, calls the existing proven functions, and writes results
back via EventActions.state_delta. No LLM calls — all orchestration only.

State-propagation: every cross-stage value travels via
``EventActions.state_delta`` as JSON-serializable data (run/items/raws as
``model_dump`` dicts). settings, storage and the watchlist are
constructor-injected, never stored in the session. This makes the tree correct
under a persistent session service (DatabaseSessionService) — only
``state_delta`` survives a session reload, so direct ``ctx.session.state``
mutation would be lost across processes. The ``_read_*`` helpers stay tolerant
of a live object OR a dict so the migration could land stage-by-stage.
See docs/superpowers/specs/2026-06-17-durable-session-state-design.md.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from google.adk.agents import ParallelAgent, SequentialAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from pydantic import ConfigDict

from app.core.config import Settings, load_sources
from app.core.domain import (
    DigestRun,
    Importance,
    NewsItem,
    RawItem,
    RunStatus,
    SourceType,
)
from app.core.ports.storage import StorageBackend
from app.pipeline.critic import (
    apply_verdicts,
    redact_unfaithful,
    reflect_and_correct,
    select_for_critique,
)
from app.pipeline.processing import process_items
from app.runner import (
    _collect,
    _default_critic,
    _default_narrator,
    _default_processor,
    _default_reprocessor,
    select_rendered,
)
from app.services import normalize as normalize_svc
from app.services.render import excel, markdown
from app.services.render import html as html_render
from app.services.watchlist import Watchlist, load_watchlist

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext


# ---------------------------------------------------------------------------
# Source-of-truth: collected source types and their state keys
# ---------------------------------------------------------------------------

# Single source of truth for which SourceTypes are collected by the pipeline.
# Both the per-type collector nodes and the NormalizeDedup merge iterate this,
# so adding a SourceType here wires it through collection AND merging — no more
# silently dropping a source by forgetting to update a second hardcoded list.
COLLECTED_SOURCE_TYPES: tuple[SourceType, ...] = (
    SourceType.RSS,
    SourceType.SCRAPE,
    SourceType.API,
    SourceType.SEARCH,
    SourceType.YOUTUBE,
)


def state_key_for(source_type: SourceType) -> str:
    """State key holding the raw items collected for ``source_type``.

    Returns the existing literals (``raws_rss`` … ``raws_youtube``) so storage
    and tests are unaffected; the matching errors key is ``errors_<key>``.
    """
    return f"raws_{source_type.value}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    """ISO timestamp for error entries."""
    return datetime.now(UTC).isoformat()


def _now_dt() -> datetime:
    return datetime.now(UTC)


def _make_event(ctx: Any, author: str, state_delta: dict | None = None) -> Event:
    """Build a terminal pipeline event.

    Durable cross-stage values travel via ``EventActions.state_delta`` so the
    pipeline is correct under a persistent session service (the runner applies
    each event's delta to the session before the next agent runs). Pass the keys
    this stage changed; omit for a stage that changes nothing.
    """
    return Event(
        invocation_id=ctx.invocation_id,
        author=author,
        branch=ctx.branch,
        actions=EventActions(state_delta=state_delta or {}),
    )


def _read_run(state: Any) -> DigestRun:
    """Read the run from state, tolerant of either a JSON dict (persistent /
    post-migration) or a live DigestRun (in-process / pre-migration)."""
    r = state["run"]
    return DigestRun.model_validate(r) if isinstance(r, dict) else r


def _read_items(state: Any) -> list[NewsItem]:
    return [
        NewsItem.model_validate(x) if isinstance(x, dict) else x
        for x in (state.get("items") or [])
    ]


def _read_raws(state: Any, key: str) -> list[RawItem]:
    return [
        RawItem.model_validate(x) if isinstance(x, dict) else x
        for x in (state.get(key) or [])
    ]


def _run_delta(run: DigestRun) -> dict:
    return {"run": run.model_dump(mode="json")}


def _items_delta(items: list[NewsItem]) -> dict:
    return {"items": [i.model_dump(mode="json") for i in items]}


# ---------------------------------------------------------------------------
# PipelineInitAgent
# ---------------------------------------------------------------------------

class PipelineInitAgent(BaseAgent):
    """Seeds DigestRun and watchlist into session state."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    settings: Settings
    storage: StorageBackend

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        run_id = state.get("run_id")
        if not run_id:
            import uuid

            run_id = uuid.uuid4().hex[:12]
            state["run_id"] = run_id
        run = DigestRun(run_id=run_id)
        self.storage.create_run(run)

        wl = load_watchlist(self.settings.config_dir)

        state["run"] = run
        state["watchlist"] = wl
        state["settings"] = self.settings

        yield _make_event(ctx, self.name)


# ---------------------------------------------------------------------------
# SourceCollectorAgent
# ---------------------------------------------------------------------------

class SourceCollectorAgent(BaseAgent):
    """Collects raw items from one source type into a dedicated state key."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    source_type: SourceType
    state_key: str
    settings: Settings
    storage: StorageBackend
    collect_fn: Callable

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        raws = []
        errors: list[dict] = []

        for source in load_sources(self.settings.config_dir):
            if not source.enabled:
                continue
            if source.type != self.source_type:
                continue
            try:
                # Run the blocking collector off the event loop so the
                # ParallelAgent collectors are genuinely concurrent.
                collected = await asyncio.to_thread(
                    self.collect_fn, source, self.settings, self.storage
                )
                raws.extend(collected)
            except Exception as exc:
                errors.append(
                    {"source_id": source.id, "error": str(exc), "ts": _now()}
                )

        # Each parallel collector writes ONLY its own keys; NormalizeDedup
        # merges the per-source errors into run.source_errors single-threaded.
        state[self.state_key] = raws
        state[f"errors_{self.state_key}"] = errors

        yield _make_event(ctx, self.name)


# ---------------------------------------------------------------------------
# NormalizeDedupAgent
# ---------------------------------------------------------------------------

class NormalizeDedupAgent(BaseAgent):
    """Merges all raws_* keys, normalizes and deduplicates them."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    settings: Settings
    storage: StorageBackend

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        run = _read_run(state)

        all_raws = []
        for source_type in COLLECTED_SOURCE_TYPES:
            key = state_key_for(source_type)
            all_raws.extend(_read_raws(state, key))
            # Merge per-source collector errors (safe: this stage is single-threaded).
            run.source_errors.extend(state.get(f"errors_{key}") or [])

        run.collected = len(all_raws)
        items = normalize_svc.normalize_and_dedup(all_raws, self.storage, run.run_id)
        run.new = len(items)
        state["items"] = items

        yield _make_event(ctx, self.name)


# ---------------------------------------------------------------------------
# ProcessingAgent
# ---------------------------------------------------------------------------

class ProcessingAgent(BaseAgent):
    """Runs the enrichment processor over all items."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    settings: Settings
    storage: StorageBackend
    processor: Callable

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        run = _read_run(state)
        items = _read_items(state)
        watchlist = state["watchlist"]

        try:
            # Run the blocking LLM batch off the event loop so the loop stays
            # responsive (and a run-level asyncio timeout can actually fire).
            batch_errors = await asyncio.to_thread(
                process_items,
                items,
                self.processor,
                watchlist,
                self.settings.importance_threshold,
                self.settings.llm_batch_size,
            )
            for be in batch_errors:
                run.source_errors.append(
                    {
                        "stage": "processing",
                        "batch": be.get("batch"),
                        "error": be.get("error"),
                        "ts": _now(),
                    }
                )
        except Exception as exc:
            run.source_errors.append(
                {"stage": "processing", "error": str(exc), "ts": _now()}
            )

        yield _make_event(ctx, self.name)


# ---------------------------------------------------------------------------
# GuardrailCriticAgent
# ---------------------------------------------------------------------------

class GuardrailCriticAgent(BaseAgent):
    """Runs the faithfulness critic and applies verdicts."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    settings: Settings
    storage: StorageBackend
    critic: Callable
    reprocessor: Callable
    watchlist: Watchlist

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        run = _read_run(state)
        items = _read_items(state)
        watchlist = self.watchlist

        selected = select_for_critique(items, watchlist, self.settings)
        try:
            if selected:
                if self.settings.critic_max_reflections > 0:
                    # Bounded self-correction: re-enrich critic-flagged items with
                    # feedback before withholding (falls back to apply_verdicts).
                    # Off the loop — it makes LLM critic + reprocess calls.
                    outcome = await asyncio.to_thread(
                        reflect_and_correct,
                        selected,
                        self.critic,
                        self.reprocessor,
                        watchlist,
                        self.settings,
                    )
                else:
                    # Reflection disabled → exactly the pre-batch path.
                    verdicts = await asyncio.to_thread(self.critic, selected)
                    outcome = apply_verdicts(
                        selected,
                        verdicts,
                        self.settings.critic_action,
                        self.settings.importance_threshold,
                    )
                run.flagged = outcome["flagged"]
                run.critic_verdicts = outcome["verdicts"]
        except Exception as exc:
            run.source_errors.append(
                {"stage": "critic", "error": str(exc), "ts": _now(), "degraded": True}
            )
            # Fail-closed: the critic could not verify the selected (HIGH /
            # watchlisted) items, so protect them rather than ship unguarded.
            if self.settings.critic_fail_mode == "closed":
                for item in selected:
                    item.status = "flagged"
                    redact_unfaithful(item)
                run.flagged = len(selected)

        yield _make_event(ctx, self.name, {**_run_delta(run), **_items_delta(items)})


# ---------------------------------------------------------------------------
# DigestEditorAgent
# ---------------------------------------------------------------------------

class DigestEditorAgent(BaseAgent):
    """Generates the narrative digest summary."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    settings: Settings
    storage: StorageBackend
    narrator: Callable

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        run = _read_run(state)
        items = _read_items(state)
        rendered = select_rendered(items)

        try:
            # Narration is an LLM call — run it off the event loop.
            run.narrative = (
                await asyncio.to_thread(self.narrator, rendered) if rendered else None
            )
        except Exception as exc:
            run.source_errors.append(
                {"stage": "narrative", "error": str(exc), "ts": _now()}
            )

        # run.narrative was set above; it travels in the run delta. The old
        # standalone state["narrative"] key was vestigial (Render reads run.narrative).
        yield _make_event(ctx, self.name, _run_delta(run))


# ---------------------------------------------------------------------------
# RenderAgent
# ---------------------------------------------------------------------------

class RenderAgent(BaseAgent):
    """Writes all output files and finalizes the run."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    settings: Settings
    storage: StorageBackend

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        run = _read_run(state)
        items = _read_items(state)

        run.processed = sum(1 for i in items if i.status == "processed")
        run.high_importance = sum(1 for i in items if i.importance == Importance.HIGH)
        self.storage.save_items(items)

        rendered = select_rendered(items)

        # Render failures propagate (no try/except)
        run.outputs["md"] = markdown.write_markdown(run, rendered, self.settings.output_dir)
        run.outputs["xlsx"] = excel.write_excel(run, rendered, self.settings.output_dir)
        run.outputs["html"] = html_render.write_html(run, rendered, self.settings.output_dir)

        run.status = RunStatus.PARTIAL if run.source_errors else RunStatus.SUCCESS
        run.finished_at = _now_dt()
        self.storage.finalize_run(run)

        yield _make_event(ctx, self.name, _run_delta(run))


# ---------------------------------------------------------------------------
# build_pipeline factory
# ---------------------------------------------------------------------------

def build_pipeline(
    settings: Settings,
    storage: StorageBackend,
    *,
    run_id: str | None = None,
    collect_fn: Callable | None = None,
    processor: Callable | None = None,
    narrator: Callable | None = None,
    critic: Callable | None = None,
    reprocessor: Callable | None = None,
) -> SequentialAgent:
    """Build and return the full NewsCatchUpPipeline SequentialAgent.

    The caller seeds run_id into session state before invoking the pipeline:
        session = await runner.session_service.create_session(
            ..., state={"run_id": run_id}
        )

    The build_pipeline `run_id` param is accepted for forward compatibility
    but unused here — PipelineInitAgent reads it from ctx.session.state.
    """
    _collect_fn = collect_fn or _collect
    _processor = processor or _default_processor(settings)
    _narrator = narrator or _default_narrator(settings)
    _critic = critic or _default_critic(settings)
    _reprocessor = reprocessor or _default_reprocessor(settings)

    # Watchlist is config, not run state: load it once here and inject it into
    # the stages that need it (Critic now; Processing in the next migration step)
    # instead of seeding the session. PipelineInit still seeds state["watchlist"]
    # for the not-yet-injected consumers until that seed is removed.
    watchlist = load_watchlist(settings.config_dir)

    # Build one collector per collected SourceType from the shared
    # source-of-truth, so the node keys and the NormalizeDedup merge keys can
    # never drift apart. Names preserve the existing literals (CollectRss …).
    collect_sources = ParallelAgent(
        name="CollectSources",
        sub_agents=[
            SourceCollectorAgent(
                name=f"Collect{source_type.value.capitalize()}",
                source_type=source_type,
                state_key=state_key_for(source_type),
                settings=settings,
                storage=storage,
                collect_fn=_collect_fn,
            )
            for source_type in COLLECTED_SOURCE_TYPES
        ],
    )

    return SequentialAgent(
        name="NewsCatchUpPipeline",
        sub_agents=[
            PipelineInitAgent(
                name="PipelineInit",
                settings=settings,
                storage=storage,
            ),
            collect_sources,
            NormalizeDedupAgent(
                name="NormalizeDedup",
                settings=settings,
                storage=storage,
            ),
            ProcessingAgent(
                name="Processing",
                settings=settings,
                storage=storage,
                processor=_processor,
            ),
            GuardrailCriticAgent(
                name="GuardrailCritic",
                settings=settings,
                storage=storage,
                critic=_critic,
                reprocessor=_reprocessor,
                watchlist=watchlist,
            ),
            DigestEditorAgent(
                name="DigestEditor",
                settings=settings,
                storage=storage,
                narrator=_narrator,
            ),
            RenderAgent(
                name="Render",
                settings=settings,
                storage=storage,
            ),
        ],
    )
