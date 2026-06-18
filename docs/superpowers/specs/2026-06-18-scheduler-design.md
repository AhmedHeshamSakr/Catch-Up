# Scheduler Subsystem — Design

**Date:** 2026-06-18
**Sub-project:** B (third of the 4-subsystem post-remediation milestone: D durable state ✅ → C Firestore/Vertex ✅ → **B scheduler** → A console screens)
**Status:** Design — awaiting user spec review before plan.

## Goal

Add in-process scheduled digest runs (the README advertises scheduling; it does not exist — the product is on-demand only). Built for the local/self-hosted target with **APScheduler**, sharing the existing single-flight guard so scheduled and manual runs can't overlap. Cloud Scheduler is the documented production alternative (an external trigger of the existing `POST /api/runs`), not in-process code.

## Constraints / context

- **Single-flight already exists** in `app/api/app.py`: a module-level `_run_lock` (`threading.Lock`) + `_run_digest_guarded(run_digest_fn, *, settings, run_id)` (releases in `finally`); `trigger_run` acquires non-blocking (409 if held) and spawns a daemon thread. The scheduler MUST reuse this exact lock.
- **`catchup serve`** runs `uvicorn.run(create_app())`; `create_app` currently has no lifespan.
- **Defaults unchanged:** scheduling is opt-in (`schedule_enabled=False`), so the test suite and existing deployments behave exactly as today.
- **Offline tests:** the scheduler is tested via an injectable `trigger_fn` and by inspecting a not-started `BackgroundScheduler`; no real time passes.

## Architecture

### 1. Settings (`app/core/config.py`)

```python
# Scheduled digest runs (opt-in). When enabled, `catchup serve` runs the digest
# on `schedule_cron` (standard 5-field cron) in `schedule_timezone`. Cloud
# deploys instead point Cloud Scheduler at POST /api/runs (see docs).
schedule_enabled: bool = False
schedule_cron: str = ""          # e.g. "0 7 * * *" = daily 07:00
schedule_timezone: str = "UTC"
```

### 2. Shared single-flight trigger — `app/run_trigger.py` (new)

Extract the single-flight out of `api/app.py` into a neutral module so both the HTTP endpoint and the scheduler use ONE lock without an api↔scheduler import cycle:

```python
import threading, uuid
from collections.abc import Callable
from app.core.config import Settings
from app.runner import run_digest

_run_lock = threading.Lock()


def _run_digest_guarded(run_digest_fn: Callable[..., object], *, settings: Settings, run_id: str) -> None:
    try:
        run_digest_fn(settings=settings, run_id=run_id)
    finally:
        _run_lock.release()


def try_start_run(settings: Settings, *, run_digest_fn: Callable[..., object] = run_digest) -> str | None:
    """Start a digest on a daemon thread if none is running. Returns the run_id,
    or None if a run is already in flight (single-flight). The lock is released by
    _run_digest_guarded's finally, even on client disconnect."""
    if not _run_lock.acquire(blocking=False):
        return None
    run_id = uuid.uuid4().hex[:12]
    threading.Thread(
        target=_run_digest_guarded,
        kwargs={"run_digest_fn": run_digest_fn, "settings": settings, "run_id": run_id},
        daemon=True,
    ).start()
    return run_id
```

`api/app.py`: delete the local `_run_lock`/`_run_digest_guarded`; `trigger_run` becomes:
```python
run_id = try_start_run(settings, run_digest_fn=run_digest_fn)
if run_id is None:
    raise HTTPException(status_code=409, detail="a digest run is already in progress")
return {"status": "started", "run_id": run_id}
```
Behavior is identical (existing 409 / run_id / injected-fn tests keep passing).

### 3. Scheduler module — `app/services/scheduler.py` (new)

