# Critical & Medium Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every verified critical and medium defect from the 2026-06-17 deep review — deployment, eval-gate, CORS, auth, concurrency, SSRF, dedup, and the two YouTube bugs — without regressing the existing suite.

**Architecture:** Surgical fixes that follow existing patterns. The biggest structural change is factoring the product `/api/*` routes into a reusable router so the *single deployable container* serves them (today it serves only the ADK agent surface). Everything else is local hardening with a test added first.

**Tech Stack:** Python 3.12, FastAPI, pydantic-settings, SQLite (`sqlite3`), httpx, ADK; Next.js 16 / React 19 + Vitest for the frontend.

## Global Constraints

- **Code preservation (CLAUDE.md):** Only modify code targeted by a task. Preserve surrounding code, config values, comments, formatting. **NEVER change the `llm_model` value** or any model id.
- **Commit identity:** commit as `AhmedHeshamSakr <a.hesham1221@gmail.com>`. **No Claude/AI co-author signatures in commits.**
- **Run Python with uv:** `uv run pytest ...`, `uv run python ...`. Backend tests need no API key.
- **Frontend (`frontend/AGENTS.md`):** This Next.js has breaking changes vs training data — read `node_modules/next/dist/docs/` before writing frontend code.
- **TDD:** every task writes the failing test first, watches it fail, implements minimally, watches it pass, commits.
- **Stop on repeated errors:** if the same error appears 3+ times, fix the root cause; don't retry.

---

## Plan-review corrections — Codex, 2026-06-17 (THESE SUPERSEDE TASK TEXT BELOW)

A Codex review of this plan flagged the following. Apply these — they override the original task bodies where they conflict:

