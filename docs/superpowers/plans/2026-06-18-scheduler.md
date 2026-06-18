# Scheduler Subsystem Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. **Each task is gated by a Codex review before commit.**

**Goal:** Add opt-in, in-process scheduled digest runs (APScheduler) that share the existing single-flight guard with `POST /api/runs`.

**Architecture:** Extract the single-flight `try_start_run` into a neutral `app/run_trigger.py` (shared by the HTTP endpoint and the scheduler). `app/services/scheduler.py` `build_scheduler(settings, trigger_fn)` returns a not-started `BackgroundScheduler` (cron + timezone) or `None`. A FastAPI lifespan in `create_app` starts/stops it, guarded by `schedule_enabled` (off by default → no scheduler in tests/today). Cloud Scheduler is a documented external-trigger recipe, not code.

**Tech Stack:** Python 3.13, FastAPI lifespan, `apscheduler` (base dep), pytest, `uv`.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-06-18-scheduler-design.md` — authoritative.
- **Commit identity:** `AhmedHeshamSakr <a.hesham1221@gmail.com>`, **NO AI/Claude trailers**.
- **Defaults unchanged:** `schedule_enabled=False` → on-demand only, identical to today. The test suite starts no scheduler.
- **Shared single-flight:** scheduled and manual runs use ONE `threading.Lock` (`app/run_trigger._run_lock`) so they can never double-run on one SQLite file.
- **Offline tests.** Run Python via `uv`. Lint: `uv run --extra lint ruff check app tests`.
- **cost-guard hook:** run pytest/ruff by **directory** (e.g. `tests/unit`), keep `git`/`gh`/`codex` separate — naming GCP-string source files or putting GCP strings in a `uv` command is blocked. (Scheduler files have no GCP strings, but `config.py`/`runner.py` do.)
- **Verify bar (every task ends green):** `uv run pytest tests/unit tests/integration -q` and ruff clean.

---

## File Structure

- `app/core/config.py` — add `schedule_enabled`/`schedule_cron`/`schedule_timezone` (Task 1).
- `pyproject.toml` — `apscheduler` base dep (Task 1).
- `app/run_trigger.py` — **new**; `_run_lock` + `_run_digest_guarded` + `try_start_run` (Task 2).
- `app/api/app.py` — drop the local lock/guard; `trigger_run` uses `try_start_run`; add the scheduler lifespan (Tasks 2, 4).
- `app/services/scheduler.py` — **new**; `build_scheduler` (Task 3).
- `tests/unit/test_run_trigger.py`, `tests/unit/test_scheduler.py` — **new** (Tasks 2, 3).
- `tests/integration/test_api.py` — lifespan tests (Task 4).
- `README.md`, `docs/ADK-GUIDE.md`, `docs/BUILD-LOG.md` — scheduling docs + Cloud Scheduler recipe (Task 5).

---

### Task 1: Settings + `apscheduler` dependency

**Files:**
- Modify: `app/core/config.py` (Settings)
- Modify: `pyproject.toml` (dependencies)
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `Settings.schedule_enabled: bool` (False), `Settings.schedule_cron: str` (""), `Settings.schedule_timezone: str` ("UTC").

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_config.py`:
```python
def test_schedule_defaults(monkeypatch):
    for k in ("SCHEDULE_ENABLED", "SCHEDULE_CRON", "SCHEDULE_TIMEZONE"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    assert s.schedule_enabled is False
    assert s.schedule_cron == ""
    assert s.schedule_timezone == "UTC"


def test_apscheduler_importable():
    import apscheduler  # noqa: F401
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit -q -k "schedule_defaults or apscheduler_importable"`
Expected: FAIL — attributes missing / `apscheduler` not installed.

- [ ] **Step 3: Add the settings**

In `app/core/config.py`, after the `google_cloud_location` field add:
```python
    # Scheduled digest runs (opt-in). When enabled, `catchup serve` runs the
    # digest on schedule_cron (standard 5-field cron) in schedule_timezone.
    # Cloud deploys instead point Cloud Scheduler at POST /api/runs (see docs).
    schedule_enabled: bool = False
    schedule_cron: str = ""
    schedule_timezone: str = "UTC"
```

- [ ] **Step 4: Add the dependency**