```python
def build_scheduler(settings, trigger_fn) -> "BackgroundScheduler | None":
    if not settings.schedule_enabled:
        return None
    if not settings.schedule_cron:
        log.warning("schedule_enabled but schedule_cron is empty; no schedule set")
        return None
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    scheduler = BackgroundScheduler(timezone=settings.schedule_timezone)
    trigger = CronTrigger.from_crontab(settings.schedule_cron, timezone=settings.schedule_timezone)
    scheduler.add_job(trigger_fn, trigger, id="digest", replace_existing=True)
    return scheduler  # NOT started — caller starts/stops it
```
- Returns `None` (no scheduling) when disabled or cron empty. Invalid cron → `from_crontab` raises `ValueError` (fail fast).
- `trigger_fn` is the injectable boundary; production passes `lambda: try_start_run(settings, run_digest_fn=run_digest_fn)`. The job calls `try_start_run`, which spawns its own daemon thread and returns immediately — the scheduler thread never blocks on a digest. When a run is already in flight, `try_start_run` returns `None`; the scheduler wraps the job to log "skipped — run already in progress" in that case.

### 4. Serve wiring — FastAPI lifespan in `create_app`

`create_app` gains an `@asynccontextmanager` lifespan (closure over `settings`/`run_digest_fn`):
- **startup:** `scheduler = build_scheduler(settings, lambda: try_start_run(settings, run_digest_fn=run_digest_fn))`; `if scheduler: scheduler.start()`; store `app.state.scheduler = scheduler`.
- **shutdown:** `if app.state.scheduler: app.state.scheduler.shutdown(wait=False)`.
- Guarded by `schedule_enabled` (default off) → the test suite and the no-schedule deploy start no scheduler. Only `create_app` gets the lifespan; `app/fast_api_app.py` (the ADK deploy surface) stays scheduler-free (Cloud deploys use Cloud Scheduler → the HTTP endpoint).

### 5. Dependency

`apscheduler` (>=3.10,<4.0) added to **base** `dependencies` in `pyproject.toml` (it's the primary scheduler for the target); `uv lock` updates `uv.lock`.

### 6. Docs

- README + `docs/ADK-GUIDE.md`: scheduling is now real (`schedule_enabled`/`schedule_cron`/`schedule_timezone`, runs in `catchup serve`).
- A **Cloud Scheduler recipe** (no code): `gcloud scheduler jobs create http catchup-digest --schedule="0 7 * * *" --uri="https://<host>/api/runs" --http-method=POST --headers="X-API-Key=…"` — the prod alternative that triggers the existing single-flight endpoint.

## Testing (offline)

- **`test_run_trigger.py`:** `try_start_run` returns a 12-hex id when free; returns `None` when the lock is already held (simulate by pre-acquiring `_run_lock` or by a blocking injected `run_digest_fn`); the spawned run calls the injected `run_digest_fn`.
- **`test_scheduler.py`:** `build_scheduler` → enabled+cron yields a scheduler with one job whose trigger is a `CronTrigger`; disabled → `None`; enabled+empty-cron → `None` (+ warning); bad cron → raises; invoking the registered job's `func` calls the injected `trigger_fn`; the skip-logging wrapper logs when `trigger_fn` returns `None`.
- **`test_api.py`:** existing single-flight (409) / run_id / injected-fn tests still pass via the extracted `try_start_run`. Add a lifespan test: `create_app(settings(schedule_enabled=True, schedule_cron="0 7 * * *"))` under a `TestClient` context → `app.state.scheduler` is running; default-off → `app.state.scheduler is None`. (The daily cron won't fire during the test.)
- Full backend suite + ruff stay green; the conftest's `SESSION_BACKEND=memory` + default `schedule_enabled=False` mean no background scheduler runs in the suite.

## Out of scope

- A Cloud Scheduler in-process adapter (it's an external HTTP trigger — documented recipe only).
- The "Runs & Schedule" console screen (sub-project A).
- Multi-instance / distributed scheduling and a shared cross-process lock (production milestone; the single-flight is per-process, as today).
- Persisting schedule state / a jobstore (in-memory APScheduler; the cron is config-driven, recreated on each `serve`).

## Acceptance

1. With `schedule_enabled=True` + a valid `schedule_cron`, `catchup serve` starts a `BackgroundScheduler` that calls `try_start_run` on the cron cadence; with defaults, no scheduler starts.
2. Scheduled and manual `POST /api/runs` share one lock — a scheduled run while one is in flight is skipped (logged), never a second concurrent pipeline.
3. `build_scheduler`/`try_start_run` unit tests + the lifespan test pass; existing API single-flight tests still pass.
4. Full backend suite green: `uv run pytest tests/unit tests/integration -q`; ruff clean.
5. Defaults unchanged: no new settings → on-demand-only, identical to today.
