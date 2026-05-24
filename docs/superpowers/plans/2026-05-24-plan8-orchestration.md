# Plan 8 — Orchestration: everything runs through the ADK agent tree

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal (user intent: "everything must be ADK"):** Make the **ADK agent tree the actual orchestration**. Build `root_agent = NewsCatchUpPipeline` — a `SequentialAgent` with a `ParallelAgent` for collection → Normalize → Processing → Guardrail → DigestEditor → Render — as thin `BaseAgent` wrappers over the existing proven functions, and **refactor `run_digest` to execute that tree via an ADK `Runner`** so the CLI and API run *through* ADK. Retire the dead scaffold weather `root_agent`. Also write a detailed **`docs/ADK-GUIDE.md`**.

**Approach = Option B (tree is the orchestration).** `run_digest` keeps its exact signature (`settings, storage, processor, narrator, critic`) and all injectable boundaries, but its BODY becomes: build the tree → run it via `InMemoryRunner` → return the `DigestRun`. **All 166 existing tests are the behavioral contract and MUST stay green** (status PARTIAL/SUCCESS/FAILED, counters, per-source isolation, per-stage graceful degradation, FAILED-finalize-and-reraise on unexpected errors). Builds fully offline (boundaries injected); only live tree runs need Gemini quota.

**Tech:** google-adk 1.34.x `BaseAgent`/`SequentialAgent`/`ParallelAgent`/`App`/`InMemoryRunner`, pydantic, pytest(+pytest-asyncio). `uv`. **Commit identity `AhmedHeshamSakr <a.hesham1221@gmail.com>`, no AI trailers.** Don't change the model. Branch `feat/orchestration` (off clean `main`).

## Load-bearing ADK facts (verified in source)
- Custom `BaseAgent._run_async_impl(self, ctx)`: `ctx.session.state` is a mutable dict; `SequentialAgent` passes the SAME ctx/session to each child → a value written by one child is visible to the next. Yield one terminal `Event` (optionally `EventActions(state_delta=...)`).
- `ParallelAgent` children SHARE the same `session.state` object → each parallel collector writes a DISTINCT key (`raws_rss|scrape|api|search|youtube`); a downstream agent merges them.
- `InMemorySessionService.create_session(app_name, user_id, state=?)` accepts an initial `state` dict and stores arbitrary Python objects. Re-read final state via `get_session(...)`.
- Agent loader for dir `app`: prefers a module attr `app` that is an `App` → keep `app = App(root_agent=..., name="app")` (`name="app"` matches `agents-cli-manifest.yaml`).
- `asyncio.run` bridges the async tree into sync `run_digest` (sync/threadpool context, no running loop) — same pattern as `adk_runtime.run_agent_text`.
- pytest has no async config yet → add `asyncio_mode = "auto"`.

## State keys (in `ctx.session.state`)
`run_id` (seeded by the delegator), `run` (DigestRun), `watchlist`, `settings`; `raws_rss|scrape|api|search|youtube`; `items`; `narrative`. `storage`/`settings` are infra → constructor args on the wrapper agents, NOT serialized state.

---