In `pyproject.toml` `dependencies`, add:
```toml
    "apscheduler>=3.10,<4.0",
```
Then `uv lock && uv sync` (apscheduler is a base dep, so install it).

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/unit -q -k "schedule_defaults or apscheduler_importable"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py pyproject.toml uv.lock tests/unit/test_config.py
git commit -m "feat(config): schedule settings + apscheduler dependency"
```

---

### Task 2: Extract `app/run_trigger.py` (shared single-flight)

**Files:**
- Create: `app/run_trigger.py`
- Modify: `app/api/app.py` (drop local lock/guard; `trigger_run` uses `try_start_run`; remove now-unused imports)
- Test: `tests/unit/test_run_trigger.py`

**Interfaces:**
- Produces: `try_start_run(settings, *, run_digest_fn=run_digest) -> str | None`; module-level `_run_lock` (threading.Lock).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_run_trigger.py`:
```python
import threading
import time

import pytest

from app.core.config import Settings
from app.run_trigger import _run_lock, try_start_run


@pytest.fixture(autouse=True)
def _ensure_lock_free():
    # best-effort: free a leaked lock so it can't wedge later tests
    yield
    if _run_lock.locked():
        try:
            _run_lock.release()
        except RuntimeError:
            pass


def _s():
    return Settings(_env_file=None)


def test_try_start_run_returns_run_id_and_runs_fn():
    ran = threading.Event()
    seen = {}

    def fake_run(*, settings, run_id):
        seen["run_id"] = run_id
        ran.set()

    rid = try_start_run(_s(), run_digest_fn=fake_run)
    assert rid is not None and len(rid) == 12
    assert ran.wait(timeout=2)
    assert seen["run_id"] == rid


def test_try_start_run_single_flight_returns_none_when_locked():
    # Simulate a run already in flight by holding the lock.
    assert _run_lock.acquire(blocking=False)
    try:
        assert try_start_run(_s(), run_digest_fn=lambda **kw: None) is None
    finally:
        _run_lock.release()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit -q -k run_trigger`
Expected: FAIL — module `app.run_trigger` missing.

- [ ] **Step 3: Create `app/run_trigger.py`**

```python
"""Single-flight digest-run starter, shared by POST /api/runs and the scheduler.

One process-wide lock guards run_digest so a scheduled run and a manual trigger
can never fan out two pipelines onto one SQLite file. (Multi-instance needs a
shared cross-process lock — production milestone.)
"""
from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

from app.core.config import Settings
from app.runner import run_digest

_run_lock = threading.Lock()


def _run_digest_guarded(
    run_digest_fn: Callable[..., object], *, settings: Settings, run_id: str
) -> None:
    try:
        run_digest_fn(settings=settings, run_id=run_id)
    finally:
        _run_lock.release()


def try_start_run(
    settings: Settings, *, run_digest_fn: Callable[..., object] = run_digest
) -> str | None:
    """Start a digest on a daemon thread if none is running; return its run_id,
    or None if a run is already in flight. The lock is released by
    _run_digest_guarded's finally (even on client disconnect)."""
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

- [ ] **Step 4: Rewire `app/api/app.py`**

Remove the module-level `_run_lock = threading.Lock()` and the `_run_digest_guarded` function (the block at lines ~29–41). Add the import (near the other `app.` imports):
```python
from app.run_trigger import try_start_run
```
Replace the `trigger_run` body with:
```python
    @api.post("/runs", status_code=202, dependencies=[require_api_key, rate_limit])
    def trigger_run():
        run_id = try_start_run(settings, run_digest_fn=run_digest_fn)
        if run_id is None:
            raise HTTPException(status_code=409, detail="a digest run is already in progress")
        return {"status": "started", "run_id": run_id}
```
Remove the now-unused `import threading` and `import uuid` from the top of `app/api/app.py` (ruff will flag them otherwise). Keep `from collections.abc import Callable` (still used for the `run_digest_fn` type).

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit tests/integration -q`
Expected: PASS — the new run_trigger tests AND the existing `test_api.py` single-flight (409) / run_id / injected-fn tests (now routed through `try_start_run`). Lint: `uv run --extra lint ruff check app tests` — clean.

- [ ] **Step 6: Commit**

```bash
git add app/run_trigger.py app/api/app.py tests/unit/test_run_trigger.py
git commit -m "refactor(api): extract shared single-flight try_start_run to app/run_trigger.py"
```

---

### Task 3: `app/services/scheduler.py` — `build_scheduler`

**Files:**
- Create: `app/services/scheduler.py`
- Test: `tests/unit/test_scheduler.py`

**Interfaces:**
- Produces: `build_scheduler(settings, trigger_fn: Callable[[], object]) -> BackgroundScheduler | None`.
- Consumes: `Settings.schedule_*` (Task 1).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_scheduler.py`:
```python
import logging

import pytest

from app.core.config import Settings
from app.services.scheduler import build_scheduler


def _s(**kw):
    return Settings(_env_file=None, **kw)


def test_disabled_returns_none():
    assert build_scheduler(_s(schedule_enabled=False), lambda: "x") is None


