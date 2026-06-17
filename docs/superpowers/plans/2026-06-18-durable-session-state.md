# Durable ADK Session State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Each task is gated by a Codex review before commit (same as the critical-medium remediation).**

**Goal:** Make the 7-stage NewsCatchUp ADK pipeline correct under a persistent session service by moving every cross-stage value into `EventActions.state_delta` (JSON-serializable), then switch the live `run_digest` runtime to a SQLite-backed `DatabaseSessionService`.

**Architecture:** Each stage stops sharing one in-process `run`/`items` object graph. Instead it *reads-deserializes* state (`DigestRun.model_validate(...)`), mutates a local copy, and *yields a terminal Event carrying `EventActions(state_delta={...})`* with re-serialized JSON. `settings`/`storage`/`watchlist` leave session state (constructor-injected). The migration runs **in reverse pipeline order** (Render → … → PipelineInit) behind tolerant read helpers, so every commit stays green under the still-`InMemory` runtime; the runtime is switched to `DatabaseSessionService` only after all stages emit deltas.

**Tech Stack:** Python 3.13, Google ADK (`google.adk.agents`, `google.adk.runners.Runner`, `google.adk.sessions.DatabaseSessionService`), pydantic v2 / pydantic-settings, SQLite via `aiosqlite`+`greenlet`, pytest + pytest-asyncio, `uv`.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-06-17-durable-session-state-design.md` — authoritative; this plan implements it.
- **Commit identity:** `AhmedHeshamSakr <a.hesham1221@gmail.com>`, **NO AI/Claude trailers**.
- **Do not change business logic** inside the proven functions (`process_items`, `adk_critique`, `reflect_and_correct`, `apply_verdicts`, `normalize_and_dedup`, render writers, `select_rendered`). Only orchestration/state-handling changes.
- **Do NOT change any `model` value or unrelated config.**
- **Run Python via `uv`**: `uv run pytest ...`. Lint: `uv run --extra lint ruff check app tests`.
- **State contract (target):** session state holds ONLY JSON-serializable values — `run_id: str`, `run: dict`, `raws_<type>: list[dict]`, `errors_raws_<type>: list[dict]`, `items: list[dict]`. `settings`/`storage`/`watchlist` are constructor-injected, never in state.
- **Reverse-order invariant:** never migrate a stage's *writes* before every downstream reader/mutator already writes its delta. Read helpers are tolerant (accept dict OR object) so any partial state is consistent.
- **Verify bar (every task ends green):** `uv run pytest tests/unit tests/integration -q` and `uv run --extra lint ruff check app tests`.

---

## File Structure

- `pyproject.toml` — add `greenlet`, `aiosqlite` runtime deps (Task 1).
- `app/core/config.py` — add `session_backend`, `session_db_url` settings (Task 1).
- `app/runner.py` — `make_session_service` + URL resolver (Task 2); `_run_tree` switched to `Runner` + injected session service (Task 10).
- `app/pipeline/agents.py` — `EventActions` import, `_make_event(state_delta=)`, read helpers + delta helpers, all reads made tolerant (Task 3); per-stage delta writes (Tasks 4–9); watchlist constructor injection into Processing/Critic (Tasks 5–6); module docstring (Task 12).
- `tests/conftest.py` — **new**; force `SESSION_BACKEND=memory` for the suite (Task 10).
- `tests/unit/test_pipeline_agents.py` — add the `_drive` delta-applying harness + tolerant assertions (Task 3); per-stage `state_delta` assertions (Tasks 4–9).
- `tests/unit/test_session_service.py` — **new**; `make_session_service`/resolver (Task 2).
- `tests/unit/test_config.py` — new-settings defaults (Task 1).
- `tests/integration/test_pipeline_persistent_session.py` — flip xfail → must-pass (Task 11).
- `tests/integration/test_run_digest_database_session.py` — **new**; e2e `run_digest` on the DB backend (Task 11).
- `docs/BUILD-LOG.md`, `docs/ADK-GUIDE.md` — document the new contract (Task 12).

---

### Task 1: Runtime dependencies + Settings fields

**Files:**
- Modify: `pyproject.toml` (dependencies array)
- Modify: `app/core/config.py:42-91` (Settings)
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `Settings.session_backend: Literal["database","memory"]` (default `"database"`), `Settings.session_db_url: str` (default `""`).

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_config.py`:
```python
def test_session_defaults():
    from app.core.config import Settings
    s = Settings(_env_file=None)
    assert s.session_backend == "database"
    assert s.session_db_url == ""


def test_greenlet_and_aiosqlite_importable():
    # DatabaseSessionService's async SQLite engine needs both at runtime.
    import aiosqlite  # noqa: F401
    import greenlet  # noqa: F401
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_config.py::test_session_defaults tests/unit/test_config.py::test_greenlet_and_aiosqlite_importable -v`
Expected: FAIL — `session_backend` attribute missing; `greenlet` import error.