### Task 1 — `app/pipeline/agents.py`: BaseAgent wrappers + `build_pipeline`
**Create** `app/pipeline/agents.py`. Each wrapper is a `BaseAgent` subclass (`model_config = ConfigDict(arbitrary_types_allowed=True)`) whose `_run_async_impl(self, ctx)` reads inputs from `ctx.session.state`, calls the EXISTING function, writes outputs back, yields one terminal Event. Helper `_done_event(ctx, author, summary)`.
- `PipelineInitAgent(settings, storage)` — read `state["run_id"]`; create `DigestRun(run_id=run_id)`; `storage.create_run(run)`; `load_watchlist`; seed `state["run"|"watchlist"|"settings"]`.
- `SourceCollectorAgent(source_type, state_key, settings, storage, collect_fn)` — iterate `load_sources`, filter enabled + matching `source_type`; per-source `try/except → run.source_errors`; write `state[state_key]` (own key → parallel-safe). (Reuse the existing `_collect` from `runner.py` as the default `collect_fn`.)
- `NormalizeDedupAgent(settings, storage)` — concat `raws_*` (fixed order), `normalize.normalize_and_dedup(...)`, set `run.collected`/`run.new`, write `state["items"]`.
- `ProcessingAgent(settings, storage, processor)` — `process_items(items, processor, watchlist, threshold, batch_size)`; try/except → `{"stage":"processing",...}`.
- `GuardrailCriticAgent(settings, storage, critic)` — `select_for_critique`→`critic`→`apply_verdicts`; set `run.flagged`/`critic_verdicts`; try/except → `{"stage":"critic",...}`.
- `DigestEditorAgent(settings, storage, narrator)` — `rendered = select_rendered(items)`; `run.narrative = narrator(rendered)`; try/except → `{"stage":"narrative",...}`; write `state["narrative"]`.
- `RenderAgent(settings, storage)` — set `run.processed`/`run.high_importance`; `storage.save_items(items)`; write md/xlsx/html via the render writers **(do NOT catch render errors — they must propagate so the delegator can mark the run FAILED, matching current behavior)**; set `run.status` (PARTIAL if `run.source_errors` else SUCCESS), `run.finished_at`, `storage.finalize_run(run)`.
- `build_pipeline(settings, storage, *, run_id, collect_fn=_collect, processor=None, narrator=None, critic=None) -> SequentialAgent` — defaults via `_default_*`; `ParallelAgent("CollectSources", [5 SourceCollectorAgents])`; `SequentialAgent("NewsCatchUpPipeline", [PipelineInit, CollectSources, NormalizeDedup, Processing, Guardrail, DigestEditor, Render])`. (run_id is seeded into session state by the delegator, OR passed to PipelineInit — choose the session-state seed.)
- First extract `select_rendered(items)` into `runner.py` (the existing `[processed] or [non-flagged]` logic) so both the wrapper and the old code path agree.

### Task 2 — Refactor `run_digest` to run the tree (the core change; TDD against the 166 tests)
**Modify** `app/runner.py`. Replace the imperative body of `run_digest(settings, storage, processor, narrator, critic)` with:
```python
def run_digest(settings=None, storage=None, processor=None, narrator=None, critic=None) -> DigestRun:
    settings = settings or Settings()
    storage = storage or build_storage(settings)
    run_id = uuid.uuid4().hex[:12]
    tree = build_pipeline(settings, storage, run_id=run_id,
                          processor=processor, narrator=narrator, critic=critic)
    try:
        asyncio.run(_run_tree(tree, run_id))
    except Exception as exc:
        run = storage.get_run(run_id)
        if run is not None:
            run.status = RunStatus.FAILED
            run.finished_at = datetime.now(UTC)
            run.source_errors.append({"error": str(exc), "ts": datetime.now(UTC).isoformat()})
            storage.finalize_run(run)
        raise
    return storage.get_run(run_id)

async def _run_tree(tree, run_id):
    runner = InMemoryRunner(agent=tree, app_name="catchup")
    session = await runner.session_service.create_session(
        app_name="catchup", user_id="system", state={"run_id": run_id})
    msg = types.Content(role="user", parts=[types.Part.from_text(text="run")])
    async for _ in runner.run_async(user_id="system", session_id=session.id, new_message=msg):
        pass
```
Keep `build_storage`, `_collect`, `_default_*`, `select_rendered`. **Run `uv run pytest tests -q` repeatedly — every existing run_digest test must pass:** end-to-end SUCCESS + outputs + saved items; per-source isolation → PARTIAL; unexpected render error → FAILED + finalized + `source_errors` has the error + RuntimeError re-raised; the critic/intel integration tests (injected `critic=`/`processor=`). Fix the wrappers until green. (The render-FAILED test relies on RenderAgent NOT catching the write error so it propagates to the delegator.)