def test_empty_cron_returns_none():
    assert build_scheduler(_s(schedule_enabled=True, schedule_cron=""), lambda: "x") is None


def test_enabled_has_one_cron_job():
    from apscheduler.triggers.cron import CronTrigger
    sched = build_scheduler(_s(schedule_enabled=True, schedule_cron="0 7 * * *"), lambda: "x")
    assert sched is not None
    jobs = sched.get_jobs()
    assert len(jobs) == 1
    assert isinstance(jobs[0].trigger, CronTrigger)


def test_bad_cron_raises():
    with pytest.raises(ValueError):
        build_scheduler(_s(schedule_enabled=True, schedule_cron="not a cron"), lambda: "x")


def test_job_calls_trigger_fn():
    calls = []
    def fake_trigger():
        calls.append(1)
        return "runid1234567"  # truthy run_id → no skip log
    sched = build_scheduler(_s(schedule_enabled=True, schedule_cron="0 7 * * *"), fake_trigger)
    sched.get_jobs()[0].func()   # invoke the registered job directly (scheduler not started)
    assert calls == [1]


def test_job_logs_skip_when_run_in_progress(caplog):
    sched = build_scheduler(_s(schedule_enabled=True, schedule_cron="0 7 * * *"), lambda: None)
    with caplog.at_level(logging.INFO):
        sched.get_jobs()[0].func()
    assert any("skipped" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit -q -k scheduler`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `build_scheduler`**

Create `app/services/scheduler.py`:
```python
"""In-process digest scheduler (APScheduler) for `catchup serve`.

build_scheduler returns a NOT-started BackgroundScheduler (the caller .start()s
and .shutdown()s it) or None when scheduling is disabled/unconfigured. The job
calls trigger_fn (the single-flight starter), which spawns its own daemon
thread, so the scheduler thread never blocks on a digest.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from app.core.config import Settings

log = logging.getLogger(__name__)


def build_scheduler(settings: Settings, trigger_fn: Callable[[], object]):
    if not settings.schedule_enabled:
        return None
    if not settings.schedule_cron:
        log.warning("schedule_enabled but schedule_cron is empty; no schedule set")
        return None

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    def _job() -> None:
        if trigger_fn() is None:
            log.info("scheduled digest skipped — a run is already in progress")

    scheduler = BackgroundScheduler(timezone=settings.schedule_timezone)
    trigger = CronTrigger.from_crontab(
        settings.schedule_cron, timezone=settings.schedule_timezone
    )
    scheduler.add_job(_job, trigger, id="digest", replace_existing=True)
    return scheduler
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit -q -k scheduler`
Expected: PASS (6 tests).
> If `get_jobs()` returns empty before `start()` in the installed APScheduler, instead build with `scheduler.start(paused=True)` inside `build_scheduler` only for inspection — but prefer the not-started form; verify against the installed version.

- [ ] **Step 5: Commit**

```bash
git add app/services/scheduler.py tests/unit/test_scheduler.py
git commit -m "feat(scheduler): build_scheduler — cron-driven APScheduler over the single-flight trigger"
```

---

### Task 4: FastAPI lifespan wiring in `create_app`

**Files:**
- Modify: `app/api/app.py` (`create_app` — add lifespan)
- Test: `tests/integration/test_api.py`

**Interfaces:**
- Consumes: `build_scheduler` (Task 3), `try_start_run` (Task 2).
- Produces: `app.state.scheduler` (a running `BackgroundScheduler` or `None`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/integration/test_api.py` (reuse the file's `_runs_settings(tmp_path)` helper; if it doesn't set schedule fields, build a fresh `Settings(...)` with the same tmp paths plus the schedule kwargs):
```python
def test_scheduler_starts_when_enabled(tmp_path):
    from fastapi.testclient import TestClient
    from app.core.config import Settings
    cfg = _runs_settings(tmp_path)  # has sqlite_path/config_dir/output_dir
    settings = Settings(
        _env_file=None, schedule_enabled=True, schedule_cron="0 7 * * *",
        sqlite_path=cfg.sqlite_path, config_dir=cfg.config_dir, output_dir=cfg.output_dir,
    )
    app = create_app(settings, run_digest_fn=lambda **kw: None)
    with TestClient(app):
        assert app.state.scheduler is not None
        assert app.state.scheduler.running


def test_scheduler_absent_by_default(tmp_path):
    from fastapi.testclient import TestClient
    app = create_app(_runs_settings(tmp_path), run_digest_fn=lambda **kw: None)
    with TestClient(app):
        assert app.state.scheduler is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/integration -q -k scheduler`
Expected: FAIL — `app.state.scheduler` not set (no lifespan).

- [ ] **Step 3: Add the lifespan to `create_app`**

In `app/api/app.py`, add `from contextlib import asynccontextmanager` (top) and `from app.services.scheduler import build_scheduler` (with the other `app.` imports). Rewrite `create_app`:
```python
def create_app(
    settings: Settings | None = None,
    *,
    run_digest_fn: Callable[..., object] = run_digest,
    resolve_channel_id_fn: Callable[..., object] = youtube_resolve.resolve_channel_id,
    discover_feed_fn: Callable[..., object] = feed_discovery.discover_feed,
) -> FastAPI:
    """Standalone product API (run by ``catchup serve``)."""
    settings = settings or Settings()

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        scheduler = build_scheduler(
            settings, lambda: try_start_run(settings, run_digest_fn=run_digest_fn)
        )
        if scheduler is not None:
            scheduler.start()
        app.state.scheduler = scheduler
        try:
            yield
        finally:
            if app.state.scheduler is not None:
                app.state.scheduler.shutdown(wait=False)

    app = FastAPI(title="Catch-Up API", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_product_routes(
        app, settings,
        run_digest_fn=run_digest_fn,
        resolve_channel_id_fn=resolve_channel_id_fn,
        discover_feed_fn=discover_feed_fn,
    )
    return app
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit tests/integration -q`
Expected: PASS — the two lifespan tests + the whole suite (default-off → no scheduler in the other tests). Lint clean.

- [ ] **Step 5: Commit**

```bash
git add app/api/app.py tests/integration/test_api.py
git commit -m "feat(api): start the digest scheduler in create_app's lifespan (opt-in)"
```

---

### Task 5: Docs + final verification

**Files:**
- Modify: `README.md`, `docs/ADK-GUIDE.md`, `docs/BUILD-LOG.md`

- [ ] **Step 1: Document scheduling**

In `README.md` and `docs/ADK-GUIDE.md` add a short scheduling section: `schedule_enabled`/`schedule_cron`/`schedule_timezone`; with `catchup serve` the digest runs on the cron in-process (shares the single-flight with manual `POST /api/runs`). Include the **Cloud Scheduler recipe** (no in-process code) for production:
```bash
gcloud scheduler jobs create http catchup-digest \
  --schedule="0 7 * * *" --time-zone="UTC" \
  --uri="https://<host>/api/runs" --http-method=POST \
  --headers="X-API-Key=<key>"
```

- [ ] **Step 2: Append a BUILD-LOG entry**

Add a `### Phase: Scheduler subsystem — sub-project B ✅` entry summarizing: shared `try_start_run` (`app/run_trigger.py`) used by both the HTTP endpoint and the scheduler; `build_scheduler` (cron/timezone, disabled/empty→None, skip-log on in-flight); `create_app` lifespan (opt-in, off in tests); `apscheduler` base dep; Cloud Scheduler = documented recipe. Note the manual key-rotation TODO is still open.

- [ ] **Step 3: Final verification**

Run each and confirm green:
```bash
uv run pytest tests/unit tests/integration -q
uv run --extra lint ruff check app tests
```
Expected: all pass; lint clean; `create_app(Settings())` (defaults) starts no scheduler.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/ADK-GUIDE.md docs/BUILD-LOG.md
git commit -m "docs: scheduling (schedule_cron) + Cloud Scheduler recipe"
```

---

## Self-Review

**1. Spec coverage:**
- `schedule_enabled`/`schedule_cron`/`schedule_timezone` settings → Task 1. ✓
- Shared `try_start_run` in a neutral module → Task 2. ✓
- `build_scheduler` (cron, timezone, disabled/empty→None, fail-fast, skip-log) → Task 3. ✓
- FastAPI lifespan start/stop, guarded, off by default → Task 4. ✓
- `apscheduler` base dep → Task 1. ✓
- Cloud Scheduler documented recipe → Task 5. ✓
- Existing single-flight (409) tests preserved → Task 2 (routed through `try_start_run`). ✓
- Scheduled+manual share one lock → Task 2 (`_run_lock`) + Task 4 (lifespan trigger_fn → try_start_run). ✓

**2. Placeholder scan:** No "TBD"/"handle errors"/"similar to". The Task 3 note about `get_jobs()` pre-start is a verify-against-installed-version caveat with a concrete fallback, not a placeholder.

**3. Type consistency:** `try_start_run(settings, *, run_digest_fn=run_digest) -> str | None` used identically in run_trigger.py, api/app.py trigger_run, and the lifespan trigger_fn. `build_scheduler(settings, trigger_fn) -> BackgroundScheduler | None` consistent across Task 3/4. `_run_lock` name shared (run_trigger.py + its test). `app.state.scheduler` set in Task 4, asserted in its tests.
