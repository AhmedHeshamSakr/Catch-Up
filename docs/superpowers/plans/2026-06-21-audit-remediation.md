# Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the confirmed findings from `docs/AUDIT-2026-06-21.md` (verified by Codex) — make the API safe, add CI, make the three deployment paths *honest* (Local desktop / Cloud Run product / ADK Agent Engine), make the Firestore swap real, delete dead code, and reconcile the docs to the actual flat `app/` architecture.

**Architecture:** Backend = flat `app/` package on Google ADK (`SequentialAgent`/`ParallelAgent` pipeline, `Runner`, `DatabaseSessionService`); product REST API in `app/api/app.py:create_app`; ADK deploy surface in `app/fast_api_app.py`. Frontend = Next.js static export consumed single-port by `create_app`. Storage = `StorageBackend` port with SQLite (default) + Firestore (prod) adapters. We are **not** restructuring into a hexagonal tree — we keep the flat layout and fix the docs that over-promise one.

**Tech Stack:** Python 3.11+ (uv), FastAPI, google-adk, pydantic v2, pytest/pytest-asyncio, ruff; Next.js 16 / React 19 / TS / Vitest; Firestore emulator for the storage contract; GitHub Actions for CI.

## Global Constraints

- **Git identity:** commit as `AhmedHeshamSakr` / `a.hesham1221@gmail.com`. **NO AI/Claude trailers, ever.**
- **Run Python via uv:** `uv run pytest tests/unit tests/integration`; lint `uv run --extra lint ruff check app tests scripts`.
- **Frontend:** `cd frontend && npm run test` and `npm run build`.
- **NEVER change the `model`/`llm_model`** or other config values not targeted by a task.
- **ruff:** line-length 88; `E501`/`C901`/`B006` ignored. Keep imports sorted (isort, first-party `app`,`frontend`).
- **cost-guard hook:** Bash commands that name a `.py` containing `google.cloud`/`vertexai`, or contain those strings inline, are BLOCKED. For Firestore tests run **by directory with a `-k` filter** that avoids those words (e.g. `uv run pytest tests/integration -k firestore`), or use the dedicated Read/Edit tools (not Bash grep) for those files.
- **TDD:** write the failing test first where a behavior changes; deletes/doc-trims are verified by the existing suite staying green.
- **Per-phase gate:** after each phase, a deep Codex review of that phase's diff runs before starting the next phase (read-only `codex exec`). The plan itself is Codex-reviewed before Phase 0.
- **Keep all 497 existing tests green** (415 backend + 82 frontend) unless a task explicitly changes a contract, in which case update the test in the same task.

---

## Phase 0 — Safety net & CI (P0)

**Phase goal:** Stop regressions and close the open-by-default attack surface before changing anything else.

### Task 0.1: Add CI pipeline

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: a CI workflow that runs backend tests, frontend tests + build, and lint on every push/PR to `main` and on PRs.

- [ ] **Step 1: Write the workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v5
      - name: Sync deps
        run: uv sync --frozen
      - name: Lint
        run: uv run --extra lint ruff check app tests scripts
      - name: Tests
        run: uv run pytest tests/unit tests/integration

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run test
      - run: npm run build

  secrets-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: gitleaks
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 2: Verify the commands match local reality** — confirm `uv sync --frozen`, the ruff path, and `npm run test`/`npm run build` exist (`frontend/package.json` scripts) before committing.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions pipeline (backend tests+lint, frontend test+build, gitleaks)"
```

**Acceptance:** workflow file present; the three jobs reference commands that pass locally.

---

### Task 0.2: Manual key-rotation note + .env hygiene

**Files:**
- Modify: `README.md` (security/setup section — add a "Rotate keys" note)
- Verify: `.gitignore` already ignores `.env`/`.env.*` (lines 2-4) — no change expected.

- [ ] **Step 1:** Add a short README note under setup: "If you ever committed or shared a key, rotate it in Google AI Studio + GNews; CI runs gitleaks to catch new leaks." (No secrets are in git history per the prior hygiene audit; this is operational guidance.)
- [ ] **Step 2: Commit** `docs: note key rotation + gitleaks in security setup`.

**Acceptance:** README documents rotation; CI gitleaks job (Task 0.1) is the enforcement. *(Actual key rotation is a manual action for the owner — flagged, not automatable here.)*

---

### Task 0.3: Fail the API closed on non-loopback / deployed entrypoints

**Files:**
- Modify: `app/api/app.py` (add a guard helper; call it in `create_app`)
- Modify: `app/fast_api_app.py` (require `API_KEY` at import — this surface is always network-exposed)
- Test: `tests/integration/test_settings_api.py` or `tests/integration/test_api.py` (new cases)

**Interfaces:**
- Produces: `require_api_key_for_nonlocal(settings, bind_host: str) -> None` in `app/api/app.py` — raises `RuntimeError` when `bind_host` is non-loopback and `settings.api_key` is falsy.

- [ ] **Step 1: Write failing tests**

```python
# tests/integration/test_api.py
import pytest
from app.api.app import require_api_key_for_nonlocal
from app.core.config import Settings

def test_nonlocal_bind_without_api_key_raises():
    s = Settings(api_key=None, app_host="0.0.0.0")
    with pytest.raises(RuntimeError, match="API_KEY"):
        require_api_key_for_nonlocal(s, s.app_host)

def test_loopback_bind_without_api_key_ok():
    s = Settings(api_key=None, app_host="127.0.0.1")
    require_api_key_for_nonlocal(s, s.app_host)  # no raise

def test_nonlocal_bind_with_api_key_ok():
    s = Settings(api_key="secret", app_host="0.0.0.0")
    require_api_key_for_nonlocal(s, s.app_host)  # no raise