- **Whisper feature is being REMOVED (user decision).** Task 11 is now *"Remove the Whisper transcription feature"* (delete the fallback in `youtube.py`, the `youtube_whisper_enabled`/`whisper_model` settings, the `[whisper]` extra in `pyproject.toml`, and the README mention). The old "fix the audio path" task is void.
- **Task 10 (SSRF): `httpx.get(extensions=…)` does NOT exist in httpx 0.28.1** — it raises `TypeError`. Use `httpx.Client(...).build_request("GET", url, headers=, params=, extensions={"sni_hostname": host})` then `client.send(request)`. `httpx.URL.copy_with(host=ip)` works for IPv4/IPv6. `Host` header must keep the original port (`host:port` when non-default); SNI uses the bare hostname. `validate_public_url` has no production callers outside `safe_get`, but `tests/unit/test_net.py` asserts its old `str` return — update those expectations. (Corrected code in Task 10 below.)
- **Task 1 (deploy): unify the CORS origin allowlist with ADK's middleware.** ADK's `get_fast_api_app` installs its own `_OriginCheckMiddleware`; a second `CORSMiddleware` won't update it. In `fast_api_app.py`, parse origins ONCE into `Settings().allow_origins` and pass that same list to `get_fast_api_app(allow_origins=…)` AND to `register_product_api`. Also: **`Dockerfile:23` copies `./app` but not `./config`** → deployed `/api/sources` & `/api/watchlist` fail. Add `COPY ./config ./config`. Strengthen the test to drive `app.fast_api_app:app` and assert a real `/api/*` route exists.
- **Task 2 (eval): regression condition is `candidate_pass_rate < baseline_pass_rate`** (a strict drop), NOT `< 1.0` — otherwise an improvement from a sub-1.0 baseline is falsely flagged. Code below corrected.
- **Task 4 (run_id): add a real concurrent single-flight test** — `TestClient` runs background tasks synchronously, so the `run_id` test alone can't prove 409. Use a fake `run_digest_fn` that blocks on a `threading.Event` and fire two requests from threads; assert exactly one 202 and one 409.
- **Task 5 (auth): an existing test (`tests/integration/test_api.py` ~line 393) asserts GET routes stay open when `api_key` is set.** Task 5 intentionally changes that — UPDATE/replace that test. Broaden the new test to assert 401-without-key on every read route (`/dashboard`, `/runs`, `/runs/{id}`, `/news`, `/sources`, `/watchlist`), `/health` staying open.
- **Task 6 (config writes): use a single `threading.RLock` held across the whole read-modify-write** (load → mutate → atomic replace), not just around the write — otherwise two writers both read the pre-image and one update is lost.
- **Task 7 (SQLite): the real defect is `journal_mode` (rollback, not WAL).** `busy_timeout` is already ~5000ms because `sqlite3.connect` defaults `timeout=5.0`. The test must assert `journal_mode == 'wal'` (the thing that's broken); the "busy_timeout is 0" claim in the original step is wrong — drop it.
- **Task 8 (dedup): key the title dedup by `source_id`, not `source_name`** — two distinct sources can share a display name. Test must cover that.
- **Task 13 (frontend): premise corrected.** The button ALREADY says "Digest run started" (not "completed"). Narrow the task to: surface the returned `run_id` and handle the new **409** ("already in progress") distinctly. Real run-status polling is optional/out-of-scope.

---

## Phase 0 — Security & prerequisites

### Task 0: Rotate exposed keys & lock down `.env`

**Context:** `app/.env` holds a live `GOOGLE_API_KEY` and `GNEWS_API_KEY` in cleartext. This is a manual operator action — no code test, but it gates everything else (do it first).

**Files:**
- Verify: `.gitignore` (must ignore `app/.env` and `.env`)
- Create: `app/.env.example`

- [ ] **Step 1: Confirm `.env` was never committed**

Run: `git log --all --oneline -- app/.env .env` — Expected: no output. If there IS output, the keys are in history → rotate is mandatory and consider history rewrite.

- [ ] **Step 2: Rotate both keys at the provider**

Manual: regenerate `GOOGLE_API_KEY` (Google AI Studio) and `GNEWS_API_KEY` (gnews.io), paste the NEW values into `app/.env`. The old values in the review output are now burned.

- [ ] **Step 3: Confirm `.gitignore` covers env files**

Run: `git check-ignore app/.env .env` — Expected: both paths echoed. If not, add `app/.env` and `.env` to `.gitignore`.

- [ ] **Step 4: Create `app/.env.example` (no secrets)**

```bash
# Copy to app/.env and fill in. NEVER commit app/.env.
GOOGLE_API_KEY=
GNEWS_API_KEY=
# Optional product-API hardening:
API_KEY=
ALLOW_ORIGINS=http://localhost:3000
```

- [ ] **Step 5: Commit**

```bash
git add .gitignore app/.env.example
git commit -m "chore(security): add .env.example, confirm env files gitignored"
```

---

## Phase 1 — Critical defects

### Task 1: Single deployable container serves the product `/api/*` routes

**Problem:** `Dockerfile:35` runs only `app.fast_api_app:app` (ADK web UI + `/feedback`). The product REST API (`/api/dashboard`, `/runs`, `/news`, `/sources`, `/watchlist`, `/resolve`) lives only in `app/api/app.py:create_app()`, run solely by `catchup serve`. A deployed frontend 404s every request. **Fix:** factor the `/api` router + CORS into a reusable `register_product_api()` and call it from both `create_app()` (unchanged behavior) and `fast_api_app.py` (so the container serves both surfaces).

**Files:**
- Modify: `app/api/app.py` (extract router registration)
- Modify: `app/fast_api_app.py` (mount product routes onto the ADK app)
- Test: `tests/integration/test_api.py`, `tests/integration/test_deploy_surface.py` (new)

**Interfaces:**
- Produces: `register_product_api(app: FastAPI, settings: Settings, *, run_digest_fn=..., resolve_channel_id_fn=..., discover_feed_fn=...) -> None` — adds CORS + the `/api` router to an existing `FastAPI`. `create_app(...)` now calls it.

- [ ] **Step 1: Write the failing test** (new file `tests/integration/test_deploy_surface.py`)

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.app import register_product_api
from app.core.config import Settings


def test_register_product_api_adds_health_route(tmp_path):
    app = FastAPI()
    settings = Settings(config_dir=str(tmp_path), sqlite_path=str(tmp_path / "t.db"))
    register_product_api(app, settings)
    client = TestClient(app)
    assert client.get("/api/health").json() == {"status": "ok"}
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/integration/test_deploy_surface.py -v`
Expected: FAIL — `ImportError: cannot import name 'register_product_api'`.

- [ ] **Step 3: Extract the router into `register_product_api` in `app/api/app.py`**

Replace the body of `create_app` so all middleware/route wiring moves into a new function, and `create_app` delegates:

```python
def register_product_api(
    app: FastAPI,
    settings: Settings,
    *,
    run_digest_fn: Callable[..., object] = run_digest,
    resolve_channel_id_fn: Callable[..., object] = youtube_resolve.resolve_channel_id,
    discover_feed_fn: Callable[..., object] = feed_discovery.discover_feed,
) -> None:
    """Attach the product /api/* routes (and their CORS) to an existing app.

    Shared by create_app() (the `catchup serve` standalone API) and
    fast_api_app.py (so the deployed ADK container also serves /api/*).
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api = APIRouter(prefix="/api")
    rate_bucket = TokenBucket(
        rate_per_sec=settings.rate_limit_refill_per_sec,
        capacity=settings.rate_limit_burst,
    )
    require_api_key = Depends(_require_api_key(settings))
    rate_limit = Depends(_rate_limiter(rate_bucket))

    def storage():
        return build_storage(settings)

    # ... MOVE every @api.get/@api.put/@api.post handler here verbatim ...

    app.include_router(api)


def create_app(
    settings: Settings | None = None,
    *,
    run_digest_fn: Callable[..., object] = run_digest,
    resolve_channel_id_fn: Callable[..., object] = youtube_resolve.resolve_channel_id,
    discover_feed_fn: Callable[..., object] = feed_discovery.discover_feed,
) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Catch-Up API", version="0.1.0")
    register_product_api(
        app, settings,
        run_digest_fn=run_digest_fn,
        resolve_channel_id_fn=resolve_channel_id_fn,
        discover_feed_fn=discover_feed_fn,
    )
    return app
```

> Note: `settings.allow_origins` is added in **Task 3** — if you do Task 3 first, use it here; otherwise temporarily keep `["http://localhost:3000"]` and switch in Task 3.

- [ ] **Step 4: Mount product routes onto the ADK app in `app/fast_api_app.py`**

After `app.description = ...` (line ~67), add:

```python
from app.api.app import register_product_api  # noqa: E402
from app.core.config import Settings  # noqa: E402

# Serve the product /api/* routes from the SAME deployed container so a
# deployed frontend (lib/api.ts -> /api/*) reaches a real backend.
register_product_api(app, Settings())
```

- [ ] **Step 5: Run the new test + existing API tests**

Run: `uv run pytest tests/integration/test_deploy_surface.py tests/integration/test_api.py -v`
Expected: PASS (all existing API tests still green — `create_app` behavior is unchanged).

- [ ] **Step 6: Commit**

```bash
git add app/api/app.py app/fast_api_app.py tests/integration/test_deploy_surface.py
git commit -m "fix(deploy): serve product /api routes from the deployable container"
```

---

### Task 2: Regression check must honor the `pass_rate` gate for safety-critical dims

**Problem:** The faithfulness acceptance gate fails on `pass_rate < 1.0` (`eval_score.py:61-63`), but `compare()`/`check_regression` only inspect `dimension_mean_score` with a 0.05 delta (`eval_score.py:114-131`). One new hallucination drops the mean ~0.027 (under 0.05) while `pass_rate` falls to 0.971 → `--check-regression` exits green on a real faithfulness regression.

**Files:**
- Modify: `app/pipeline/eval_score.py` (`compare`)
- Test: `tests/unit/test_eval_score.py`

- [ ] **Step 1: Write the failing test**

```python
from app.pipeline.eval_score import EvalReport, compare


def _report(faith_pass_rate: float, faith_mean: float) -> EvalReport:
    dims = ["faithfulness", "category_accuracy", "importance_calibration", "ar_translation_quality"]
    return EvalReport(
        n=35,
        dimension_pass_rate={d: (faith_pass_rate if d == "faithfulness" else 1.0) for d in dims},
        dimension_mean_score={d: (faith_mean if d == "faithfulness" else 0.95) for d in dims},
        dimension_min_score=dict.fromkeys(dims, 0.0),
        passed=True,
        failures=[],
    )


def test_safety_critical_pass_rate_drop_is_a_regression_even_when_mean_barely_moves():
    baseline = _report(faith_pass_rate=1.0, faith_mean=0.96)
    candidate = _report(faith_pass_rate=0.971, faith_mean=0.933)  # one new hallucination
    result = compare(baseline, candidate)
    assert "faithfulness" in result["regressions"]
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/unit/test_eval_score.py::test_safety_critical_pass_rate_drop_is_a_regression_even_when_mean_barely_moves -v`
Expected: FAIL — `faithfulness` not in regressions (mean drop 0.027 < 0.05).

- [ ] **Step 3: Add pass-rate-aware regression for safety-critical dims in `compare()`**

Replace the loop in `compare` (lines 123-129) with:

```python
    for dim in _DIMENSIONS:
        b = baseline.dimension_mean_score.get(dim, 0.0)
        c = candidate.dimension_mean_score.get(dim, 0.0)
        delta = c - b
        deltas[dim] = round(delta, 6)
        if dim in SAFETY_CRITICAL:
            # Safety-critical dims gate on pass_rate (==1.0), so ANY pass_rate
            # drop is a regression — a mean-only check averages a single
            # hallucination away and ships it. Mirrors _dimension_passes.
            b_pr = baseline.dimension_pass_rate.get(dim, 0.0)
            c_pr = candidate.dimension_pass_rate.get(dim, 0.0)
            if c_pr < b_pr or c_pr < 1.0:
                regressions.append(dim)
        elif delta < -REGRESSION_DELTA:
            regressions.append(dim)
```

- [ ] **Step 4: Run the eval_score tests**

Run: `uv run pytest tests/unit/test_eval_score.py -v`
Expected: PASS (new test green; pre-existing soft-dimension tests still green).

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/eval_score.py tests/unit/test_eval_score.py
git commit -m "fix(eval): flag safety-critical pass_rate drops in regression check"
```

---

### Task 3: Configurable CORS origins (no hardcoded localhost)

**Problem:** `app/api/app.py` hardcodes `allow_origins=["http://localhost:3000"]` with no override; any non-local deploy has its preflight rejected. The other surface reads `ALLOW_ORIGINS` from env — inconsistent.

**Files:**
- Modify: `app/core/config.py` (add `allow_origins` setting)
- Modify: `app/api/app.py` (use it — already referenced in Task 1's `register_product_api`)
- Test: `tests/unit/test_config.py`, `tests/integration/test_api.py`

**Interfaces:**
- Produces: `Settings.allow_origins: list[str]` — defaults to `["http://localhost:3000"]`; parsed from the `ALLOW_ORIGINS` env var as a comma-separated list.

- [ ] **Step 1: Write the failing test** (in `tests/unit/test_config.py`)

```python
def test_allow_origins_parses_comma_separated_env(monkeypatch):
    monkeypatch.setenv("ALLOW_ORIGINS", "https://a.example , https://b.example")
    from app.core.config import Settings
    s = Settings()
    assert s.allow_origins == ["https://a.example", "https://b.example"]


def test_allow_origins_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("ALLOW_ORIGINS", raising=False)
    from app.core.config import Settings
    assert Settings().allow_origins == ["http://localhost:3000"]
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/unit/test_config.py -k allow_origins -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'allow_origins'`.

- [ ] **Step 3: Add the field + parser to `Settings`** (after `api_key`, ~line 84)

```python
    # CORS allowlist for the product API. Comma-separated in the ALLOW_ORIGINS
    # env var; defaults to the local console origin.
    allow_origins: list[str] = ["http://localhost:3000"]

    @field_validator("allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value
```

Add `field_validator` to the existing pydantic import at the top if not already imported in this module (`from pydantic import BaseModel, field_validator` is already present).

- [ ] **Step 4: Use `settings.allow_origins` in `register_product_api`**

In `app/api/app.py`, confirm the `CORSMiddleware` call uses `allow_origins=settings.allow_origins` (set in Task 1 Step 3).

- [ ] **Step 5: Run config + API tests**

Run: `uv run pytest tests/unit/test_config.py tests/integration/test_api.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py app/api/app.py tests/unit/test_config.py
git commit -m "fix(api): make CORS origins configurable via ALLOW_ORIGINS"
```

---

## Phase 2 — API robustness & auth

### Task 4: `POST /api/runs` returns a `run_id` and is single-flight

**Problem:** `trigger_run` schedules a blocking `run_digest` into the threadpool with no mutual exclusion (up to ~burst pipelines concurrently hammer one SQLite file) and returns `{status: "started"}` with no `run_id`, so the UI can't poll the run it launched.

**Files:**
- Modify: `app/runner.py` (accept an injected `run_id`)
- Modify: `app/api/app.py` (`trigger_run`: generate id, single-flight guard, return id)
- Test: `tests/integration/test_api.py`

**Interfaces:**
- Consumes: `run_digest(settings=..., ..., run_id: str | None = None)` — when provided, the run uses this id (seeded into the pipeline session state) instead of generating its own.
- Produces: `POST /api/runs` → `202 {"status": "started", "run_id": "<hex12>"}`, or `409 {"detail": "a digest run is already in progress"}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_trigger_run_returns_run_id(client_factory):
    calls = {}
    def fake_run(*, settings, run_id=None, **kw):
        calls["run_id"] = run_id
    client = client_factory(run_digest_fn=fake_run)
    r = client.post("/api/runs")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "started"
    assert isinstance(body["run_id"], str) and len(body["run_id"]) == 12
```

> If `tests/integration/test_api.py` lacks a `client_factory` fixture that forwards `run_digest_fn`, add one that calls `create_app(settings, run_digest_fn=...)` wrapped in `TestClient`. Background tasks in `TestClient` run synchronously after the response, so `calls["run_id"]` is set by assertion time.

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/integration/test_api.py -k trigger_run_returns_run_id -v`
Expected: FAIL — response has no `run_id`.

- [ ] **Step 3: Let `run_digest` accept an injected `run_id`** (`app/runner.py`)

Change the signature (line 97) to add `run_id: str | None = None`, and line 111 to:

```python
    run_id = run_id or uuid.uuid4().hex[:12]
```

- [ ] **Step 4: Single-flight guard + id in `trigger_run`** (`app/api/app.py`)

Add near the top of the module (after imports):

```python
import threading
import uuid

_run_lock = threading.Lock()


def _run_digest_guarded(run_digest_fn, *, settings, run_id):
    # Hold the single-flight lock for the whole run so concurrent triggers 409.
    try:
        run_digest_fn(settings=settings, run_id=run_id)
    finally:
        _run_lock.release()
```

Replace `trigger_run` (lines 153-156) with:

```python
    @api.post("/runs", status_code=202, dependencies=[require_api_key, rate_limit])
    def trigger_run(background: BackgroundTasks):
        if not _run_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="a digest run is already in progress")
        run_id = uuid.uuid4().hex[:12]
        background.add_task(
            _run_digest_guarded, run_digest_fn, settings=settings, run_id=run_id
        )
        return {"status": "started", "run_id": run_id}
```

> The lock is released in `_run_digest_guarded`'s `finally`. Document in a comment that this is per-process (not multi-instance) — true cross-instance locking is the separate production milestone.

- [ ] **Step 5: Run API tests**

Run: `uv run pytest tests/integration/test_api.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/runner.py app/api/app.py tests/integration/test_api.py
git commit -m "fix(api): POST /runs returns run_id and is single-flight"
```

---

### Task 5: End-to-end API key — backend enforces on all routes when set; frontend can send it

**Problem:** `api_key` defaults to `None` (fail-open; read endpoints have *no* auth dependency at all). If an operator sets it, the frontend has no way to send it, so every mutation 401s. Result: API is either fully open or breaks the console.

**Files:**
- Modify: `app/api/app.py` (apply `require_api_key` to read routes too; warn when unset)
- Modify: `frontend/lib/api.ts` (send `X-API-Key` when configured)
- Create: docs note in `frontend/.env.local.example`
- Test: `tests/integration/test_api.py`, `frontend/lib/api.test.ts`

- [ ] **Step 1: Write the failing backend test**

```python
def test_read_endpoints_require_key_when_configured(client_factory):
    client = client_factory(api_key="secret123")
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/dashboard", headers={"X-API-Key": "secret123"}).status_code == 200
```

> Extend `client_factory` to accept `api_key=...` and pass `Settings(api_key=...)`. `/api/health` must stay public (liveness).

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/integration/test_api.py -k read_endpoints_require_key -v`
Expected: FAIL — `/api/dashboard` returns 200 without a key.

- [ ] **Step 3: Apply `require_api_key` to read routes; warn when unset**

In `register_product_api`, after building `require_api_key`, add a startup warning:

```python
    if not settings.api_key:
        logger.warning(
            "API_KEY is unset — the product API is OPEN (no auth). "
            "Set API_KEY for any non-local deployment."
        )
```

Add `dependencies=[require_api_key]` to `dashboard`, `list_runs`, `get_run`, `list_news`, `get_sources`, `get_watchlist` (leave `/api/health` open). Example:

```python
    @api.get("/dashboard", response_model=DashboardOut, dependencies=[require_api_key])
    def dashboard() -> DashboardOut:
        ...
```

> `_require_api_key` is already a no-op when `api_key` is unset, so local/dev behavior is unchanged.

- [ ] **Step 4: Run backend tests**

Run: `uv run pytest tests/integration/test_api.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing frontend test** (`frontend/lib/api.test.ts`)

```ts
it("sends X-API-Key when NEXT_PUBLIC_API_KEY is set", async () => {
  process.env.NEXT_PUBLIC_API_KEY = "secret123";
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } })
  );
  vi.stubGlobal("fetch", fetchMock);
  const { api } = await import("@/lib/api");
  await api.getSources();
  const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
  expect(headers["X-API-Key"]).toBe("secret123");
});
```

- [ ] **Step 6: Run it to confirm it fails**

Run: `cd frontend && npx vitest run lib/api.test.ts -t "sends X-API-Key"`
Expected: FAIL — header absent.

- [ ] **Step 7: Send the key from the api client** (`frontend/lib/api.ts`, in `request`)

```ts
  const base = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const res = await fetch(base + path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(apiKey ? { "X-API-Key": apiKey } : {}),
      ...(init?.headers ?? {}),
    },
  });
```

Append to `frontend/.env.local.example`:

```bash
# Optional: only for trusted/internal deploys. This key IS exposed to the
# browser (NEXT_PUBLIC_*). Real per-user auth is a separate milestone.
NEXT_PUBLIC_API_KEY=
```

- [ ] **Step 8: Run frontend tests**

Run: `cd frontend && npm test`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/api/app.py frontend/lib/api.ts frontend/lib/api.test.ts frontend/.env.local.example
git commit -m "fix(auth): enforce API key on all routes when set; frontend sends X-API-Key"
```

---

### Task 6: Atomic, locked config writes (`PUT /sources`, `/watchlist`)

**Problem:** `config_store.write_sources/write_watchlist` do truncating read-modify-write with no locking → lost updates and torn reads (a concurrent reader/run can see a half-written file).

**Files:**
- Modify: `app/services/config_store.py`
- Test: `tests/unit/test_config_store.py`

- [ ] **Step 1: Write the failing test**

```python
import threading
from app.services import config_store
from app.core.config import SourceConfig, load_sources


def test_concurrent_writes_never_leave_a_corrupt_file(tmp_path):
    base = [SourceConfig(id="a", type="rss", name="A", url="https://a.example/feed")]
    config_store.write_sources(tmp_path, base)

    def writer(n):
        config_store.write_sources(
            tmp_path,
            [SourceConfig(id=f"s{n}", type="rss", name=str(n), url="https://x.example/feed")],
        )

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()
    # File must always parse (no torn write) after the storm.
    assert load_sources(tmp_path)  # raises if YAML is corrupt
```

- [ ] **Step 2: Run it to confirm it fails (flakily)**

Run: `uv run pytest tests/unit/test_config_store.py -k concurrent_writes -v`
Expected: FAIL intermittently (`yaml` parse error / empty list) under the write storm.

- [ ] **Step 3: Add a process lock + atomic replace** (`app/services/config_store.py`)

```python
import os
import threading

_write_lock = threading.Lock()


def _atomic_write(path: Path, render) -> None:
    """Serialize writers and replace atomically so readers never see a torn file."""
    with _write_lock:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            render(fh)
        os.replace(tmp, path)  # atomic on POSIX & Windows
```

Rewrite the tail of `write_sources`:

```python
    def render(fh):
        yml.dump(data, fh)
    _atomic_write(path, render)
```

And `write_watchlist`:

```python
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    _atomic_write(path, lambda fh: fh.write(text))
```

> Keep the `_write_lock` held across the read-modify-write in `write_sources` (move the `yml.load(...)` inside the lock) so two writers can't both read the pre-image and lose one update. Adjust the function so the load happens within `_atomic_write`'s lock, or wrap the whole body in `with _write_lock:` and have `_atomic_write` assume the lock is held (use a reentrant `threading.RLock`).

- [ ] **Step 4: Run config_store tests**

Run: `uv run pytest tests/unit/test_config_store.py -v`
Expected: PASS (run a few times to confirm non-flaky).

- [ ] **Step 5: Commit**

```bash
git add app/services/config_store.py tests/unit/test_config_store.py
git commit -m "fix(config): atomic, lock-guarded sources/watchlist writes"
```

---

## Phase 3 — Data layer

### Task 7: SQLite WAL + busy_timeout

**Problem:** `_conn()` uses default `sqlite3.connect` (no `busy_timeout`, rollback journaling). Background runs write while read endpoints read the same file → intermittent unhandled `SQLITE_BUSY` 500s.

**Files:**
- Modify: `app/adapters/storage/sqlite_backend.py`
- Test: `tests/unit/test_sqlite_backend.py`

- [ ] **Step 1: Write the failing test**

```python
def test_conn_enables_wal_and_busy_timeout(tmp_path):
    from app.adapters.storage.sqlite_backend import SqliteBackend
    be = SqliteBackend(str(tmp_path / "t.db"))
    be.init_schema()
    with be._conn() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/unit/test_sqlite_backend.py -k wal_and_busy_timeout -v`
Expected: FAIL — journal_mode is `delete`, busy_timeout is `0`.

- [ ] **Step 3: Set the PRAGMAs in `_conn()`**

```python
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        # WAL lets readers and a single writer proceed concurrently; busy_timeout
        # makes a contending connection wait instead of erroring SQLITE_BUSY.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn
```

- [ ] **Step 4: Run storage tests (full suite — WAL changes file behavior)**

Run: `uv run pytest tests/unit/test_sqlite_backend.py tests/unit/storage_contract.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/adapters/storage/sqlite_backend.py tests/unit/test_sqlite_backend.py
git commit -m "fix(storage): enable SQLite WAL + busy_timeout to avoid SQLITE_BUSY 500s"
```

---

### Task 8: Source-aware, observable title dedup

**Problem:** `normalize_and_dedup` uses one run-wide lowercased-title set that collapses ANY two items sharing a generic headline ("Market Update") across sources, silently and order-dependently.

**Files:**
- Modify: `app/services/normalize.py`
- Test: `tests/unit/test_normalize.py`

- [ ] **Step 1: Write the failing test**

```python
import logging
from app.core.domain import RawItem, SourceType
from app.services.normalize import normalize_and_dedup


class _NoStore:
    def existing_ids(self, ids): return set()


def test_same_title_from_different_sources_is_kept(caplog):
    raws = [
        RawItem(title="Market Update", url="https://a.example/1", source_id="a",
                source_name="A", source_type=SourceType.RSS),
        RawItem(title="Market Update", url="https://b.example/2", source_id="b",
                source_name="B", source_type=SourceType.RSS),
    ]
    out = normalize_and_dedup(raws, _NoStore(), run_id="r1")
    assert len(out) == 2  # distinct sources -> both kept


def test_same_title_same_source_is_collapsed_and_logged(caplog):
    raws = [
        RawItem(title="Daily Brief", url="https://a.example/1", source_id="a",
                source_name="A", source_type=SourceType.RSS),
        RawItem(title="Daily Brief", url="https://a.example/2", source_id="a",
                source_name="A", source_type=SourceType.RSS),
    ]
    with caplog.at_level(logging.INFO):
        out = normalize_and_dedup(raws, _NoStore(), run_id="r1")
    assert len(out) == 1
    assert any("dedup" in r.message.lower() for r in caplog.records)
```

> Confirm `RawItem`'s real field names from `app/core/domain.py` and adjust the constructor kwargs to match before running.

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/unit/test_normalize.py -k same_title -v`
Expected: FAIL — first test gets 1 item (cross-source collapse).

- [ ] **Step 3: Make the title key source-aware + log drops** (`app/services/normalize.py`)

```python
import logging

log = logging.getLogger(__name__)


def _norm_title(title: str) -> str:
    return " ".join(title.lower().split())


def normalize_and_dedup(
    raws: list[RawItem], storage: StorageBackend, run_id: str
) -> list[NewsItem]:
    seen_ids: set[str] = set()
    # Title dedup is now keyed by (normalized_title, source_name): it removes
    # intra-feed repeats but NO LONGER collapses distinct same-headline stories
    # from different sources. Cross-source reprint dedup (fuzzy/source-aware) is
    # a later plan. Every collapse is logged so drops are never silent.
    seen_titles: set[tuple[str, str]] = set()
    candidates: list[NewsItem] = []
    for raw in raws:
        item = NewsItem.from_raw(raw, run_id=run_id)
        title_key = (_norm_title(raw.title), raw.source_name)
        if item.id in seen_ids:
            continue
        if title_key in seen_titles:
            log.info("dedup: dropped repeat title %r from source %r", raw.title, raw.source_name)
            continue
        seen_ids.add(item.id)
        seen_titles.add(title_key)
        candidates.append(item)
    already = storage.existing_ids([c.id for c in candidates])
    return [c for c in candidates if c.id not in already]
```

> Use the actual attribute that carries the source name on `RawItem`/`NewsItem` (e.g. `raw.source_name`). Verify in `app/core/domain.py`.

- [ ] **Step 4: Run normalize tests**

Run: `uv run pytest tests/unit/test_normalize.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/normalize.py tests/unit/test_normalize.py
git commit -m "fix(normalize): source-aware title dedup; log every collapse"
```

---

## Phase 4 — Pipeline runtime & SSRF

### Task 9: LLM stages run off the event loop so `run_timeout` can fire

**Problem:** `ProcessingAgent`, `GuardrailCriticAgent`, `DigestEditorAgent` call their LLM functions synchronously inside `_run_async_impl`, parking the event-loop thread, so `asyncio.wait_for(run_timeout)` can't interrupt an in-flight call (the collectors already use `asyncio.to_thread` correctly).

**Files:**
- Modify: `app/pipeline/agents.py` (3 stages)
- Test: `tests/unit/test_pipeline_agents.py`

- [ ] **Step 1: Write the failing test**

```python
import asyncio
import pytest


@pytest.mark.asyncio
async def test_run_timeout_interrupts_a_blocking_processing_stage(make_ctx, settings_factory):
    # A processor that sleeps longer than the run timeout must be interrupted.
    def slow_processor(items):
        import time; time.sleep(2.0); return []

    from app.runner import _run_tree_with_timeout, build_pipeline
    settings = settings_factory(run_timeout=0.3)
    # build a tree whose Processing stage uses slow_processor; seed one item.
    ...
    with pytest.raises(asyncio.TimeoutError):
        await _run_tree_with_timeout(tree, "rid", 0.3)
```

> This needs a tree wired with a slow processor and at least one item in state. If the existing `test_pipeline_agents.py` already has helpers to build a partial tree / drive a single stage, reuse them; otherwise assert the simpler property: the event loop stays responsive — schedule a `asyncio.sleep(0)` ticker task and assert it advances while the stage runs. Pick whichever the existing fixtures support and keep the test deterministic.

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/unit/test_pipeline_agents.py -k run_timeout_interrupts -v`
Expected: FAIL — no `TimeoutError` (loop blocked, `wait_for` never fires).

- [ ] **Step 3: Offload the blocking LLM calls** (`app/pipeline/agents.py`)

`ProcessingAgent._run_async_impl` — wrap `process_items`:

```python
            batch_errors = await asyncio.to_thread(
                process_items,
                items,
                self.processor,
                watchlist,
                self.settings.importance_threshold,
                self.settings.llm_batch_size,
            )
```

`GuardrailCriticAgent._run_async_impl` — `select_for_critique` is cheap (leave sync); offload the LLM-bearing branch:

```python
            if selected:
                if self.settings.critic_max_reflections > 0:
                    outcome = await asyncio.to_thread(
                        reflect_and_correct,
                        selected, self.critic, self.reprocessor, watchlist, self.settings,
                    )
                else:
                    verdicts = await asyncio.to_thread(self.critic, selected)
                    outcome = apply_verdicts(
                        selected, verdicts,
                        self.settings.critic_action, self.settings.importance_threshold,
                    )
```

`DigestEditorAgent._run_async_impl`:

```python
            run.narrative = (
                await asyncio.to_thread(self.narrator, rendered) if rendered else None
            )
```

> `asyncio` is already imported in this module. Inside the worker thread, `run_agent_text`'s `_run_coro_sync` sees no running loop and uses `asyncio.run` directly (removing the previous nested-thread hop).

- [ ] **Step 4: Run pipeline-agent tests**

Run: `uv run pytest tests/unit/test_pipeline_agents.py tests/integration/test_pipeline_tree.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/agents.py tests/unit/test_pipeline_agents.py
git commit -m "fix(pipeline): run LLM stages via asyncio.to_thread so run_timeout can interrupt"
```

---

### Task 10: SSRF guard pins the validated IP (close the DNS-rebinding/TOCTOU window)

**Problem:** `safe_get` validates the hostname's resolved IPs, then `httpx.get` re-resolves independently at connect time. A low-TTL attacker domain can return a public IP during validation and `169.254.169.254` during connect. The docstring already flags this; the fix is to connect to the validated IP.

**Files:**
- Modify: `app/services/net.py`
- Test: `tests/unit/test_net.py`

**Interfaces:**
- Produces: `safe_get` connects to one of the IPs returned by `resolver(host)` (pinned), sending the original `Host` header and SNI, so the connection cannot be re-pointed after validation.

- [ ] **Step 1: Write the failing test** (httpx 0.28.1 — uses `MockTransport`)

```python
import httpx
from app.services import net


def test_safe_get_connects_to_the_validated_ip_not_a_reresolved_one(monkeypatch):
    # resolver returns a public IP; if the code re-resolves via the hostname at
    # connect time it would hit a DIFFERENT (attacker) IP. Pinning proves it doesn't.
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url_host"] = request.url.host
        seen["host_header"] = request.headers.get("host")
        seen["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, text="ok")

    real_client = httpx.Client

    def fake_client(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(net.httpx, "Client", fake_client)
    resp = net.safe_get("https://example.com/x", resolver=lambda h: ["93.184.216.34"])
    assert resp.status_code == 200
    assert seen["url_host"] == "93.184.216.34"   # connected to the pinned IP
    assert seen["host_header"] == "example.com"  # original Host preserved
    assert seen["sni"] == "example.com"          # TLS SNI = real hostname
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/unit/test_net.py -k connects_to_the_validated_ip -v`
Expected: FAIL — current code connects to `example.com` (re-resolved), not the pinned IP.

- [ ] **Step 3: Pin the validated IP in `safe_get`** (`app/services/net.py`)

First make `validate_public_url` return the chosen safe IP:

```python
def validate_public_url(
    url: str, *, resolver: Callable[[str], list[str]] = _default_resolver
) -> tuple[str, str]:
    """Validate and return (original_url, first_safe_ip)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"scheme not allowed: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("missing host")
    try:
        addresses = resolver(host)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"cannot resolve host: {host}") from exc
    if not addresses:
        raise UnsafeURLError(f"no addresses resolved for host: {host}")
    for addr in addresses:
        ip = ipaddress.ip_address(addr)
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise UnsafeURLError(f"{host} resolves to non-public address {ip}")
    return url, addresses[0]
