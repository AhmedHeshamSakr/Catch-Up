# Durable ADK Session State — Design

**Date:** 2026-06-17
**Sub-project:** D (first of the 4-subsystem post-remediation milestone: D durable state → C Firestore/Vertex → B scheduler → A console screens)
**Status:** Design — awaiting user spec review before plan.

## Goal

Make the NewsCatchUp ADK pipeline correct under a **persistent session service** by moving every cross-stage value out of direct `ctx.session.state` object-mutation and into `EventActions.state_delta` (JSON-serializable), then switch the live `run_digest` runtime to a SQLite-backed `DatabaseSessionService`. Flip the existing xfail portability test to a passing test.

## Why now

The pipeline currently relies on all seven stages sharing **one in-process object graph**: `PipelineInitAgent` creates a `DigestRun`, and `NormalizeDedup → Processing → GuardrailCritic → DigestEditor → Render` mutate that same `run` object (and the same `items` list — Critic flips `item.status`) in place, then emit empty terminal events with no `state_delta`. This only works with `InMemorySessionService`, where every stage sees the same Python object.

A persistent/distributed session service hands each agent a **freshly deserialized copy** of session state between events. Under that model the in-place mutations vanish — exactly what `tests/integration/test_pipeline_persistent_session.py` is written to catch (it `xfail`s today with *"direct ctx.session.state mutation not persisted by DatabaseSessionService — Plan 9 must move durable values to state_delta"*). This sub-project is the foundation that makes C (Firestore) and any future distributed/resumable run safe.

## Approach (chosen)

**Full `state_delta` refactor + switch runtime to `DatabaseSessionService`.** Both the serialization refactor *and* the runtime swap (the user explicitly chose to switch the runtime, not just prove portability via the test).

Rejected alternatives:
- *Minimal mirror* (only mirror the values the test checks; keep direct mutation as the live path) — the xfail comment explicitly names this the wrong path; it leaves latent "mutation lost" bugs the moment anything distributed touches state.
- *Refactor but keep `InMemoryRunner` at runtime* — proves portability via the test only. The user chose to switch the runtime for true production parity and resumability/inspectability of session state.

## Architecture

### New session-state contract — every value JSON-serializable

| Key | Type | Written by | Read by |
|-----|------|-----------|---------|
| `run_id` | `str` | session seed (`create_session(state={"run_id": ...})`) / PipelineInit | PipelineInit |
| `run` | `dict` — `DigestRun.model_dump(mode="json")` | every stage that mutates the run, via `state_delta` | all downstream stages |
| `raws_<type>` | `list[dict]` — `RawItem.model_dump(mode="json")` | each parallel `SourceCollectorAgent` | NormalizeDedup |
| `errors_raws_<type>` | `list[dict]` | each parallel `SourceCollectorAgent` | NormalizeDedup |
| `items` | `list[dict]` — `NewsItem.model_dump(mode="json")` | NormalizeDedup, Processing, GuardrailCritic | downstream stages |

`<type>` ∈ the existing `state_key_for(source_type)` literals (`raws_rss` … `raws_youtube`). Keys and shapes are unchanged in name; only their *values* change from live objects to JSON dicts, and writes move from `state[key] = obj` to a yielded `state_delta`.

### Removed from session state → constructor injection

These are **configuration**, not per-run state, and must not live in a serialized session:
- `settings` — already injected into every agent ctor; today's `state["settings"] = self.settings` (PipelineInit) is dead weight no stage reads. **Stop writing it.**
- `storage` — already injected into every agent ctor. Never belonged in state.
- `watchlist` — today loaded in PipelineInit and written to `state["watchlist"]`, read by Processing + Critic. Move to: load **once** in `build_pipeline(...)` via `load_watchlist(settings.config_dir)` and pass into the `ProcessingAgent` and `GuardrailCriticAgent` constructors as a `watchlist` field. **Stop writing it to state.**
- `state["narrative"]` (DigestEditor) — vestigial; Render reads `run.narrative`, not this key. **Drop it.**

### Per-stage change (uniform read-deserialize / mutate / write-delta pattern)

Each stage:
1. **Reads** by deserializing from `ctx.session.state`: `run = DigestRun.model_validate(state["run"])`, `items = [NewsItem.model_validate(x) for x in state.get("items") or []]`, `raws = [RawItem.model_validate(x) for x in state.get(key) or []]`.
2. **Mutates** its local copies (unchanged business logic — the proven functions are untouched).
3. **Yields** a terminal `Event` carrying `EventActions(state_delta={...})` with **only the keys it changed**, re-serialized to JSON.

Stage-by-stage `state_delta` payloads:

| Stage | Reads | `state_delta` it yields |
|-------|-------|--------------------------|
| **PipelineInit** | `run_id` | `{"run_id": run_id, "run": run.model_dump(mode="json")}` (still calls `storage.create_run(run)`) |
| **SourceCollector** (×N parallel) | `sources` from config | `{state_key: [r.model_dump(mode="json") for r in raws], f"errors_{state_key}": errors}` — distinct keys per branch, so ADK's parallel merge is conflict-free |
| **NormalizeDedup** | `run`, all `raws_*` + `errors_*` | `{"run": run.model_dump(mode="json"), "items": [i.model_dump(mode="json") for i in items]}` |
| **Processing** | `run`, `items`, (injected `watchlist`) | `{"run": ..., "items": ...}` (enrichment mutates items + run.source_errors) |
| **GuardrailCritic** | `run`, `items`, (injected `watchlist`) | `{"run": ..., "items": ...}` (verdicts mutate run.flagged/critic_verdicts + item.status) |
| **DigestEditor** | `run`, `items` | `{"run": ...}` (sets run.narrative; items unchanged) |
| **Render** | `run`, `items` | `{"run": ...}` (final counts/status/outputs; persists via `storage.save_items` + `finalize_run`) |