```

- [ ] **Step 2: Implement the guard in `app/api/app.py`** (near `_LOOPBACK_HOSTS`, ~line 54):

```python
def require_api_key_for_nonlocal(settings: Settings, bind_host: str) -> None:
    """Refuse to serve a network-exposed API without an API key.

    Loopback binds (127.0.0.1/::1/localhost) stay open for local/dev use; any
    other bind (0.0.0.0, a LAN/public IP) MUST set api_key or we fail closed.
    """
    if _hostname(bind_host) in _LOOPBACK_HOSTS or bind_host in _LOOPBACK_IPS:
        return
    if not settings.api_key:
        raise RuntimeError(
            "Refusing to start: API is bound to a non-loopback address "
            f"({bind_host!r}) without API_KEY set. Set API_KEY for any "
            "network-exposed deployment."
        )
```

- [ ] **Step 3: Call it in `create_app`** (after `settings = settings or Settings()`, ~line 324):

```python
    require_api_key_for_nonlocal(settings, settings.app_host)
```

- [ ] **Step 4: Require the key in `app/fast_api_app.py`** (after `_settings = Settings()`, ~line 50):

```python
# This module is the network-exposed deploy surface (Cloud Run / Agent Engine).
# Fail closed: a deployed /api/* MUST be authenticated.
if not _settings.api_key:
    raise RuntimeError(
        "app.fast_api_app is the deployed surface and requires API_KEY. "
        "Set the API_KEY env var (Secret Manager in prod)."
    )
```

- [ ] **Step 5: Run tests** `uv run pytest tests/integration/test_api.py -k api_key -v` → PASS. Run the full integration suite to ensure existing tests (which use loopback defaults) still pass.
- [ ] **Step 6: Commit** `feat(security): fail API closed on non-loopback bind / deployed entrypoint without API_KEY`.

**Acceptance:** non-loopback bind without a key raises; loopback unaffected; `fast_api_app` import raises without `API_KEY`. Update any test that imports `fast_api_app` to set `API_KEY` (or monkeypatch env) — note this for Phase 3 Docker too.

> **Note for Task 0.1/CI & existing tests:** `tests/integration/test_deploy_surface.py` imports `fast_api_app`; set `API_KEY` in that test's env (monkeypatch) so the new guard passes. Update in this task.

---

### Task 0.4: SSRF response-size cap in `safe_get`

**Files:**
- Modify: `app/services/net.py:74-132` (`safe_get`)
- Test: `tests/unit/test_net.py`

**Interfaces:**
- Produces: `safe_get(..., max_bytes: int = 5_000_000)` — raises `UnsafeURLError` when the declared or streamed body exceeds `max_bytes`.

- [ ] **Step 1: Write failing tests** (use a fake transport/resolver pattern already present in `test_net.py`):

```python
def test_safe_get_rejects_oversized_content_length(monkeypatch):
    # a response advertising a huge Content-Length is rejected before download
    ...
    with pytest.raises(UnsafeURLError, match="too large"):
        safe_get("https://host/big", resolver=lambda h: ["93.184.216.34"], max_bytes=1000)

def test_safe_get_rejects_oversized_stream(monkeypatch):
    # a response with no/again wrong Content-Length but a body over the cap
    with pytest.raises(UnsafeURLError, match="exceeds"):
        safe_get("https://host/big", resolver=lambda h: ["93.184.216.34"], max_bytes=10)
```

- [ ] **Step 2: Re-implement the request/response part of `safe_get`** to stream with a cap. Replace the `with httpx.Client(...)` block + redirect handling (lines 120-131) with:

```python
        with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            request = client.build_request(
                "GET", str(pinned), headers=req_headers,
                params=next_params, extensions=extensions,
            )
            resp = client.send(request, stream=True)
            try:
                if resp.is_redirect and resp.headers.get("location"):
                    location = resp.headers["location"]
                    current_url = str(httpx.URL(current_url).join(location))
                    next_params = None
                    continue
                declared = resp.headers.get("content-length")
                if declared is not None and declared.isdigit() and int(declared) > max_bytes:
                    raise UnsafeURLError(
                        f"response too large: {declared} bytes (> {max_bytes})"
                    )
                body = bytearray()
                for chunk in resp.iter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise UnsafeURLError(
                            f"response exceeds {max_bytes} bytes"
                        )
                # Return a fully-read Response so callers can use .text/.json/.content.
                return httpx.Response(
                    status_code=resp.status_code,
                    headers=resp.headers,
                    content=bytes(body),
                    request=resp.request,
                )
            finally:
                resp.close()