```

Then connect to the pinned IP. **httpx 0.28.1 has no `extensions=` kwarg on `httpx.get` — use a `Client` + `build_request`/`send`:**

```python
    for _ in range(max_redirects + 1):
        _, safe_ip = validate_public_url(current_url, resolver=resolver)
        parsed = httpx.URL(current_url)
        pinned = parsed.copy_with(host=safe_ip)
        # Preserve the original Host (with non-default port) for vhost routing;
        # SNI uses the bare hostname so the TLS cert is validated against the name.
        host_header = parsed.host if parsed.port is None else f"{parsed.host}:{parsed.port}"
        req_headers = {**merged_headers, "Host": host_header}
        extensions = {"sni_hostname": parsed.host} if parsed.scheme == "https" else {}
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            request = client.build_request(
                "GET", str(pinned), headers=req_headers,
                params=next_params, extensions=extensions,
            )
            resp = client.send(request)
        if resp.is_redirect and resp.headers.get("location"):
            location = resp.headers["location"]
            current_url = str(httpx.URL(current_url).join(location))
            next_params = None
            continue
        return resp
```

> **Important:** `validate_public_url` now returns a 2-tuple. Run `grep -rn "validate_public_url" app/ tests/` and update every caller (notably `tests/unit/test_net.py`, which asserts the old `str` return) to unpack `url, _ip`.

- [ ] **Step 4: Run net + collector tests**

Run: `uv run pytest tests/unit/test_net.py tests/unit/test_scrape.py tests/unit/test_rss.py tests/unit/test_feed_discovery.py tests/unit/test_youtube_resolve.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/net.py tests/unit/test_net.py
git commit -m "fix(security): pin validated IP in safe_get to close DNS-rebinding SSRF window"
```

---

## Phase 5 — Collectors (YouTube)

### Task 11: Remove the Whisper transcription feature (user decision)

**Decision:** The optional Whisper fallback (yt-dlp + faster-whisper) is being removed entirely. After this task, `get_transcript` relies solely on `youtube-transcript-api`; videos with no caption transcript simply return `None` (the collector already handles a `None` transcript gracefully).

**Files:**
- Modify: `app/services/youtube.py` (`get_transcript` — delete the whole "Attempt 2: Whisper fallback" branch, lines ~173-209, and the Whisper line in the docstring)
- Modify: `app/core/config.py` (remove `youtube_whisper_enabled` and `whisper_model`)
- Modify: `pyproject.toml` (remove the `[whisper]` optional-dependency group, lines ~44-46)
- Modify: `README.md` (drop the "optional Whisper fallback behind the `whisper` extra" clause, ~line 47)
- Test: `tests/unit/test_youtube.py` (remove any Whisper-specific test; keep transcript-api tests)

- [ ] **Step 1: Find every Whisper reference**

Run: `grep -rni "whisper\|yt_dlp\|yt-dlp\|faster_whisper\|faster-whisper" app pyproject.toml README.md tests config`
Expected: the references listed in this task. Use the result as the deletion checklist.

- [ ] **Step 2: Delete the Whisper fallback in `get_transcript`** (`app/services/youtube.py`)

Replace the docstring's tries-list with just the transcript-api line, and DELETE the entire block from `# --- Attempt 2: Whisper fallback ---` (line ~173) through its `return None` (line ~209), leaving the function ending with the existing final `return None` after Attempt 1. The result:

```python
def get_transcript(video_id: str, settings: Settings, *, lang_pref: str | None = None) -> str | None:
    """Fetch transcript for a YouTube video via youtube-transcript-api (free, no download).

    Returns plain text, or None if no transcript is available.
    """
    # --- youtube-transcript-api ---
    try:
        ...  # (unchanged Attempt-1 body)
    except ImportError:
        log.debug("youtube-transcript-api not installed")

    return None
```

- [ ] **Step 3: Remove the settings** (`app/core/config.py`, delete lines 70-71)

Delete:
```python
    youtube_whisper_enabled: bool = False
    whisper_model: str = "base"
```

- [ ] **Step 4: Remove the optional dependency group** (`pyproject.toml`, delete the `whisper = [...]` group)

- [ ] **Step 5: Update README** (`README.md` ~line 47)

Change "summarize each video's transcript (`youtube-transcript-api`, with an optional Whisper fallback behind the `whisper` extra; the transcript summary needs `GOOGLE_API_KEY`)" to "summarize each video's transcript (`youtube-transcript-api`; the transcript summary needs `GOOGLE_API_KEY`)".

- [ ] **Step 6: Remove/adjust Whisper tests, then run the suite**

Run: `grep -rni "whisper" tests` — delete any test that exercises the removed branch. Then:
Run: `uv run pytest tests/unit/test_youtube.py -v`
Expected: PASS (no Whisper tests remain; transcript-api tests still green).