- [ ] **Step 3: Add the dependencies**

In `pyproject.toml`, add to the main `dependencies` list (alongside the existing runtime deps — keep formatting consistent):
```toml
    "greenlet",
    "aiosqlite",
```
Then sync: `uv lock && uv sync` (or `agents-cli install`).

- [ ] **Step 4: Add the settings fields**

In `app/core/config.py`, inside `Settings`, after the `run_timeout` field (around line 66) add:
```python
    # ADK session persistence. "database" (default) = persistent
    # DatabaseSessionService (SQLite via aiosqlite) so a run's session survives a
    # restart and the tree is portable to any persistent service. "memory" =
    # in-process InMemorySessionService (fast tests / ephemeral runs).
    session_backend: Literal["database", "memory"] = "database"
    # Session store URL. Empty => derive a local SQLite file next to sqlite_path:
    #   sqlite+aiosqlite:///<dir of sqlite_path>/sessions.db
    # Set explicitly to point at another backend later (e.g. postgresql+asyncpg://).
    session_db_url: str = ""
```
(`Literal` is already imported at `app/core/config.py:4`.)

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock app/core/config.py tests/unit/test_config.py
git commit -m "feat(config): session_backend/session_db_url settings + greenlet/aiosqlite deps"
```

---

### Task 2: Session-service factory in runner.py

**Files:**
- Modify: `app/runner.py` (add factory + resolver; do NOT wire into `_run_tree` yet)
- Test: `tests/unit/test_session_service.py` (new)

**Interfaces:**
- Produces:
  - `_resolve_session_db_url(settings: Settings) -> str`
  - `make_session_service(settings: Settings) -> BaseSessionService`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_session_service.py`:
```python
from google.adk.sessions import DatabaseSessionService, InMemorySessionService

from app.core.config import Settings
from app.runner import _resolve_session_db_url, make_session_service


def test_resolve_derives_local_sessions_db(tmp_path):
    s = Settings(_env_file=None, sqlite_path=str(tmp_path / "catchup.db"), session_db_url="")
    url = _resolve_session_db_url(s)
    assert url.startswith("sqlite+aiosqlite:///")
    assert url.endswith("/sessions.db")


def test_resolve_passes_explicit_url_through():
    s = Settings(_env_file=None, session_db_url="postgresql+asyncpg://h/db")
    assert _resolve_session_db_url(s) == "postgresql+asyncpg://h/db"


def test_make_memory_backend():
    s = Settings(_env_file=None, session_backend="memory")
    assert isinstance(make_session_service(s), InMemorySessionService)


def test_make_database_backend(tmp_path):
    s = Settings(
        _env_file=None, session_backend="database",
        sqlite_path=str(tmp_path / "catchup.db"),
    )
    assert isinstance(make_session_service(s), DatabaseSessionService)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_session_service.py -v`
Expected: FAIL — `cannot import name '_resolve_session_db_url'`.

- [ ] **Step 3: Implement the factory**