`_make_event(ctx, author)` grows a `state_delta: dict | None = None` param and attaches `actions=EventActions(state_delta=state_delta)` when provided. The module docstring's "we intentionally emit no state_delta" note is replaced with the new contract.

### Runtime: persistent session service

`app/runner.py`:
- New `make_session_service(settings)`:
  - `settings.session_backend == "database"` → `DatabaseSessionService(db_url=<resolved url>)`.
  - `settings.session_backend == "memory"` → `InMemorySessionService()`.
- `_run_tree(tree, run_id, session_service)` builds `Runner(agent=tree, app_name="catchup", session_service=session_service)` (replacing `InMemoryRunner`). Artifact/memory services are not used by the pipeline; the plan verifies whether `Runner` needs an explicit `InMemoryArtifactService` (match `InMemoryRunner`'s wiring) or accepts the defaults.
- `run_digest(...)` builds the session service once via `make_session_service(settings)` and threads it through `_run_tree_with_timeout`.
- The `asyncio.run(...)` + `run_timeout` SOFT-cap semantics are unchanged.

### Config (`app/core/config.py`)

Add to `Settings`:
```python
# ADK session persistence. "database" (default) = persistent DatabaseSessionService
# (SQLite via aiosqlite) so a run's session survives a restart and the tree is
# portable to any persistent service. "memory" = in-process InMemorySessionService
# (fast tests / ephemeral runs).
session_backend: Literal["database", "memory"] = "database"
# Session store URL. Empty => derive a local SQLite file next to sqlite_path:
#   sqlite+aiosqlite:///<dir of sqlite_path>/sessions.db
# Set explicitly to point at another backend later (e.g. postgresql+asyncpg://…).
session_db_url: str = ""
```
A small resolver (in `runner.py` or a `Settings` helper) computes the effective URL when `session_db_url` is empty. The session DB is a **separate file** from the app DB (`catchup.db`) — ADK owns its own schema.

### Dependencies (`pyproject.toml`)

Add `greenlet` and `aiosqlite` as **runtime** dependencies. They are absent today (which is exactly why the portability test currently skips on this machine); `DatabaseSessionService`'s SQLAlchemy async engine needs them at runtime once it's the live session store. Update `uv.lock` accordingly.

## Preconditions / risks

- **ADK must actually ship `DatabaseSessionService` + `Runner` in the installed version.** The portability test imports them inside a `try/except` and skips if unavailable, so their presence is **not** guaranteed. The plan's **first task** verifies, offline, that `from google.adk.sessions import DatabaseSessionService` and `from google.adk.runners import Runner` import *and* that `DatabaseSessionService(db_url=...).create_session(...)` runs with `greenlet`+`aiosqlite` installed. If that check fails, the runtime switch is blocked → fall back to **Approach 2** (keep `InMemoryRunner` at runtime, still do the full `state_delta` refactor, prove portability via the now-passing test) and flag it to the user before proceeding. The `state_delta` refactor is identical under either approach, so no rework is lost.
- **Parallel `state_delta` merge:** the per-type collectors each write only their own `raws_<type>`/`errors_raws_<type>` keys, so ADK's concurrent-branch state merge never has a key conflict. The persistent-session test exercises this end-to-end.
- **pydantic-settings precedence:** explicit `Settings(session_backend="database")` init kwargs override the conftest `SESSION_BACKEND=memory` env var (init > env), so the database-backend tests select the real path even with the suite-wide memory default in place.

## Testing

- **Flip the xfail:** rewrite `tests/integration/test_pipeline_persistent_session.py` so the persistent-session run **must PASS** (assert `RunStatus.SUCCESS`, `collected == 1`, `new == 1`). Remove the `xfail` branch — a failure is now a real failure. Keep the skip-if-driver-unavailable guard only as a safety net (with greenlet/aiosqlite as runtime deps it should always run).
- **New end-to-end test:** `run_digest(...)` with `session_backend="database"` and a tmp `sqlite_path` (so the session DB lands in tmp) completes a SUCCESS run with injected fakes — proving the *production runtime path* (not just a hand-built Runner) works on the persistent backend.
- **State-delta guard (unit):** a test that drives each mutating stage and asserts the yielded event carries a **non-empty** `state_delta` with the expected keys — guards against silently regressing to direct mutation.
- **Behavior parity:** all existing pipeline/contract/integration tests stay green. The `InMemory` path (`session_backend="memory"`) produces identical outputs/storage writes to today.
- **Test isolation:** a conftest autouse fixture sets `SESSION_BACKEND=memory` for the suite so the hundreds of existing tests stay fast and write no session DB; the two tests above explicitly opt into `"database"` with tmp paths.

## Out of scope (this sub-project)

- Pruning/retention of old session rows in the session DB (note as a future cleanup).
- Firestore session service / Vertex Agent Engine session (that's sub-project C's storage adapter + a possible future session adapter).
- Any change to the business logic inside the proven functions (`process_items`, `adk_critique`, `normalize_and_dedup`, render writers).

## Acceptance

1. `tests/integration/test_pipeline_persistent_session.py` PASSES (no xfail).
2. New end-to-end database-backend `run_digest` test PASSES.
3. State-delta guard test PASSES.
4. Full suite green: `uv run pytest tests/unit tests/integration -q`.
5. Lint clean: `uv run --extra lint ruff check app tests`.
6. A real `run_digest()` with default settings creates a `sessions.db` next to `catchup.db` and finalizes a run identical in content to the pre-refactor behavior.