- [ ] **Step 7: Verify no dangling references**

Run: `grep -rni "whisper\|yt_dlp\|faster_whisper" app pyproject.toml README.md tests`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add app/services/youtube.py app/core/config.py pyproject.toml README.md tests/unit/test_youtube.py
git commit -m "feat(youtube)!: remove optional Whisper transcription fallback"
```

---

### Task 12: Don't silently summarize a wrong-language transcript

**Problem:** When no preferred-language transcript matches, the code grabs `list(transcript_list)[0]` (arbitrary language) and summarizes it with no signal — a French/German transcript gets summarized as if it were the target language.

**Files:**
- Modify: `app/services/youtube.py` (`get_transcript`, fallback ~lines 157-164)
- Test: `tests/unit/test_youtube.py`

- [ ] **Step 1: Write the failing test**

```python
def test_transcript_fallback_logs_when_using_unpreferred_language(monkeypatch, caplog):
    import logging
    from app.core.config import Settings
    from app.services import youtube
    # Build a fake transcript_list whose only transcript is language "fr".
    # find_transcript([...]) raises for ar/en/en-US/en-GB; list() yields the fr one.
    ...
    with caplog.at_level(logging.WARNING):
        text = youtube.get_transcript("vidFR", Settings())
    assert text  # still returns something
    assert any("language" in r.message.lower() for r in caplog.records)