In `app/runner.py`, add `from pathlib import Path` to the imports, change `from google.adk.runners import InMemoryRunner` to `from google.adk.runners import Runner`, and add:
```python
from google.adk.sessions import (
    BaseSessionService,
    DatabaseSessionService,
    InMemorySessionService,
)


def _resolve_session_db_url(settings: Settings) -> str:
    """Effective ADK session DB URL. Empty session_db_url => a local SQLite file
    next to sqlite_path (separate from the app DB; ADK owns its own schema)."""
    if settings.session_db_url:
        return settings.session_db_url
    db_path = Path(settings.sqlite_path).resolve().parent / "sessions.db"
    return f"sqlite+aiosqlite:///{db_path}"


def make_session_service(settings: Settings) -> BaseSessionService:
    """Build the ADK session service for a run from settings.session_backend."""
    if settings.session_backend == "memory":
        return InMemorySessionService()
    return DatabaseSessionService(db_url=_resolve_session_db_url(settings))
```
> Note: changing the import to `Runner` will break `_run_tree` (it still references `InMemoryRunner`). That is fixed in Task 10. **To keep Task 2 green, temporarily leave `_run_tree` using `InMemoryRunner` by keeping BOTH imports:** `from google.adk.runners import InMemoryRunner, Runner`. Task 10 removes `InMemoryRunner`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_session_service.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/runner.py tests/unit/test_session_service.py
git commit -m "feat(runner): make_session_service + session_db_url resolver"
```

---

### Task 3: Pipeline state helpers + tolerant reads (prep, no behavior change)

**Files:**
- Modify: `app/pipeline/agents.py` (imports, `_make_event`, new helpers; convert ALL stage reads to helpers)
- Modify: `tests/unit/test_pipeline_agents.py` (add `_drive` harness; route tests through it + tolerant assertions)

**Interfaces:**
- Produces (module-level in `agents.py`):
  - `_make_event(ctx, author, state_delta: dict | None = None) -> Event`
  - `_read_run(state) -> DigestRun`
  - `_read_items(state) -> list[NewsItem]`
  - `_read_raws(state, key: str) -> list[RawItem]`
  - `_run_delta(run) -> dict` → `{"run": run.model_dump(mode="json")}`
  - `_items_delta(items) -> dict` → `{"items": [i.model_dump(mode="json") for i in items]}`
- Produces (in test file): `async def _drive(agent, state: dict) -> dict` — runs one agent, applies any yielded `state_delta`, returns the updated state.

- [ ] **Step 1: Add the import + helpers to agents.py**

At the top of `app/pipeline/agents.py` add the import:
```python
from google.adk.events.event_actions import EventActions
```
Replace `_make_event` (lines 94–105) with:
```python
def _make_event(ctx: Any, author: str, state_delta: dict | None = None) -> Event:
    """Build a terminal pipeline event.

    Durable cross-stage values travel via ``EventActions.state_delta`` so the
    pipeline is correct under a persistent session service (the runner applies
    each event's delta to the session before the next agent runs). Pass the
    keys this stage changed; omit for a stage that changes nothing.
    """
    return Event(
        invocation_id=ctx.invocation_id,
        author=author,
        branch=ctx.branch,
        actions=EventActions(state_delta=state_delta or {}),
    )
```
After `_make_event`, add the read/delta helpers:
```python
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
```
(`RawItem` is already imported at `agents.py:29`.)

- [ ] **Step 2: Convert all stage READS to the helpers (no write changes)**

In each stage `_run_async_impl`, replace direct reads:
- `run: DigestRun = state["run"]` → `run = _read_run(state)`
- `items: list[NewsItem] = state.get("items") or []` → `items = _read_items(state)`
- In `NormalizeDedupAgent`, replace `all_raws.extend(state.get(key) or [])` → `all_raws.extend(_read_raws(state, key))`.

Leave ALL writes (`state[...] = ...`, in-place object mutation, `_make_event(ctx, self.name)`) unchanged. Behavior is identical because pre-migration `state["run"]`/`state["items"]` hold live objects, so the helpers return those same objects.

- [ ] **Step 3: Add the `_drive` harness to the test file and route stage tests through it**

In `tests/unit/test_pipeline_agents.py`, add near the top:
```python
from app.pipeline.agents import _read_items, _read_run  # tolerant readers


async def _drive(agent, state: dict) -> dict:
    """Run one agent against a plain state dict, applying any yielded
    EventActions.state_delta (mimicking the ADK Runner), and return the state.
    Tolerant of stages that still mutate state directly (empty delta)."""
    ctx = _ctx(state)  # existing per-test context builder (rename to match file)
    async for ev in agent._run_async_impl(ctx):
        if ev.actions and ev.actions.state_delta:
            state.update(ev.actions.state_delta)
    return state
```
Then update existing stage tests so they: (a) call `state = await _drive(agent, state)` instead of iterating the agent and reading raw `state[...]`; (b) assert via the tolerant readers — e.g. `assert _read_run(state).collected == 2`, `assert _read_items(state)[0].status == "processed"`. This keeps them green now (empty deltas → state unchanged → readers return the mutated objects) AND after each later stage starts emitting deltas (readers deserialize the dicts).

> The exact per-test edits are mechanical: wherever a test currently does `async for _ in agent._run_async_impl(ctx): pass` followed by `state["run"].X` / `state["items"]`, switch to `_drive` + `_read_run(state).X` / `_read_items(state)`. Apply to every stage test in the file. Match the file's existing context-builder helper name.

- [ ] **Step 4: Run the full agents test module**

Run: `uv run pytest tests/unit/test_pipeline_agents.py -q`
Expected: PASS (all existing tests still green; behavior unchanged).

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/agents.py tests/unit/test_pipeline_agents.py
git commit -m "refactor(pipeline): state helpers + tolerant reads + delta-applying test harness"
```

---

### Task 4: RenderAgent emits run delta

**Files:**
- Modify: `app/pipeline/agents.py` `RenderAgent._run_async_impl` (lines ~382–404)
- Test: `tests/unit/test_pipeline_agents.py` (RenderAgent tests)

**Interfaces:**
- Consumes: `_read_run`, `_read_items`, `_run_delta`, `_make_event` (Task 3).

- [ ] **Step 1: Add the failing delta assertion**