```

Add `max_bytes: int = 5_000_000,` to the signature (after `max_redirects`).

- [ ] **Step 3: Run** `uv run pytest tests/unit/test_net.py -v` → PASS (new + existing).
- [ ] **Step 4: Commit** `fix(security): cap safe_get response size to prevent SSRF/OOM via large bodies`.

**Acceptance:** oversized declared length and oversized streamed body both raise; normal fetches unchanged; all collector tests still pass (they call `safe_get`).

---

### Task 0.5: CSRF guard on mutating product routes when the API is open

**Files:**
- Modify: `app/api/app.py` (`register_product_routes` — add an origin guard dependency on mutating routes)
- Test: `tests/integration/test_api.py`

**Interfaces:**
- Produces: a dependency that, **only when `settings.api_key` is unset** (open/local mode), requires `Origin`/`Referer` (when present) to be loopback — so a malicious web page can't `POST /api/runs` against a local instance. When `api_key` IS set, auth is the control and CORS governs browsers, so the guard is a no-op.

- [ ] **Step 1: Write failing test**

```python
def test_post_runs_rejects_cross_origin_when_open():
    # api_key unset; a cross-site Origin on POST /api/runs -> 403
    ...
    resp = client.post("/api/runs", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403

def test_post_runs_allows_same_origin_when_open():
    resp = client.post("/api/runs", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code in (202, 409)
```

- [ ] **Step 2: Implement** an `_require_same_origin_when_open(settings)` dependency factory (reuse `_hostname` + `_LOOPBACK_HOSTS`, and allow configured `settings.allow_origins`). Apply it to `POST /runs`, `PUT /sources`, `PUT /watchlist`, `POST /sources/resolve` via their `dependencies=[...]` lists.
- [ ] **Step 3: Run** the API integration tests → PASS.
- [ ] **Step 4: Commit** `fix(security): block cross-origin mutations on the open (no-API-key) local API`.

**Acceptance:** cross-origin POST blocked in open mode; same-origin and keyed mode unaffected.

---

### Task 0.6: Authenticate & rate-limit `/feedback` on the deploy surface

**Files:**
- Modify: `app/fast_api_app.py:80-91` (`/feedback`)
- Test: `tests/integration/test_deploy_surface.py`

- [ ] **Step 1: Write failing test:** `/feedback` without the API key → 401 (after Task 0.3 sets `API_KEY` in that test env).
- [ ] **Step 2: Implement:** add `dependencies=[Depends(_require_api_key(_settings))]` to the `/feedback` route (import `_require_api_key` from `app.api.app`), and reuse a token bucket (or the product limiter) so it can't be used as an unbounded Cloud Logging write/cost vector.
- [ ] **Step 3: Run** `uv run pytest tests/integration/test_deploy_surface.py -v` → PASS.
- [ ] **Step 4: Commit** `fix(security): require API key + rate-limit on /feedback (deploy surface)`.

**Acceptance:** unauthenticated `/feedback` rejected; authenticated still logs.

**PHASE 0 GATE:** run full suite (`uv run pytest tests/unit tests/integration`) + frontend tests green, then **deep Codex review of the Phase 0 diff** before Phase 1.

---

## Phase 1 — Architecture hygiene

**Phase goal:** Remove import-time side effects and the layering cycle so importing `app.*` is free of I/O and the dependency graph points one way.

### Task 1.1: Make `root_agent` lazy (no DB creation at import)

**Files:**
- Modify: `app/agent.py` (lazy factory; drop import-time `uuid`/`build_storage`)
- Modify: `app/__init__.py` (don't import `.agent` at package import)
- Test: `tests/unit/test_adk_runtime.py` or a new `tests/unit/test_import_side_effects.py`

**Interfaces:**
- Produces: `app/agent.py` exposes `root_agent` and `app` **lazily** (built on first access, not at import). After this, `import app.core.domain` must NOT create `data/catchup.db`.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_import_side_effects.py
import importlib, sys
from pathlib import Path

def test_importing_app_does_not_create_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "x.db"))
    for m in list(sys.modules):
        if m.startswith("app"):
            del sys.modules[m]
    importlib.import_module("app.core.domain")
    assert not (tmp_path / "x.db").exists()
```

- [ ] **Step 2: Rewrite `app/agent.py`** to build lazily. ADK's `agents_dir` loader expects a module-level `root_agent`/`app`; use a module `__getattr__` so the value is constructed only when ADK (or a caller) actually accesses it:

```python
# ruff: noqa
# <keep the existing Apache license header>
from __future__ import annotations

from app.core.config import Settings


def build_app():
    """Construct the ADK App lazily (no I/O at import time)."""
    from google.adk.apps import App
    from app.pipeline.agents import build_pipeline
    from app.runner import build_storage
    settings = Settings()
    return App(root_agent=build_pipeline(settings, build_storage(settings)), name="app")


def __getattr__(name: str):
    if name in ("app", "root_agent"):
        built = build_app()
        value = built if name == "app" else built.root_agent
        globals()[name] = value
        return value
    raise AttributeError(name)
```

- [ ] **Step 3: Update `app/__init__.py`** — remove `from .agent import app`. Keep `__all__` empty or drop it. (ADK discovers `app` via `agents_dir` import of `app.agent`, not via `app.__init__`.)

```python
# <keep the Apache header>
# No import-time side effects: the ADK App is built lazily in app.agent.
```

- [ ] **Step 4: Verify ADK discovery still works** — `app/fast_api_app.py` uses `get_fast_api_app(agents_dir=AGENT_DIR, ...)` which imports `app.agent` and reads `app`/`root_agent`; the `__getattr__` covers that. Add an assertion test that `app.agent.root_agent` is buildable.
- [ ] **Step 5: Run** `uv run pytest tests/unit -k "import_side_effects or adk_runtime" -v` → PASS; then full unit suite.
- [ ] **Step 6: Commit** `refactor: build ADK root_agent lazily; remove import-time DB creation`.

**Acceptance:** importing any `app.*` module performs no disk I/O; ADK still resolves `root_agent`. This also removes the ignored `build_pipeline(run_id=...)` call site.

---

### Task 1.2: Break the `runner` ↔ `pipeline` import cycle + drop the unused `run_id` param

**Files:**
- Modify: `app/pipeline/agents.py:47-54` (stop importing from `app.runner`)
- Modify: `app/runner.py` (move `_collect` + `_default_*` + `select_rendered` OUT to the pipeline package, or to a new `app/pipeline/wiring.py`)
- Modify: `app/pipeline/agents.py:453-473` (`build_pipeline` — remove the unused `run_id` param)
- Modify callers: `app/runner.py:165` `build_pipeline(... run_id=run_id ...)` → drop `run_id=`
- Test: existing `tests/unit/test_pipeline_agents.py`, `tests/unit/test_build_storage.py`, `tests/integration/test_pipeline_tree.py`

**Interfaces:**
- Produces: `app/pipeline/wiring.py` exporting `collect` (was `_collect`), `default_processor`, `default_narrator`, `default_critic`, `default_reprocessor`, `select_rendered`. `app/runner.py` imports these from the pipeline; `app/pipeline/agents.py` imports them from `wiring` (no `app.runner` import). `build_storage` stays in `runner.py` (it's a runtime concern) and `wiring` may import it lazily if needed.

- [ ] **Step 1:** Create `app/pipeline/wiring.py` and move the bodies of `_collect`, `_default_processor`, `_default_narrator`, `_default_critic`, `_default_reprocessor`, `select_rendered` from `runner.py` into it (keep names without leading underscore for the public ones; re-export the underscore aliases from `runner.py` for backward-compat if any test imports them).
- [ ] **Step 2:** In `app/pipeline/agents.py`, change the `from app.runner import (...)` block (lines 47-54) to `from app.pipeline.wiring import (...)`.
- [ ] **Step 3:** In `runner.py`, replace the deferred `from app.pipeline.agents import build_pipeline` (line 158) — it can now be a top-level import since the cycle is gone. Import the moved helpers from `wiring`.
- [ ] **Step 4:** Remove the `run_id: str | None = None` param from `build_pipeline` (the docstring at 466-472 says it's accepted-but-unused) and drop `run_id=run_id` at the call site in `runner.py`.
- [ ] **Step 5: Run** `uv run pytest tests/unit/test_pipeline_agents.py tests/integration/test_pipeline_tree.py -v` and the full suite → PASS. Grep for `_collect`/`_default_` references in tests and update imports.
- [ ] **Step 6: Commit** `refactor: move pipeline wiring out of runner to break the import cycle; drop unused build_pipeline(run_id=)`.

**Acceptance:** `app/pipeline/agents.py` no longer imports `app.runner`; `runner.py` imports `build_pipeline` at top level; `build_pipeline` has no `run_id` param; suite green.

---

### Task 1.3: Fix the render output-key mismatch

**Files:**
- Decide canonical key set and align both sides. Backend writes `run.outputs["md"|"xlsx"|"html"]` (`app/pipeline/agents.py:438-440`). Frontend expects `html|excel|markdown` (`frontend/components/digests/output-links.tsx:8-19`).
- Modify: `frontend/components/digests/output-links.tsx` (map to `md`/`xlsx`/`html`) **OR** `app/pipeline/agents.py` (emit `markdown`/`excel`). **Chosen: change the frontend to the backend keys** (`md`,`xlsx`,`html`) — fewer moving parts, and `run.outputs` is already persisted with those keys in existing DBs.
- Test: backend `tests/unit/test_run_trigger.py` or a render test asserting the `run.outputs` key set; frontend `frontend/components/digests/*.test.tsx`.

- [ ] **Step 1: Write/extend a backend test** asserting `set(run.outputs) == {"md", "xlsx", "html"}` after a render (lock the contract).
- [ ] **Step 2: Update the frontend** `output-links.tsx` to read `outputs.md`, `outputs.xlsx`, `outputs.html` (keep the human labels Markdown/Excel/HTML). Update `frontend/lib/schemas.ts`/`types.ts` if the outputs shape is typed.
- [ ] **Step 3:** Add/adjust a frontend test asserting the three badges render from `{md,xlsx,html}`.
- [ ] **Step 4: Run** backend + `cd frontend && npm run test` → PASS.
- [ ] **Step 5: Commit** `fix(ui): align digest output keys (md/xlsx/html) so all three formats show`.

**Acceptance:** the three output formats display in the UI; a test pins the `run.outputs` key set so it can't drift again. *(Note: files are still not downloadable — that's a separate FR6 item, out of scope here; do not claim downloads work.)*

**PHASE 1 GATE:** full suite + frontend green, then **deep Codex review of the Phase 1 diff**.

---

## Phase 2 — Firestore: make the swap real

**Phase goal:** `STORAGE_BACKEND=firestore` works against a real emulator and is exercised by the storage contract. Follow the existing checklist in `tests/integration/test_firestore_emulator.py:6-19`.

> **cost-guard:** run these tests by directory + filter: `uv run pytest tests/integration -k firestore`. Edit the google.cloud-touching files with the Edit tool, not Bash.

### Task 2.1: Use `FieldFilter` instead of positional `where()`

**Files:**
- Modify: `app/adapters/storage/firestore_backend.py:62-96` (`get_items_for_run`, `list_news`)
- Update: `tests/unit/fake_firestore.py` if it must accept `filter=` kwargs (it currently mirrors positional `where`).
- Test: `tests/unit/test_firestore_backend.py`

- [ ] **Step 1:** Import lazily inside methods (keep adapter import free of `google.cloud`): `from google.cloud.firestore_v1.base_query import FieldFilter`. Provide a small helper `_where(q, field, op, value)` that uses `FieldFilter` when available and falls back to positional for the fake. **Cleaner:** make `FakeFirestoreClient` accept `where(filter=FieldFilter(...))` so prod and fake share one path.
- [ ] **Step 2:** Replace `.where("digest_run_id", "==", run_id)` → `.where(filter=FieldFilter("digest_run_id", "==", run_id))` (and the others).
- [ ] **Step 3:** Update `fake_firestore.py` to parse `filter=` (read `.field_path`/`.op_string`/`.value` from the `FieldFilter`).
- [ ] **Step 4: Run** `uv run pytest tests/unit -k firestore -v` → PASS.
- [ ] **Step 5: Commit** `refactor(firestore): use FieldFilter (positional where is deprecated)`.

**Acceptance:** adapter uses `FieldFilter`; fake + unit tests pass; no `google.cloud` import at module scope.

---

### Task 2.2: Composite indexes + `firestore.indexes.json`

**Files:**
- Create: `firestore.indexes.json` (composite indexes for `news_items`: `category`+`collected_at desc`, `importance`+`collected_at desc`, `is_flagged`+`collected_at desc`, and the multi-equality combos used by `list_news`).
- Modify: README/deploy docs to reference `gcloud firestore indexes composite create` / `firebase deploy --only firestore:indexes`.

- [ ] **Step 1:** Enumerate the exact filter+order combinations in `list_news` (category?, importance?, is_flagged) × `order_by collected_at DESC` and `list_runs` (`started_at DESC`). Write the matching composite index definitions.
- [ ] **Step 2:** Document the deploy command in the Phase 3 deploy section.
- [ ] **Step 3: Commit** `feat(firestore): composite index definitions for list_news/list_runs`.

**Acceptance:** `firestore.indexes.json` covers every filtered+ordered query; documented.

---

### Task 2.3: Batch `existing_ids` (avoid O(N) doc gets)

**Files:**
- Modify: `app/adapters/storage/firestore_backend.py:40-44`
- Test: `tests/unit/test_firestore_backend.py`

- [ ] **Step 1: Write a test** asserting `existing_ids` returns the present subset for a 600-id input (crosses the 500 `in`/batch boundary) without per-doc gets.
- [ ] **Step 2: Implement** using `get_all` on document refs (or chunked `FieldFilter("__name__","in",chunk)` ≤ 30/chunk, or `get_all([col.document(i) for i in ids])`). Prefer `self._client.get_all(refs)` and collect `snap.id for snap in ... if snap.exists`.
- [ ] **Step 3: Update** `fake_firestore.py` to support the chosen batch read (`get_all`).
- [ ] **Step 4: Run** `uv run pytest tests/unit -k firestore -v` → PASS.
- [ ] **Step 5: Commit** `perf(firestore): batch existing_ids lookup`.

**Acceptance:** dedup does a bounded number of reads regardless of N; tests pass.

---

### Task 2.4: `is_flagged` parity with SQLite NULL handling

**Files:**
- Modify: `app/adapters/storage/firestore_backend.py` (`_item_doc` already sets `is_flagged`; ensure default queries treat missing field as not-flagged via backfill, since Firestore `==False` does NOT match a missing field — unlike SQLite's `status IS NULL OR != 'flagged'`).
- Add: a tiny migration/backfill note + (optional) a `backfill_is_flagged()` helper.
- Test: storage contract case asserting an item with `status='raw'` (not flagged) is returned by default `list_news`/`get_items_for_run`.

- [ ] **Step 1:** Confirm every write path sets `is_flagged` (it does, in `_item_doc`). Add a contract test (Task 2.5 harness) that a non-flagged item is returned by default queries on **both** backends.
- [ ] **Step 2:** Add `backfill_is_flagged()` (sets `is_flagged=False` where missing) for pre-existing docs; document running it once before relying on filtered queries.
- [ ] **Step 3: Commit** `fix(firestore): ensure is_flagged parity with SQLite NULL-status semantics`.

**Acceptance:** default queries on both backends return non-flagged items identically; backfill documented.

---

### Task 2.5: Un-skip the emulator-backed storage contract

**Files:**
- Modify: `tests/integration/test_firestore_emulator.py` (replace the skip + AssertionError with a real test that runs `StorageContract` against a `firestore.Client` pointed at the emulator)
- Reuse: `tests/unit/storage_contract.py` (the shared contract both backends already subclass)

- [ ] **Step 1:** Implement: gate on `FIRESTORE_EMULATOR_HOST` being set (`pytest.mark.skipif` when unset, so CI without the emulator skips cleanly rather than failing). When set, instantiate `FirestoreBackend(firestore.Client(...))` and run the full `StorageContract` suite against it.
- [ ] **Step 2:** Add a CI job step (optional, can be a separate workflow) that starts the emulator (`gcloud beta emulators firestore start`) and runs `uv run pytest tests/integration -k firestore_emulator`. If emulator setup in CI is too heavy, leave it as a documented local pre-deploy gate and say so in the test docstring.
- [ ] **Step 3: Run locally** with the emulator: `gcloud beta emulators firestore start &`, `export FIRESTORE_EMULATOR_HOST=...`, `uv run pytest tests/integration -k firestore_emulator`. (If the emulator/SDK isn't installed locally, leave skipif in place and record that the gate is ready but unrun.)
- [ ] **Step 4: Commit** `test(firestore): emulator-backed storage contract (skipif no emulator)`.

**Acceptance:** with the emulator running, `FirestoreBackend` passes the same `StorageContract` as SQLite; without it, the test skips (never the old hard `AssertionError`).

---

### Task 2.6: Cache one Firestore client per process

**Files:**
- Modify: `app/runner.py:40-62` (`_firestore_client`/`build_storage`) — memoize the client/ backend so the long-lived API doesn't build a new client per call.

- [ ] **Step 1:** Add a module-level cache keyed by `(backend, project)` so `build_storage` returns a cached `FirestoreBackend` under repeated calls (the API calls `storage()` per request). Keep SQLite per-call (cheap) or cache likewise.
- [ ] **Step 2:** Add a test asserting two `build_storage(settings)` calls with the firestore backend return the same instance (inject a fake client factory).
- [ ] **Step 3: Commit** `perf(firestore): cache the client/backend per process`.

**Acceptance:** repeated `build_storage` reuses one Firestore client.

**PHASE 2 GATE:** `uv run pytest tests/unit tests/integration -k "storage or firestore or sqlite"` + full suite green, then **deep Codex review of the Phase 2 diff**.

---

## Phase 3 — Deploy story: three honest paths

**Phase goal:** Make Local desktop, Cloud Run product, and ADK Agent Engine each *accurate*. No descriptor claims a capability the code doesn't ship.

### Task 3.1: Dockerfile builds the console + serves the product app on `$PORT`

**Files:**
- Modify: `Dockerfile` (add a Node build stage for `frontend/out`; copy it in; run `create_app` on `$PORT`)
- Modify: `app/api/app.py` / a small ASGI entry so the container serves `create_app()` (product console + API) — **this is the Cloud Run "product" path**.

- [ ] **Step 1:** Add a multi-stage build: stage 1 `node:20` runs `npm ci && npm run build` in `frontend/` (with `NEXT_PUBLIC_API_BASE=""` so the static console calls same-origin `/api`); stage 2 (python) copies `frontend/out` to the path `Settings.console_dir` expects (`/code/frontend/out`).
- [ ] **Step 2:** Provide the product ASGI app for Cloud Run. Add `app/web_app.py` exposing `app = create_app()` (honest name), and set the Dockerfile `CMD` to `uv run uvicorn app.web_app:app --host 0.0.0.0 --port ${PORT:-8080}`. `create_app` already mounts the console when `console_dir` exists and now enforces Task 0.3's key guard (so the image MUST run with `API_KEY` set — document it).
- [ ] **Step 3:** Keep `app.fast_api_app:app` available as the **Agent Engine** path (Task 3.5), but the default product image runs `app.web_app`.
- [ ] **Step 4:** Add `--extra firestore` to the image's `uv sync` so `STORAGE_BACKEND=firestore` can import (Codex's catch). Either `uv sync --frozen --extra firestore` or document it as opt-in build-arg.
- [ ] **Step 5: Build locally** `docker build -t catchup .` (if Docker available); else verify the Dockerfile statements. Add a test that `app.web_app` imports and exposes `app` (with `API_KEY` set in env).
- [ ] **Step 6: Commit** `feat(deploy): Dockerfile builds the console and serves the product app (Cloud Run path) on $PORT with firestore extra`.

**Acceptance:** the image bundles the Next.js console and serves console + `/api` single-port; Firestore extra installed; `API_KEY` required.

---

### Task 3.2: Reconcile `agents-cli-manifest.yaml` honestly

**Files:**
- Modify: `agents-cli-manifest.yaml`

- [ ] **Step 1:** Update the fields to reflect reality of the chosen Agent-Engine path (only if you actually use `agents-cli deploy`). If Agent Engine is a real path, set `deployment_target`/`session_type`/`datastore` to honest values; if it's NOT used, add a comment that the manifest is the ADK-scaffold descriptor for the optional Agent-Engine path and the product deploy is the Dockerfile/Cloud Run path. Do not leave `none/none/in_memory` implying nothing deploys when the README claims cloud.
- [ ] **Step 2: Commit** `docs(deploy): make agents-cli-manifest honest about the Agent Engine path`.

**Acceptance:** the manifest no longer contradicts the README/Dockerfile.

---

### Task 3.3: README + ARCHITECTURE — three honest deployment paths

**Files:**
- Modify: `README.md`, `ARCHITECTURE.md`

- [ ] **Step 1:** Add a "Deployment" section describing exactly three paths, each with *what it includes and excludes*:
  1. **Local desktop** — `Catch-Up.app` / `scripts/run.sh` → `create_app` single-port, SQLite, loopback, no API key needed. (Works today.)
  2. **Cloud Run product** — Docker image from Task 3.1: console + `/api`, `$PORT`, `API_KEY` required, optional Firestore (extra installed). Cloud Scheduler → `POST /api/runs` for scheduled runs.
  3. **ADK Agent Engine** — `app/fast_api_app.py` (ADK web UI + `/api`, no product console), for `agents-cli deploy` / Gemini Enterprise.
- [ ] **Step 2:** Remove/repair any prose that implies the old single contradictory story. State Firestore's status honestly (now emulator-tested; needs indexes deployed).
- [ ] **Step 3: Commit** `docs: document the three honest deployment paths (local / cloud run / agent engine)`.

**Acceptance:** a reader can pick a path and the code matches the description.

---

### Task 3.4: Keep `fast_api_app.py` honest (Agent Engine path)

**Files:**
- Modify: `app/fast_api_app.py` (docstring already accurate; add the `/feedback` auth from Task 0.6 and a note that this surface has NO product console)

- [ ] **Step 1:** Confirm the docstring (lines 15-29) still matches after Task 0.3/0.6. Add one line: "This path serves the ADK web UI + `/api/*` but NOT the Next.js product console — use the Cloud Run image (`app.web_app`) for that."
- [ ] **Step 2: Commit** `docs(deploy): clarify fast_api_app is the console-less Agent Engine surface`.

**Acceptance:** the entrypoint's own docs are accurate.

**PHASE 3 GATE:** full suite green + (if Docker available) image builds, then **deep Codex review of the Phase 3 diff**.

---

## Phase 4 — Deletes & drops

**Phase goal:** Remove dead/over-sold code. Each delete keeps the suite green (update tests in the same task).

### Task 4.1: Delete the ADK-native eval scaffold

**Files:**
- Delete: `tests/eval/evalsets/basic.evalset.json`, `tests/eval/eval_config.json`, `tests/eval/evalsets/README.md`
- Modify: `docs/eval/README.md` (one line: the ADK-native `agents-cli eval` path is intentionally unused; the custom enrichment harness in `app/pipeline/eval_score.py` + `scripts/eval_enrichment.py` is the real eval)
- Verify: no code imports them (grep first; the custom harness uses `tests/eval/baseline.json` + `tests/eval/fixtures/enrichment_reference.json`, which STAY).

- [ ] **Step 1:** `grep -rn "basic.evalset\|eval_config\|eval_set_id" app tests scripts docs` (via Bash, avoiding google words) → expect zero references outside the deleted files.
- [ ] **Step 2:** Delete the three files; add the note to `docs/eval/README.md`.
- [ ] **Step 3: Run** `uv run pytest tests/unit tests/integration` → PASS (nothing referenced them).
- [ ] **Step 4: Commit** `chore: delete dead ADK-native eval scaffold (custom harness is the real eval)`.

**Acceptance:** scaffold gone; custom eval intact; suite green. **ADK itself is untouched** (pipeline uses `SequentialAgent`/`ParallelAgent`/`Runner`).

---

### Task 4.2: Remove `NewsItem.language`

**Files:**
- Modify: `app/core/domain.py:152` (remove `language`)
- Modify: `frontend/lib/types.ts` / `frontend/lib/schemas.ts` (remove `language` if present)
- Test: `tests/unit/test_domain.py` (drop any language assertion); any serialization snapshot.

- [ ] **Step 1:** grep for `\.language`/`"language"`/`language=` across `app`, `tests`, `frontend` → confirm it's never produced/consumed.
- [ ] **Step 2:** Remove the field + any frontend type entry. Run backend + frontend tests.
- [ ] **Step 3: Commit** `chore: drop always-None NewsItem.language field`.

**Acceptance:** field removed; suite green; no payload references `language`.

---

### Task 4.3: Remove `output_key` on the LLM agents

**Files:**
- Modify: the 6 LLM agent builders (`app/pipeline/processing.py`, `critic.py`, `judge.py`, `digest_editor.py` — wherever `output_key=` is passed to an `LlmAgent`).
- Test: existing pipeline/agent tests.

- [ ] **Step 1:** grep `output_key` across `app/pipeline` → confirm the value is written to throwaway sessions and never read (the text re-parse path is load-bearing).
- [ ] **Step 2:** Remove the `output_key=` kwargs. Run `uv run pytest tests/unit/test_pipeline_agents.py tests/unit/test_processing.py tests/unit/test_critic.py tests/unit/test_judge.py tests/unit/test_digest_editor.py -v`.
- [ ] **Step 3: Commit** `chore: remove unused output_key from LLM agents`.

**Acceptance:** agents build/run without `output_key`; suite green.

---

### Task 4.4: Replace the `example.com` scrape source

**Files:**
- Modify: `config/sources.yaml` (the `example_scrape` entry)

- [ ] **Step 1:** Replace the non-functional `example.com` scrape source with either a real, reputable disabled-by-default scrape example (with a working CSS selector) or remove it; keep the file's other defaults intact.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_config.py -v` (source loading) → PASS.
- [ ] **Step 3: Commit** `chore(config): replace placeholder example.com scrape source`.

**Acceptance:** no `example.com` placeholder; config still loads.

---

### Task 4.5: Drop multi-tenant `org_id`/`user_id`

**Files:**
- Modify: `app/core/domain.py` (remove `org_id`/`user_id` from `NewsItem`; remove `org_id` from `DigestRun`; remove `DEFAULT_ORG`/`DEFAULT_USER` if now unused)
- Modify: `app/adapters/storage/sqlite_backend.py` (drop the `org_id` column from `news_items`/`digest_runs` DDL + the `org_id` value in `save_items`/`create_run`; **add a migration note** — existing DBs keep the dead column harmlessly; new schema omits it)
- Modify: `app/adapters/storage/firestore_backend.py` (no schema, but `model_dump` no longer emits the fields — fine)
- Modify: `frontend/lib/schemas.ts`/`types.ts` (remove `org_id`/`user_id`)
- Test: `tests/unit/test_domain.py`, `tests/unit/storage_contract.py`, `tests/unit/test_sqlite_backend.py`

**Interfaces:**
- Produces: `NewsItem`/`DigestRun` without tenancy fields. **Decision:** keep the existing SQLite `org_id` columns physically (dropping a column needs a table rebuild) but stop writing/reading them; new DDL for fresh DBs omits them. Document this so it's not mistaken for drift.

- [ ] **Step 1: Write failing test** asserting `NewsItem` and `DigestRun` have no `org_id`/`user_id` fields (`'org_id' not in NewsItem.model_fields`).
- [ ] **Step 2:** Remove the fields from the domain; remove `org_id` usage in `SqliteBackend.save_items`/`create_run` (insert `NULL` or drop the column from the INSERT + fresh DDL). Update the `_RUN_COLUMNS`/DDL accordingly; keep migration tolerant of old DBs that still have the column.
- [ ] **Step 3:** Update the storage contract + sqlite tests; update the frontend schema/types.
- [ ] **Step 4: Run** `uv run pytest tests/unit tests/integration -k "domain or storage or sqlite or firestore"` + frontend tests → PASS.
- [ ] **Step 5: Commit** `chore: drop vestigial multi-tenant org_id/user_id (single-user v1)`.

**Acceptance:** tenancy fields gone from domain, storage writes, and frontend; both backends + contract pass; old DBs still load.

**PHASE 4 GATE:** full suite + frontend green, then **deep Codex review of the Phase 4 diff**.

---

## Phase 5 — Doc trim & reconcile

**Phase goal:** Make the spec + ARCHITECTURE describe the *actual* flat `app/` architecture. Keep the storage hexagon (real); drop the fictional `llm.py` port, scheduler port/adapters, and `usecases/` ring.

### Task 5.1: Trim the design spec §6/§12/§21

**Files:**
- Modify: `docs/superpowers/specs/2026-05-23-adk-catchup-agent-design.md`

- [ ] **Step 1: §12 Swap-Points** — remove `core/ports/scheduler.py` and `core/ports/llm.py` and `adapters/scheduling/*` from the tree. Replace with the truth: storage is the only port/adapter pair; LLM provider swaps via the `GOOGLE_GENAI_USE_VERTEXAI` env toggle (no port); the scheduler swap is "Cloud Scheduler → `POST /api/runs`" (no port/adapter).
- [ ] **Step 2: §21 Project Structure** — replace the `backend/catchup/{... core/{domain/, ports/, usecases/, config.py} ...}` tree with the real flat `app/` layout (no `usecases/`; `domain.py` is a module; `core/ports/storage.py` only).
- [ ] **Step 3: §6 Principles** — soften "domain + use-cases independent of frameworks" to match: ports&adapters applied where it pays (storage); the rest is pragmatic flat modules.
- [ ] **Step 4: Commit** `docs(spec): trim aspirational hexagon to the actual flat app/ layout`.

**Acceptance:** the spec's structure sections match `git ls-files app/`.

---

### Task 5.2: Reconcile ARCHITECTURE.md swap-points

**Files:**
- Modify: `ARCHITECTURE.md` (the "swap SQLite→Firestore, AI Studio→Vertex, APScheduler→Cloud Scheduler by config alone" line + Storage/Orchestration rows)

- [ ] **Step 1:** Keep the storage swap claim (now real). Reword the scheduler swap as "Cloud Scheduler hits `POST /api/runs`" and the LLM swap as "env toggle `GOOGLE_GENAI_USE_VERTEXAI`". Remove any implication of scheduler/llm ports.
- [ ] **Step 2: Commit** `docs(architecture): reconcile swap-points with the real code`.

**Acceptance:** ARCHITECTURE matches code; no fictional ports.

---

### Task 5.3: Update CLAUDE.md eval line + BUILD-LOG entry

**Files:**
- Modify: `CLAUDE.md` (the `agents-cli eval run` mention → point at the custom harness, or note the ADK-native path is unused)
- Modify: `docs/BUILD-LOG.md` (append an audit-remediation entry tracing this milestone)

- [ ] **Step 1:** Fix the eval guidance; add the BUILD-LOG entry.
- [ ] **Step 2: Commit** `docs: update eval guidance + build log for the audit-remediation milestone`.

**Acceptance:** docs internally consistent with the deletes in Phase 4.

**PHASE 5 GATE:** full suite + frontend green; final **deep Codex review of the Phase 5 diff** + a brief end-to-end review that the docs now match the code.

---

## Self-Review (author checklist)

- **Spec coverage vs the audit:** P0 security (Tasks 0.3–0.6, 0.2) · CI (0.1) · import side-effects (1.1) · import cycle (1.2) · output keys (1.3) · Firestore real swap incl. the import-extra Codex miss (2.1–2.6, 3.1) · three honest deploy paths (3.1–3.4) · CSRF + /feedback Codex misses (0.5, 0.6) · deletes/drops (4.1–4.5) · doc trim (5.1–5.3). The browser-visible `NEXT_PUBLIC_API_KEY` note is documented in Task 3.3 (framed as stopgap). **Gap check:** rate-limit-not-on-collectors and tenacity/circuit-breaker resilience are NOT in this plan — they are deliberately deferred (documented as a follow-up in BUILD-LOG, Task 5.3) to keep this milestone focused; ARCHITECTURE's resilience claims will be softened in Task 5.2.
- **Placeholder scan:** code blocks are real; the few "enumerate/grep then implement" steps are mechanical and bounded.
- **Type consistency:** `require_api_key_for_nonlocal(settings, bind_host)`, `safe_get(..., max_bytes=...)`, `app/pipeline/wiring.py` exports, `app/web_app.py:app` are referenced consistently across tasks.

## Codex plan-review — resolved corrections (incorporated)

Codex pre-execution review (`.claude/codex-reviews/20260621T190755Z-remediation-plan-review.md`) read the live code and returned "do not execute as written" until these are addressed. All are now folded in:

**Decisions (all confirmed by Codex):**
1. **Output keys** (Task 1.3): change the frontend to `md/xlsx/html` — backend + existing DB rows already use those keys. ✅ chosen.
2. **SQLite tenancy columns** (Task 4.5): keep the old physical columns, **omit `org_id` from the new DDL AND from the INSERT column lists entirely** — do NOT "write NULL by naming the column". Old + new schemas both work; no table rebuild. ✅
3. **Firestore emulator in CI** (Task 2.5): `skipif` is acceptable ONLY if docs label Firestore as pre-deploy-validated, not continuously enforced; otherwise run the emulator in a CI job. Plan: `skipif` + a separate/optional emulator CI job; README states the status honestly. ✅

**Corrections to apply during execution:**
- **Task 0.3/3.1 (Cloud Run auth hole):** `create_app`'s guard on `settings.app_host` does NOT cover Cloud Run, where uvicorn binds `--host 0.0.0.0` externally while `app_host` stays `127.0.0.1`. → **Phase 3 `app/web_app.py` MUST explicitly require `API_KEY`** (not rely on create_app's app_host guard). *(Already done for `catchup serve` via the CLI `--host` guard and for `fast_api_app` via its import guard.)*
- **Task 1.2 (cycle):** `app/pipeline/wiring.py` must **not** import `runner` or `build_storage` (remove the "may import lazily" note). `build_storage` stays in `runner.py`. **Preserve monkeypatch targets:** tests patch `app.pipeline.agents._collect`, `runner.rss`, `runner.markdown` (see `tests/integration/test_run_digest.py:115`, `tests/integration/test_run_digest_database_session.py:47`) — re-export the underscore aliases so existing patches keep working, or update the patch targets in the same task.
- **Task 2.1 (FieldFilter):** default CI runs WITHOUT the `[firestore]` extra, so production code must not unconditionally construct `FieldFilter` in fake-backed unit tests. Implement `_where()` with a `try: from google.cloud.firestore_v1.base_query import FieldFilter / except ImportError` fallback to positional (for the fake), OR install `--extra firestore` in the backend CI job. Plan: `_where()` fallback + fake supports `where(filter=...)`.
- **Task 2.4 (is_flagged backfill):** make it concrete — scan documents, batch-update those missing `is_flagged`, and emulator-test it (not just a doc note).
- **fast_api_app guard order:** ✅ already fixed (key guard moved above GCP auth/logging).
- **Gap — docs/ADK-GUIDE.md:** add a Phase 5 task to update it (it still documents eager `app = App(...)` and `build_pipeline(..., run_id=...)`, both removed in Phase 1).