```

> Mirror the existing transcript-api mocking style in `test_youtube.py`; assert a WARNING naming the language is emitted when falling back to a non-preferred transcript.

- [ ] **Step 2: Run it to confirm it fails**

Run: `uv run pytest tests/unit/test_youtube.py -k unpreferred_language -v`
Expected: FAIL — no warning emitted on arbitrary-language fallback.

- [ ] **Step 3: Log the language when falling back** (`get_transcript`, lines 157-161)

```python
            if transcript is None:
                # No preferred-language transcript; fall back to whatever exists
                # but record which language we settled on so a wrong-language
                # summary is auditable rather than silent.
                transcripts = list(transcript_list)
                if transcripts:
                    transcript = transcripts[0]
                    lang = getattr(transcript, "language_code", None) or getattr(transcript, "language", "?")
                    if lang not in langs:
                        log.warning(
                            "youtube %s: no preferred-language transcript; "
                            "summarizing %r transcript instead", video_id, lang,
                        )
```

- [ ] **Step 4: Run youtube tests**

Run: `uv run pytest tests/unit/test_youtube.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/youtube.py tests/unit/test_youtube.py
git commit -m "fix(youtube): warn when summarizing a non-preferred-language transcript"
```

---

## Phase 6 — Frontend "Run now" correctness

### Task 13: "Run now" tracks the real run instead of a premature success toast

**Problem:** `POST /api/runs` is fire-and-forget (202 before the run exists); the button shows a success toast and `mutate()`s immediately, so the UI reports success and revalidates before any data exists. Now that Task 4 returns a `run_id`, the button can reflect "started" honestly and poll.

**Files:**
- Modify: `frontend/lib/api.ts` (`triggerRun` return type)
- Modify: `frontend/components/layout/run-now-button.tsx`
- Test: `frontend/components/layout/run-now-button.test.tsx` (new) or extend existing

- [ ] **Step 1: Update `triggerRun` typing + write the failing test**

`triggerRun` now returns `{ status: string; run_id: string }`:

```ts
  triggerRun(): Promise<{ status: string; run_id: string }> {
    return request<{ status: string; run_id: string }>("/api/runs", { method: "POST" });
  },