### Task 3 — Retire the weather `root_agent`
**Modify** `app/agent.py`: delete the weather tools/agent/imports; 
```python
from google.adk.apps import App
from app.core.config import Settings
from app.pipeline.agents import build_pipeline
from app.runner import build_storage
import uuid
_settings = Settings()
root_agent = build_pipeline(_settings, build_storage(_settings), run_id=uuid.uuid4().hex[:12])
app = App(root_agent=root_agent, name="app")
```
(Import-time `build_storage` opens sqlite — acceptable for `adk web`; note lazy-init as a follow-up.) Verify `uv run python -c "import app.agent as a; print(type(a.root_agent).__name__, a.app.name)"` → `SequentialAgent app`.

### Task 4 — Tests (offline, async)
- `tests/unit/test_pipeline_agents.py` — each wrapper's `_run_async_impl` via a fake ctx (`SimpleNamespace(session=SimpleNamespace(state={...}), invocation_id="t", branch=None)`), boundaries injected: collector happy + per-source failure; normalize merges + dedups; processing/guardrail with injected fakes; render writes + finalizes.
- `tests/integration/test_pipeline_tree.py` — `build_pipeline` driven by `InMemoryRunner` with injected `collect_fn`/`processor`/`narrator`/`critic`; assert outputs written, items saved, SUCCESS; a raising `collect_fn` → PARTIAL.
- `pyproject.toml` `[tool.pytest.ini_options]`: add `asyncio_mode = "auto"`. Full suite green.

### Task 5 — `docs/ADK-GUIDE.md` (detailed)
Write a thorough guide covering: (1) what ADK is + which ADK pieces we use (`Agent`/`LlmAgent` with `output_schema`, `BaseAgent`, `SequentialAgent`, `ParallelAgent`, `App`, `Runner`/`InMemoryRunner`, `Session`/state, `google_search` tool, `google.genai` types); (2) our **agent tree diagram** (root `NewsCatchUpPipeline` → nodes) with each agent's role, inputs/outputs, and the file it lives in; (3) the LLM agents (`news_processor`, `digest_editor`, `faithfulness_critic`, `enrichment_judge`, `youtube_summary`, `search_collector`) — model, prompt file, output_schema; (4) **exactly how we connect to ADK** — `adk_runtime.run_agent_text` (sync bridge over `run_async`), how state flows through `ctx.session.state`, how `run_digest` drives the tree, how `app/agent.py`/`App` exposes it to `adk web`/`adk run`; (5) the injectable-boundary pattern (why tests are offline); (6) free-tier (AI Studio key) vs Vertex; (7) how to run it (`adk run app`, `adk web`, `uv run python -m app.cli run`). Detailed, with code snippets and the data-flow.

### Task 6 — README + BUILD-LOG, final review, PR
- README architecture section: `adk run`/`adk web` now drive the real `NewsCatchUpPipeline`; `run_digest` executes the ADK tree. Link `docs/ADK-GUIDE.md`. BUILD-LOG entry (Option B; what defers to live quota; this fixed the stacked-merge gap by branching from clean main).
- Final reviewer over the branch. Push + PR → main (**delete branch on merge**). All commits AhmedHeshamSakr.

## Offline integrity & deferred
All LLM/collection boundaries injectable; wrappers call proven functions; tests fully offline. **Deferred to quota:** live `adk web`/`adk run` driving the tree's Gemini nodes; a live end-to-end tree run.

## Self-review
- Tree is the real orchestration (`run_digest` runs it) → "everything ADK". ✓
- All 166 tests preserved (behavioral contract). ✓
- ParallelAgent safety via distinct per-source keys. ✓
- Graceful degradation + per-source isolation + FAILED-reraise preserved. ✓
- Weather toy retired; `App(name="app")` kept for loader. ✓
- ADK-GUIDE.md documents features + architecture + connection. ✓