In a RenderAgent test (e.g. the success-path one ~line 715), after driving the agent, assert the yielded event carried a run delta. Capture the event:
```python
async def _drive_capture(agent, state):
    ctx = _ctx(state)
    events = []
    async for ev in agent._run_async_impl(ctx):
        events.append(ev)
        if ev.actions and ev.actions.state_delta:
            state.update(ev.actions.state_delta)
    return state, events
```
Add a test:
```python
@pytest.mark.asyncio
async def test_render_emits_run_delta(tmp_path):
    settings, storage = _settings_storage(tmp_path)  # match file's fixture helpers
    state = {"run": DigestRun(run_id="r1"), "items": [_processed_item()]}
    agent = RenderAgent(name="Render", settings=settings, storage=storage)
    _, events = await _drive_capture(agent, state)
    delta = events[-1].actions.state_delta
    assert "run" in delta and isinstance(delta["run"], dict)
    assert delta["run"]["status"] in ("success", "partial")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_pipeline_agents.py::test_render_emits_run_delta -v`
Expected: FAIL — `state_delta` is empty (`'run' not in delta`).

- [ ] **Step 3: Migrate RenderAgent**

In `RenderAgent._run_async_impl`, keep the body but change the final `yield`:
```python
        run.status = RunStatus.PARTIAL if run.source_errors else RunStatus.SUCCESS
        run.finished_at = _now_dt()
        self.storage.finalize_run(run)

        yield _make_event(ctx, self.name, _run_delta(run))
```
(reads already use `_read_run`/`_read_items` from Task 3.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_pipeline_agents.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/agents.py tests/unit/test_pipeline_agents.py
git commit -m "refactor(pipeline): RenderAgent emits run state_delta"
```

---

### Task 5: DigestEditorAgent emits run delta (drop narrative state key)

**Files:**
- Modify: `app/pipeline/agents.py` `DigestEditorAgent._run_async_impl` (lines ~347–367)
- Test: `tests/unit/test_pipeline_agents.py` (DigestEditor tests)

- [ ] **Step 1: Add the failing delta assertion**

```python
@pytest.mark.asyncio
async def test_digest_editor_emits_run_delta_with_narrative(tmp_path):
    settings, storage = _settings_storage(tmp_path)
    state = {"run": DigestRun(run_id="r1"), "items": [_processed_item()]}
    agent = DigestEditorAgent(
        name="DigestEditor", settings=settings, storage=storage,
        narrator=lambda items: "A narrative.",
    )
    _, events = await _drive_capture(agent, state)
    delta = events[-1].actions.state_delta
    assert delta.get("run", {}).get("narrative") == "A narrative."
    assert "narrative" not in delta  # the vestigial separate key is gone
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_pipeline_agents.py::test_digest_editor_emits_run_delta_with_narrative -v`
Expected: FAIL — empty delta / `narrative` still written as its own key.

- [ ] **Step 3: Migrate DigestEditorAgent**

Replace the tail of `DigestEditorAgent._run_async_impl` (the `state["narrative"] = run.narrative` line and the `yield`) with:
```python
        # run.narrative was set above; it travels in the run delta. The old
        # standalone state["narrative"] key was vestigial (Render reads run.narrative).
        yield _make_event(ctx, self.name, _run_delta(run))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_pipeline_agents.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/agents.py tests/unit/test_pipeline_agents.py
git commit -m "refactor(pipeline): DigestEditor emits run delta, drop vestigial narrative key"
```

---

### Task 6: GuardrailCriticAgent — inject watchlist + emit run/items delta

**Files:**
- Modify: `app/pipeline/agents.py` `GuardrailCriticAgent` (class field + `_run_async_impl` lines ~285–331) and `build_pipeline` (Critic construction ~line 476)
- Test: `tests/unit/test_pipeline_agents.py` (GuardrailCritic tests)

**Interfaces:**
- Produces: `GuardrailCriticAgent.watchlist: Watchlist` (new constructor field).
- Consumes: `Watchlist`, `load_watchlist` (already imported at `agents.py:49`).

- [ ] **Step 1: Add the failing assertions**

The critic mutates `item.status`/`run.flagged`; assert both travel as deltas, and that it uses the injected watchlist (no `state["watchlist"]`):
```python
@pytest.mark.asyncio
async def test_critic_emits_run_and_items_delta_using_injected_watchlist(tmp_path):
    from app.services.watchlist import Watchlist
    settings, storage = _settings_storage(tmp_path)
    state = {"run": DigestRun(run_id="r1"), "items": [_high_item()]}  # no "watchlist" key
    agent = GuardrailCriticAgent(
        name="GuardrailCritic", settings=settings, storage=storage,
        critic=lambda items: [{"id": items[0].id, "faithful": False}],
        reprocessor=lambda items, verdicts: items,
        watchlist=Watchlist(entities=[], keywords=[]),
    )
    _, events = await _drive_capture(agent, state)
    delta = events[-1].actions.state_delta
    assert "run" in delta and "items" in delta
    assert isinstance(delta["items"], list) and isinstance(delta["items"][0], dict)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_pipeline_agents.py::test_critic_emits_run_and_items_delta_using_injected_watchlist -v`
Expected: FAIL — `TypeError` (no `watchlist` kwarg) and/or empty delta.

- [ ] **Step 3: Migrate GuardrailCriticAgent**

Add the field to the class (after `reprocessor: Callable`):
```python
    watchlist: Watchlist
```
Add the import at top of `agents.py`: `from app.services.watchlist import Watchlist, load_watchlist` (extend the existing `load_watchlist` import). In `_run_async_impl`, replace `watchlist = state["watchlist"]` with `watchlist = self.watchlist`, and change the final `yield` to emit both deltas (merge dicts):
```python
        yield _make_event(ctx, self.name, {**_run_delta(run), **_items_delta(items)})
```
In `build_pipeline`, load the watchlist once near the top of the function (after the `_collect_fn = ...` block):
```python
    watchlist = load_watchlist(settings.config_dir)
```
and pass `watchlist=watchlist` into the `GuardrailCriticAgent(...)` construction.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_pipeline_agents.py -q`
Expected: PASS. (Update the other GuardrailCritic test constructions to pass `watchlist=Watchlist(entities=[], keywords=[])`.)

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/agents.py tests/unit/test_pipeline_agents.py
git commit -m "refactor(pipeline): GuardrailCritic injects watchlist + emits run/items delta"
```

---

### Task 7: ProcessingAgent — inject watchlist + emit run/items delta

**Files:**
- Modify: `app/pipeline/agents.py` `ProcessingAgent` (class field + `_run_async_impl` lines ~235–268) and `build_pipeline` (Processing construction ~line 470)
- Test: `tests/unit/test_pipeline_agents.py` (Processing tests)

**Interfaces:**
- Produces: `ProcessingAgent.watchlist: Watchlist` (new constructor field).

- [ ] **Step 1: Add the failing assertion**

```python
@pytest.mark.asyncio
async def test_processing_emits_run_and_items_delta_using_injected_watchlist(tmp_path):
    from app.services.watchlist import Watchlist
    settings, storage = _settings_storage(tmp_path)
    state = {"run": DigestRun(run_id="r1"), "items": [_raw_item_in_state()]}  # no "watchlist"
    agent = ProcessingAgent(
        name="Processing", settings=settings, storage=storage,
        processor=_fake_processor,  # match file's existing fake
        watchlist=Watchlist(entities=[], keywords=[]),
    )
    _, events = await _drive_capture(agent, state)
    delta = events[-1].actions.state_delta
    assert "run" in delta and "items" in delta
    assert isinstance(delta["items"][0], dict)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_pipeline_agents.py::test_processing_emits_run_and_items_delta_using_injected_watchlist -v`
Expected: FAIL — no `watchlist` kwarg / empty delta.

- [ ] **Step 3: Migrate ProcessingAgent**

Add `watchlist: Watchlist` field after `processor: Callable`. In `_run_async_impl`, replace `watchlist = state["watchlist"]` with `watchlist = self.watchlist`, and change the final `yield`:
```python
        yield _make_event(ctx, self.name, {**_run_delta(run), **_items_delta(items)})
```
> `process_items` enriches the items in place; reading them via `_read_items` (fresh copies post-migration) and re-serializing in the delta captures that enrichment. In `build_pipeline`, pass `watchlist=watchlist` (already loaded in Task 6) into the `ProcessingAgent(...)` construction.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_pipeline_agents.py -q`
Expected: PASS. (Add `watchlist=...` to the other ProcessingAgent test constructions, incl. line ~978.)

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/agents.py tests/unit/test_pipeline_agents.py
git commit -m "refactor(pipeline): Processing injects watchlist + emits run/items delta"
```

---

### Task 8: NormalizeDedupAgent emits run/items delta

**Files:**
- Modify: `app/pipeline/agents.py` `NormalizeDedupAgent._run_async_impl` (lines ~201–219)
- Test: `tests/unit/test_pipeline_agents.py` (NormalizeDedup tests)

- [ ] **Step 1: Add the failing assertion**

```python
@pytest.mark.asyncio
async def test_normalize_emits_run_and_items_delta(tmp_path):
    settings, storage = _settings_storage(tmp_path)
    state = {"run": DigestRun(run_id="r1"), "raws_rss": [_raw("https://x/1", "T")]}
    agent = NormalizeDedupAgent(name="NormalizeDedup", settings=settings, storage=storage)
    _, events = await _drive_capture(agent, state)
    delta = events[-1].actions.state_delta
    assert delta["run"]["collected"] == 1
    assert delta["run"]["new"] == 1
    assert len(delta["items"]) == 1 and isinstance(delta["items"][0], dict)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_pipeline_agents.py::test_normalize_emits_run_and_items_delta -v`
Expected: FAIL — empty delta.

- [ ] **Step 3: Migrate NormalizeDedupAgent**

Replace `state["items"] = items` and the `yield` with:
```python
        yield _make_event(ctx, self.name, {**_run_delta(run), **_items_delta(items)})
```
(reads already tolerant from Task 3.)

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_pipeline_agents.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/agents.py tests/unit/test_pipeline_agents.py
git commit -m "refactor(pipeline): NormalizeDedup emits run/items delta"
```

---

### Task 9: SourceCollectorAgent emits raws/errors delta

**Files:**
- Modify: `app/pipeline/agents.py` `SourceCollectorAgent._run_async_impl` (lines ~157–186)
- Test: `tests/unit/test_pipeline_agents.py` (SourceCollector tests)

- [ ] **Step 1: Add the failing assertion**

```python
@pytest.mark.asyncio
async def test_collector_emits_raws_delta_as_dicts(tmp_path):
    settings, storage = _settings_storage_with_rss_source(tmp_path)  # match file helper
    state = {}
    agent = SourceCollectorAgent(
        name="CollectRss", source_type=SourceType.RSS, state_key="raws_rss",
        settings=settings, storage=storage,
        collect_fn=lambda src, s, st=None: [_raw("https://x/1", "T")],
    )
    _, events = await _drive_capture(agent, state)
    delta = events[-1].actions.state_delta
    assert isinstance(delta["raws_rss"], list) and isinstance(delta["raws_rss"][0], dict)
    assert delta["errors_raws_rss"] == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_pipeline_agents.py::test_collector_emits_raws_delta_as_dicts -v`
Expected: FAIL — empty delta.

- [ ] **Step 3: Migrate SourceCollectorAgent**

Replace the two `state[...] = ...` writes and the `yield` with:
```python
        yield _make_event(
            ctx, self.name,
            {
                self.state_key: [r.model_dump(mode="json") for r in raws],
                f"errors_{self.state_key}": errors,
            },
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_pipeline_agents.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/agents.py tests/unit/test_pipeline_agents.py
git commit -m "refactor(pipeline): SourceCollector emits raws/errors state_delta"
```

---

### Task 10: PipelineInitAgent emits run delta + drop settings/watchlist seeds

**Files:**
- Modify: `app/pipeline/agents.py` `PipelineInitAgent._run_async_impl` (lines ~120–139)
- Test: `tests/unit/test_pipeline_agents.py` (PipelineInit tests)

- [ ] **Step 1: Add the failing assertions**

```python
@pytest.mark.asyncio
async def test_pipeline_init_emits_run_delta_no_object_seeds(tmp_path):
    settings, storage = _settings_storage(tmp_path)
    state = {"run_id": "r1"}
    agent = PipelineInitAgent(name="PipelineInit", settings=settings, storage=storage)
    _, events = await _drive_capture(agent, state)
    delta = events[-1].actions.state_delta
    assert delta["run"]["run_id"] == "r1" and isinstance(delta["run"], dict)
    assert "settings" not in delta and "watchlist" not in delta
    # state no longer carries non-serializable objects
    assert "settings" not in state and "watchlist" not in state
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_pipeline_agents.py::test_pipeline_init_emits_run_delta_no_object_seeds -v`
Expected: FAIL — `state["settings"]`/`state["watchlist"]` still seeded; empty delta.

- [ ] **Step 3: Migrate PipelineInitAgent**

Replace the body after `self.storage.create_run(run)` (the `wl = ...` load and the three `state[...] =` writes and `yield`) with:
```python
        # settings/storage are constructor-injected; watchlist is injected into
        # the stages that need it (Processing/Critic). Seed only the durable run.
        delta = _run_delta(run)
        if state.get("run_id") != run_id:
            delta["run_id"] = run_id
        yield _make_event(ctx, self.name, delta)
```
Remove the now-unused `load_watchlist` usage here (the import stays — Task 6/build_pipeline uses it). Remove the local `wl` variable.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_pipeline_agents.py -q`
Expected: PASS. Then run the whole suite to confirm the InMemory path is fully delta-driven and still correct:
`uv run pytest tests/unit tests/integration -q` — Expected: all pass (persistent-session test still skips — flipped in Task 11).

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/agents.py tests/unit/test_pipeline_agents.py
git commit -m "refactor(pipeline): PipelineInit emits run delta, drops settings/watchlist seeds"
```

---

### Task 11: Switch runtime to the persistent session service + conftest isolation

**Files:**
- Modify: `app/runner.py` `_run_tree`, `_run_tree_with_timeout`, `run_digest` (lines ~75–142)
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: `make_session_service` (Task 2).

- [ ] **Step 1: Create the suite isolation conftest**

Create `tests/conftest.py`:
```python
"""Keep the test suite on the in-memory ADK session service by default so tests
stay fast and write no session DB. Tests that exercise the persistent path pass
session_backend="database" explicitly (init kwargs beat this env var)."""
import os

os.environ.setdefault("SESSION_BACKEND", "memory")
```

- [ ] **Step 2: Write the failing runtime test**

Add to `tests/unit/test_session_service.py`:
```python
import inspect
from app import runner


def test_run_tree_uses_injected_session_service():
    sig = inspect.signature(runner._run_tree)
    assert "session_service" in sig.parameters
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/unit/test_session_service.py::test_run_tree_uses_injected_session_service -v`
Expected: FAIL — `_run_tree` has no `session_service` parameter.

- [ ] **Step 4: Switch the runtime**

In `app/runner.py`, remove `InMemoryRunner` from the import (leave `Runner`). Rewrite the three functions:
```python
async def _run_tree(tree, run_id: str, session_service) -> None:
    runner = Runner(agent=tree, app_name="catchup", session_service=session_service)
    session = await session_service.create_session(
        app_name="catchup", user_id="system", state={"run_id": run_id}
    )
    msg = types.Content(role="user", parts=[types.Part.from_text(text="run")])
    async for _ in runner.run_async(
        user_id="system", session_id=session.id, new_message=msg
    ):
        pass


async def _run_tree_with_timeout(tree, run_id: str, session_service, timeout: float | None) -> None:
    # (keep the existing SOFT-cap docstring)
    if timeout is None:
        await _run_tree(tree, run_id, session_service)
    else:
        await asyncio.wait_for(_run_tree(tree, run_id, session_service), timeout=timeout)
```
In `run_digest`, after building `tree`, build the session service and pass it through:
```python
    session_service = make_session_service(settings)
    try:
        asyncio.run(_run_tree_with_timeout(tree, run_id, session_service, settings.run_timeout))
```

- [ ] **Step 5: Run to verify it passes (and the suite stays green)**

Run: `uv run pytest tests/unit tests/integration -q`
Expected: all pass. The suite runs on the memory backend (conftest); the persistent path is covered next.

- [ ] **Step 6: Commit**

```bash
git add app/runner.py tests/conftest.py tests/unit/test_session_service.py
git commit -m "feat(runner): run pipeline via Runner + persistent session service (memory default in tests)"
```

---

### Task 12: Flip the portability test to must-pass + e2e DB-backend run_digest

**Files:**
- Modify: `tests/integration/test_pipeline_persistent_session.py`
- Create: `tests/integration/test_run_digest_database_session.py`

- [ ] **Step 1: Flip the portability test**

In `tests/integration/test_pipeline_persistent_session.py`, the run is now expected to SUCCEED. Replace the `try/except → pytest.xfail(...)` block (lines ~135–150) with a plain assertion path (no xfail):
```python
    async for _ in runner.run_async(
        user_id="system", session_id=session.id, new_message=msg
    ):
        pass
    run = storage.get_run(run_id)
    assert run is not None
    assert run.status == RunStatus.SUCCESS
    assert run.collected == 1
    assert run.new == 1
```
Keep the `_service_runnable` skip guard (it should no longer skip now that `greenlet` is a runtime dep, but it stays as a safety net for exotic environments). Update the module docstring to say the tree IS portable (delta-driven) and this test proves it.

- [ ] **Step 2: Run it (should PASS now, not xfail)**

Run: `uv run pytest tests/integration/test_pipeline_persistent_session.py -v`
Expected: PASS (not xfail, not skip).

- [ ] **Step 3: Write the e2e DB-backend run_digest test**

Create `tests/integration/test_run_digest_database_session.py`:
```python
"""End-to-end: run_digest on the real production runtime path (database session
backend), proving the live code (not a hand-built Runner) works persistently."""
from pathlib import Path

from app.core.config import Settings
from app.core.domain import Category, RunStatus, SourceType
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
        session_backend="database",  # beats the conftest memory default
        sqlite_path=str(tmp_path / "catchup.db"),
        config_dir=str(cfg),
        output_dir=str(tmp_path / "out"),
    )


def test_run_digest_completes_on_database_session(tmp_path, monkeypatch):
    from app.core.domain import RawItem
    import app.runner as runner_mod

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

    monkeypatch.setattr(runner_mod, "_collect", fake_collect)
    settings = _settings(tmp_path)
    run = run_digest(
        settings,
        processor=lambda items: fake_enrich(items, settings),
        narrator=lambda items: "Narrative.",
        critic=lambda items: [],
    )
    assert run.status == RunStatus.SUCCESS
    assert run.collected == 1 and run.new == 1
    # the session DB landed next to the app DB
    assert (Path(settings.sqlite_path).parent / "sessions.db").exists()
```
> If `run_digest`'s `processor`/`critic`/`narrator` injection differs in arity from the above, match the signatures used by the existing `tests/integration` run_digest tests.

- [ ] **Step 4: Run it**

Run: `uv run pytest tests/integration/test_run_digest_database_session.py -v`
Expected: PASS; a `sessions.db` is created under `tmp_path`.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_pipeline_persistent_session.py tests/integration/test_run_digest_database_session.py
git commit -m "test: portability test must-pass + e2e run_digest on database session backend"
```

---

### Task 13: Docs + final verification

**Files:**
- Modify: `app/pipeline/agents.py` (module docstring lines 1–15)
- Modify: `docs/BUILD-LOG.md`, `docs/ADK-GUIDE.md`

- [ ] **Step 1: Update the agents.py module docstring**

Replace the lines 7–14 "State-propagation decision: … will need to move into `state_delta`" note with the new contract:
```
State-propagation: every cross-stage value travels via
``EventActions.state_delta`` as JSON-serializable data (run/items/raws as
model_dump dicts). settings, storage and the watchlist are constructor-injected,
never stored in the session. This makes the tree correct under a persistent
session service (DatabaseSessionService) — see
docs/superpowers/specs/2026-06-17-durable-session-state-design.md.
```

- [ ] **Step 2: Append a BUILD-LOG entry**

Add a dated "Durable session state (sub-project D)" section to `docs/BUILD-LOG.md` summarizing: state_delta migration (reverse order), watchlist/settings injection, runtime switch to `DatabaseSessionService` (`session_backend`/`session_db_url`), greenlet/aiosqlite runtime deps, portability test flipped to must-pass.

- [ ] **Step 3: Update ADK-GUIDE.md**

In `docs/ADK-GUIDE.md`, update any section describing direct `ctx.session.state` mutation / "no state_delta" to the new delta contract + the persistent session runtime.

- [ ] **Step 4: Final full verification**

Run each and confirm green:
```bash
uv run pytest tests/unit tests/integration -q
uv run --extra lint ruff check app tests
```
Expected: all pass; lint clean. Confirm `tests/integration/test_pipeline_persistent_session.py` PASSES (not xfail/skip).

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/agents.py docs/BUILD-LOG.md docs/ADK-GUIDE.md
git commit -m "docs: durable session-state contract + persistent runtime"
```

---

## Self-Review

**1. Spec coverage:**
- State_delta for all cross-stage values → Tasks 3–10. ✓
- settings/storage/watchlist out of state (constructor injection) → Tasks 6,7,10. ✓
- Drop vestigial `state["narrative"]` → Task 5. ✓
- New settings `session_backend`/`session_db_url` + derived URL → Tasks 1,2. ✓
- greenlet/aiosqlite runtime deps → Task 1. ✓
- Runtime switch to DatabaseSessionService → Task 11. ✓
- Portability test flips to must-pass → Task 12. ✓
- New e2e DB-backend run_digest test → Task 12. ✓
- State-delta guard (per-stage delta assertions) → distributed across Tasks 4–10. ✓
- conftest memory default + init-kwarg precedence → Task 11. ✓
- ADK availability precondition → covered: Task 1 installs greenlet (the missing piece; imports already verified), Task 12's e2e+portability tests prove the live path. If `DatabaseSessionService` had been unimportable the fallback was Approach 2 — but availability is confirmed (greenlet was the only gap).

**2. Placeholder scan:** No "TBD"/"handle errors"/"similar to". The only soft spots are explicit "match the file's existing helper name / fixture" notes for the pre-existing `tests/unit/test_pipeline_agents.py` — unavoidable since that file's local helpers aren't redefined here; the transformation rule and concrete assertions are given.

**3. Type consistency:** `_read_run/_read_items/_read_raws`, `_run_delta/_items_delta`, `_make_event(ctx, author, state_delta)`, `make_session_service`, `_resolve_session_db_url`, `_run_tree(tree, run_id, session_service)` are used consistently across tasks. `watchlist: Watchlist` field name matches in Processing (Task 7) and Critic (Task 6) and `build_pipeline`. State keys (`run`, `items`, `raws_<type>`, `errors_raws_<type>`, `run_id`) match the spec contract.