```

Test (assert the toast says "started", not "complete", and that a 409 surfaces an "already running" message):

```tsx
it("shows a started (not completed) message and handles 409", async () => {
  // mock api.triggerRun -> resolves {status:"started", run_id:"abc123def456"}
  // render <RunNowButton/>, click, assert toast text contains "started"
  // then mock a 409 ApiError and assert it shows "already in progress"
});
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd frontend && npx vitest run components/layout/run-now-button.test.tsx`
Expected: FAIL — current copy claims completion.

- [ ] **Step 3: Fix the button copy + error handling** (`run-now-button.tsx`)

Change the success toast to communicate that a run *started* (e.g. `Digest run started (<run_id短>)…`), keep the `mutate()` to refresh the runs list, and catch `ApiError` with `status === 409` to show "A digest run is already in progress." Do not claim the digest is ready.

> Read `node_modules/next/dist/docs/` / the existing component before editing (per `frontend/AGENTS.md`). Keep within the existing toast/`sonner` and SWR `mutate` patterns already used in the file.

- [ ] **Step 4: Run frontend tests**

Run: `cd frontend && npm test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/components/layout/run-now-button.tsx frontend/components/layout/run-now-button.test.tsx
git commit -m "fix(fe): Run now reports started + handles 409, no premature success"
```

---

## Final verification

- [ ] **Run the whole backend suite:** `uv run pytest tests/unit tests/integration -q` — Expected: all pass.
- [ ] **Lint:** `uv run --extra lint ruff check app tests` — Expected: clean.
- [ ] **Frontend:** `cd frontend && npm test && npm run build` — Expected: tests pass, build succeeds.
- [ ] **Smoke the deploy surface:** `uv run uvicorn app.fast_api_app:app --port 8081 &` then `curl localhost:8081/api/health` — Expected: `{"status":"ok"}` (proves Task 1).

---

## Out of scope — separate milestone (NOT in this plan)

These review items are **net-new features / large refactors**, not defect fixes, and each warrants its own plan with brainstorming + UI spec. Lumping half-built versions into this remediation plan would lower quality:

1. **Four missing console screens** (Categories, Pipeline config+traces, Runs & Schedule, Settings) + their `/api/categories`, `/api/pipeline/config`, `/api/settings` endpoints. *Runs & Schedule depends on (2).*
2. **Scheduling subsystem** (APScheduler → Cloud Scheduler, `core/ports/scheduler.py`, local/cloud adapters) — the README advertises it; it does not exist. The product is on-demand only until this lands.
3. **Durable/distributed ADK session state** — migrate all seven stages from direct `ctx.session.state` mutation to `EventActions.state_delta`, add a persistent `SessionService`, and un-skip the portability test (needs `greenlet`/`aiosqlite`).
4. **Firestore storage adapter** behind `StorageBackend` + the Vertex (`GOOGLE_GENAI_USE_VERTEXAI`) production path.

## Appendix — bundled low-severity quick-wins (optional, ~10 min each)

If touching the relevant file anyway, fold these in (each: failing test → fix → commit):
- **Excel formula injection** (`render/excel.py`): prefix a leading `=,+,-,@` in `title`/`summary`/`source_name` cells with `'` before writing.
- **`importance_threshold` inert** (`pipeline/processing.py:score_to_importance`): either read the band boundaries from `Settings` or rename the setting to reflect that the bands are fixed (0.66/0.33), so config doesn't mislead.
- **`build_storage` runs DDL on every request** (`runner.py:34` / `api/app.py:89`): build storage once per `create_app`/`register_product_api` and reuse, instead of re-running `init_schema()` on every read.
