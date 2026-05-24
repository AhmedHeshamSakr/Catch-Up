# Code-Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every Critical/High/Medium/A11y finding from the 2026-05-24 deep code review (backend correctness, security, architecture; frontend engineering + UI/UX accessibility) without regressing the green baseline (195 backend tests, 43 frontend tests, ruff/eslint/tsc clean).

**Architecture:** Surgical fixes that preserve the hexagonal core, the injectable-boundary test strategy, and the ADK agent tree. The two headline changes are (a) a loop-aware sync→async bridge so the live LLM pipeline actually runs inside the ADK tree, and (b) a single `safe_get` SSRF chokepoint that all collectors route through. Commit identity: **AhmedHeshamSakr <a.hesham1221@gmail.com>**, NO AI trailers. Run Python via `uv`; lint `uv run --extra lint ruff check app tests scripts`. Do not change the model (`gemini-flash-latest`).

**Tech Stack:** Python 3.11+, Google ADK 1.34.x, FastAPI, pydantic v2, pydantic-settings, httpx, ruamel.yaml; Next.js 16 / React 19 / TS / Tailwind v4 / @base-ui/react / SWR / Vitest+RTL / zod.

---

## Batch B1 — Critical #1: nested `asyncio.run` (live pipeline silently fails)

**Files:**
- Modify: `app/pipeline/adk_runtime.py`
- Test: `tests/integration/test_pipeline_live_bridge.py` (create)

**Root cause:** `run_agent_text` calls `asyncio.run()` (adk_runtime.py:35) while already inside the event loop started by `run_digest`'s `asyncio.run(_run_tree)` (runner.py:101). Raises `RuntimeError`, swallowed at agents.py:189 → unenriched PARTIAL digests on every live run.

**Approach (loop-aware bridge):** `run_agent_text` must detect whether an event loop is already running in the current thread. If not, `asyncio.run` as today. If yes, run the coroutine in a **separate thread** with its own loop (so we never call `asyncio.run` inside a running loop). Do NOT use `nest-asyncio` (remove it from deps).

- [ ] **Step 1: Write the failing integration test.** Drive the real `run_agent_text` path from inside a running loop using a **stubbed model**, not a stubbed callable. Build a tiny `Agent` whose model is faked (monkeypatch the genai client / use an ADK test double that returns canned JSON) — OR, if stubbing the model is impractical, assert at minimum that calling `run_agent_text` from within an already-running event loop returns the stubbed text instead of raising `RuntimeError`. The test MUST fail on current code with `RuntimeError: asyncio.run() cannot be called from a running event loop`.

```python
# tests/integration/test_pipeline_live_bridge.py
import asyncio
from app.pipeline import adk_runtime

def test_run_agent_text_works_inside_running_loop(monkeypatch):
    async def fake_run_text_async(agent, payload, *, app_name="catchup"):
        return '{"ok": true}'
    monkeypatch.setattr(adk_runtime, "_run_text_async", fake_run_text_async)

    async def driver():
        # Call the SYNC bridge from inside a running loop (mirrors the ADK tree).
        return adk_runtime.run_agent_text(object(), "payload", _settings_stub())
    result = asyncio.run(driver())
    assert result == '{"ok": true}'

def test_run_agent_text_works_without_loop(monkeypatch):
    async def fake_run_text_async(agent, payload, *, app_name="catchup"):
        return "plain"
    monkeypatch.setattr(adk_runtime, "_run_text_async", fake_run_text_async)
    assert adk_runtime.run_agent_text(object(), "p", _settings_stub()) == "plain"
```
Provide a minimal `_settings_stub()` (an object with `google_api_key=None`) so `ensure_api_key` is a no-op.

- [ ] **Step 2: Run it — confirm the in-loop test fails** with RuntimeError. `uv run pytest tests/integration/test_pipeline_live_bridge.py -q`.

- [ ] **Step 3: Implement the loop-aware bridge:**

```python
import asyncio
import concurrent.futures

def _run_coro_blocking(coro):
    """Run a coroutine to completion from sync code, even if a loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)        # no loop in this thread — safe
    # A loop is already running (we're inside the ADK tree). Run in a worker thread.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()

def run_agent_text(agent, payload, settings, *, app_name="catchup"):
    ensure_api_key(settings)
    return _run_coro_blocking(_run_text_async(agent, payload, app_name=app_name))
```
Note: `_run_text_async(...)` is a coroutine object created once and handed to the bridge.

- [ ] **Step 4: Run the new tests — both pass.**
- [ ] **Step 5: Run full suite** `uv run pytest tests -q` → 197+ green; `ruff` clean.
- [ ] **Step 6: Remove `nest-asyncio`** from `pyproject.toml` dev deps (now unused). Re-run `uv sync` and the suite.
- [ ] **Step 7: Commit** `fix(pipeline): loop-aware sync bridge so live LLM agents run inside the ADK tree`.

---

## Batch B2 — High: break `services ↔ pipeline` import cycle + honest parallelism

**Files:**
- Create: `app/llm/__init__.py`, move `app/pipeline/adk_runtime.py` → `app/llm/runtime.py`
- Modify: every importer of `app.pipeline.adk_runtime` (grep: `app/pipeline/processing.py`, `digest_editor.py`, `critic.py`, `judge.py`, `app/services/search.py`, `app/services/youtube.py`)
- Modify: `app/pipeline/agents.py` (remove deferred in-function imports now that cycle is gone), `app/runner.py`
- Modify: `app/pipeline/agents.py` (CollectSources concurrency + per-source error keys)
- Test: existing `tests/integration/test_pipeline_tree.py`, `tests/unit/test_agents*.py`

**Part A — break the cycle:**
- [ ] Grep the exact cycle edges first: `grep -rn "app.pipeline" app/services` and `grep -rn "app.services" app/pipeline`. The services→pipeline edge is `adk_runtime`. Move it to a neutral `app/llm/runtime.py` (it depends only on `google.adk`, `google.genai`, `app.core.config` — all lower layers, so no new cycle).
- [ ] Update ALL imports `from app.pipeline.adk_runtime import ...` → `from app.llm.runtime import ...`.
- [ ] Confirm `app/services/*` no longer imports `app.pipeline.*` (re-grep). If `youtube.py`/`search.py` still import any other `pipeline` module, move that too (likely none beyond runtime).
- [ ] Remove the now-unnecessary deferred in-function imports in `agents.py` (`build_pipeline`) and `runner.py` (`from app.pipeline.agents import build_pipeline` can stay in `run_digest` if it avoids a separate cycle — verify; prefer top-level if clean).
- [ ] Keep B1's bridge intact in the moved file.

**Part B — honest parallelism + safe error accumulation:**
- [ ] In `SourceCollectorAgent._run_async_impl`, wrap the blocking collector in a thread so the `ParallelAgent` is genuinely concurrent and never blocks the loop:
```python
raws = await asyncio.to_thread(self.collect_fn, source, self.settings, self.storage)
```
(Match the actual `collect_fn` signature; thread the storage kwarg as today.)
- [ ] Replace shared-`DigestRun.source_errors` mutation inside the parallel collectors with **per-source state keys** (e.g. `state[f"errors_{self.state_key}"] = [...]`). Each collector writes only its own key.
- [ ] In `NormalizeDedupAgent`, **merge** all `errors_*` keys into `run.source_errors` (single-threaded stage, safe). Preserve the existing error dict shape so API/tests are unaffected.
- [ ] Run `tests/integration/test_pipeline_tree.py` + agent unit tests; fix any wrapper-unit-test assertions that referenced the old error-write location. Keep behavior (final `run.source_errors` content) identical.
- [ ] **Commit** `refactor(arch): extract LLM runtime to break services↔pipeline cycle; make CollectSources truly concurrent with per-source error keys`.

---

## Batch B3 — Critical #2 (SEC): SSRF guard on every outbound fetch

**Files:**
- Modify: `app/services/net.py` (add `safe_get`)
- Modify: `app/services/rss.py`, `app/services/youtube.py` (`_default_fetch` + the resolve lambda at ~:261), `app/services/newsapi.py`, `app/services/scrape.py`, `app/services/feed_discovery.py`, `app/services/youtube_resolve.py` (route through `safe_get`)
- Test: `tests/unit/test_net.py`, `tests/unit/test_rss.py`, `tests/unit/test_youtube.py`, `tests/unit/test_newsapi.py`

**Approach:** One chokepoint `safe_get` that validates-then-fetches and is redirect-safe.

- [ ] **Step 1: Write failing tests** asserting `rss.fetch_feed`, `youtube` channel fetch, and `newsapi.fetch_gnews` all reject a private/loopback/link-local URL (raise `UnsafeURLError`) — using the injectable resolver/fetch seams so it's offline.
- [ ] **Step 2: Implement `safe_get` in `net.py`:**
```python
import httpx
from app.services.net import validate_public_url, UnsafeURLError  # already present

_DEFAULT_HEADERS = {"User-Agent": "CatchUp/1.0 (+https://github.com/AhmedHeshamSakr/Catch-Up)"}

def safe_get(url: str, *, timeout: float = 15.0, resolver=None, headers=None,
             max_redirects: int = 3) -> httpx.Response:
    """SSRF-safe GET: validates the public-ness of every hop, no auto-redirects."""
    current = url
    for _ in range(max_redirects + 1):
        validate_public_url(current, resolver=resolver)   # re-validate each hop (kills rebinding-via-redirect)
        resp = httpx.get(current, timeout=timeout, follow_redirects=False,
                         headers={**_DEFAULT_HEADERS, **(headers or {})})
        if resp.is_redirect and resp.headers.get("location"):
            current = str(httpx.URL(current).join(resp.headers["location"]))
            continue
        return resp
    raise UnsafeURLError(f"too many redirects from {url}")
```
Keep `validate_public_url`'s existing signature; if it doesn't accept `resolver`, thread it the same way the current callers do. Document the residual DNS-TOCTOU window in a comment (full pinning is a follow-up; per-hop re-validation + no auto-redirect closes the redirect bypass, which was the exploitable part).
- [ ] **Step 3: Route every collector through `safe_get`.** Replace each raw `httpx.get(..., follow_redirects=True)` (`rss.py:15`, `youtube.py:48-52`, `newsapi.py:29`, `scrape.py`, `feed_discovery.py`) with `safe_get(...)`. For `youtube.py:~261`, pass the guarded `_fetch`/`safe_get` instead of the inline unguarded lambda.
- [ ] **Step 4: Run tests** — new SSRF tests pass, existing collector tests still pass (their injected `fetch` seams bypass `safe_get`, so they’re unaffected; where a test exercised the real default fetch, point it at `safe_get` with an injected resolver/transport).
- [ ] **Step 5: Commit** `fix(security): route all outbound fetches through SSRF-safe safe_get with per-redirect validation`.

---

## Batch B4 — Critical #3 (SEC): API auth + rate-limit + href XSS + HttpUrl + no exc leak

**Files:**
- Modify: `app/core/config.py` (`api_key: str | None = None`, plus rate-limit settings)
- Modify: `app/api/app.py` (auth dependency, rate-limit on `/runs` & `/resolve`, stop reflecting `str(exc)`)
- Modify: `app/api/schemas.py` + `app/core/config.py` `SourceConfig` (url → validated http(s))
- Modify: `app/services/render/html.py` (href scheme whitelist)
- Modify: `app/services/ratelimit.py` only if needed to wire `TokenBucket`
- Test: `tests/integration/test_api.py`, `tests/unit/test_html.py`

- [ ] **Step 1: href XSS (failing test first).** In `test_html.py`, add a case: an item with `url="javascript:alert(1)"` must NOT appear as a live `href`. Implement a `_safe_href(url)` that returns the url only if it starts with `http://`/`https://`, else `"#"` (or omit the link). Apply at `html.py:48`.
- [ ] **Step 2: URL validation at the boundary.** Make `ResolveIn.url`, and the `url` field on `SourceConfig`/`SourceIn` schema, reject non-http(s). Simplest: a pydantic field validator that calls the existing scheme check (avoid `HttpUrl` if it ripples type changes through storage; a `@field_validator` returning the str is lower-risk). Add a test that `PUT /api/sources` / `POST /resolve` rejects `file://`/`javascript:` with 422.
- [ ] **Step 3: Optional API-key auth.** Add `settings.api_key`. Write a FastAPI dependency `require_api_key`:
```python
def require_api_key(settings):
    def dep(authorization: str | None = Header(None), x_api_key: str | None = Header(None)):
        if not settings.api_key:
            return                      # open in local/dev when unset
        supplied = x_api_key or (authorization or "").removeprefix("Bearer ").strip()
        if supplied != settings.api_key:
            raise HTTPException(401, "invalid or missing API key")
    return dep
```
Apply as a dependency on the mutating routes (`PUT /api/sources`, `PUT /api/watchlist`, `POST /api/runs`, `POST /api/sources/resolve`). GET reads stay open. Tests: with `api_key` set, mutating routes 401 without the header and 200 with it; with `api_key` unset, all behave as today (keep existing tests green by leaving default `api_key=None`).
- [ ] **Step 4: Rate-limit `/runs` and `/resolve`.** Wire the existing `TokenBucket` (per-process) into a dependency for those two endpoints; configurable burst/refill via settings (sane defaults). Test that exceeding the bucket returns 429.
- [ ] **Step 5: Stop leaking internals.** Replace `raise HTTPException(422, detail=str(exc))` (app.py:103-104, 113-114) with a generic client message (`"could not resolve source"`) and `log.warning(... exc)` server-side. Update the test that asserted the SSRF message is echoed (test_api.py:223) to assert the generic message + a 4xx.
- [ ] **Step 6:** full suite + ruff. **Commit** `fix(security): optional API-key auth, rate-limit runs/resolve, href scheme whitelist, url validation, stop leaking exception text`.

---

## Batch B5 — Medium backend: dual FastAPI surface, YAML round-trip, pagination, state_delta

**Files:**
- Modify: `app/fast_api_app.py` + `app/api/app.py` (canonical surface)
- Modify: `app/api/config_store.py` (ruamel round-trip), `pyproject.toml` (add `ruamel.yaml`)
- Modify: `app/api/app.py` (paginate `list_runs`/`list_news`), `app/core/ports/storage.py` + `sqlite_backend.py` if offset needed
- Modify: `app/pipeline/agents.py` (`_make_event` state_delta decision)

- [ ] **Dual FastAPI surface:** make `app/fast_api_app.py` mount the `app/api` router (single source of routes/CORS), or document `fast_api_app.py` as scaffold-only and have it delegate to `create_app`. Pick one; add a comment stating which is canonical for deploy. Keep `catchup serve` working.
- [ ] **YAML round-trip:** add `ruamel.yaml`; in `config_store.py` load+dump with `ruamel.yaml.YAML()` round-trip mode so comments in `config/sources.yaml` survive `PUT /api/sources`. Test: a YAML string with a comment round-trips with the comment intact.
- [ ] **Pagination/limit caps:** `list_runs`/`list_news` accept `limit: int = Query(50, ge=1, le=200)` + `offset: int = Query(0, ge=0)`. Replace `dashboard`'s magic `list_news(limit=500)` with a named constant. Thread offset to storage if cheap; otherwise cap limit and note pagination follow-up. Tests for the bounds (422 on over-cap).
- [ ] **state_delta decision:** simplest defensible choice — delete the dead `EventActions(state_delta={})` plumbing in `_make_event` and add a one-line module comment: "Pipeline shares one in-process session (InMemoryRunner) and mutates `ctx.session.state` directly; a persistent session service (Firestore/Vertex, Plan 9) will require moving durable values to `state_delta`." This documents the Plan-9 constraint without a premature rewrite. (If trivially feasible, instead emit `state_delta` for `run_id`/`items`; prefer the documented-direct-mutation path to avoid risk.)
- [ ] Full suite + ruff. **Commit** `refactor(api): single canonical FastAPI surface, comment-preserving YAML round-trip, paginated/capped list endpoints; document state propagation`.

---

## Batch F1 — A11y: contrast, focus-visible, reduced-motion

**Files:**
- Modify: `frontend/app/globals.css` (token contrast + reduced-motion block)
- Modify: `frontend/components/layout/sidebar.tsx`, `frontend/components/digests/news-card.tsx`, `frontend/components/dashboard/run-health-card.tsx`, `frontend/app/digests/[runId]/page.tsx` (focus-visible rings; amber/cyan contrast)

- [ ] **Contrast:** darken the cyan link token used for NewsCard titles + "View detail"/"Back" links so it clears AA 4.5:1 on `--card`/white (e.g. `#0E7490`), and bump amber error *body* text on `amber-50` to `amber-800/900`. Prefer fixing the token in `globals.css` so it propagates; add `underline`/`hover:underline` on text links so color isn't the sole signal. (Cannot run an automated contrast checker here — pick values from the WCAG-known-good set: cyan-700 `#0E7490` ≈ 4.7:1 on white; amber-800 `#92400E` passes on amber-50.)
- [ ] **Focus-visible:** add explicit `focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none rounded-md` to sidebar nav `<Link>`s, NewsCard title `<a>`, run-health "View detail" link, and the detail-page "Back" link.
- [ ] **Reduced-motion:** add to `globals.css`:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```
- [ ] `npm run lint` + `npx tsc --noEmit` + `npm test` green. **Commit** `fix(a11y): AA-contrast link/error colors, focus-visible rings, prefers-reduced-motion`.

---

## Batch F2 — Route boundaries + shared AsyncBoundary

**Files:**
- Create: `frontend/app/error.tsx`, `frontend/app/not-found.tsx`, `frontend/components/common/async-boundary.tsx`
- Modify: the five page routes to use `<AsyncBoundary>` for the repeated loading/error/empty ladder
- Doc: a short comment/README note owning the client-render decision

- [ ] Add `app/error.tsx` ("use client", shows message + `reset()` button using existing `ErrorState`) and `app/not-found.tsx`.
- [ ] Build `<AsyncBoundary>` that takes `{ isLoading, error, isEmpty, skeleton, emptyState, children, onRetry }` and renders the right branch (DRYs the duplicated ladder across Dashboard/Digests/News/Sources/Watchlist). Migrate at least the simplest 2–3 pages to it; keep behavior identical.
- [ ] Document the rendering decision (client-rendered SWR console is intentional for an internal tool) in the frontend README (replacing the stale create-next-app README is part of F3).
- [ ] FE lint/tsc/test green. **Commit** `feat(fe): route error/not-found boundaries + shared AsyncBoundary; document client-render decision`.

---

## Batch F3 — zod boundary, list keys, color-only signals, README

**Files:**
- Modify: `frontend/lib/api.ts` (+ `frontend/lib/schemas.ts` create), add `zod` dep
- Modify: `frontend/components/watchlist/tag-editor.tsx:78`, `frontend/components/digests/news-card.tsx:81` (stable keys), sentiment dot, `output-links.tsx`, sidebar dead buttons, tap-target sizes
- Modify: `frontend/README.md` (real setup)

- [ ] **zod:** add `zod`; define schemas for the key API responses in `lib/schemas.ts`; in `request<T>` parse with `safeParse` and throw a normalized `ApiError` on mismatch; normalize `ApiError.message` so raw HTML/stack bodies don't reach toasts. Update `api.test.ts` to cover a malformed-response case. (Type the parsed result; keep existing call sites compiling.)
- [ ] **List keys:** `tag-editor.tsx:78` → `key={value}` (dedup guarantees uniqueness); `news-card.tsx:81` entities → `key={`${e.name}-${e.type}`}`.
- [ ] **Color-only signals:** sentiment — add a tiny up/down/neutral icon or letter beside the dot and keep the `aria-label`; category bars — add `role="img" aria-label="{label}: {count}"`; make `output-links.tsx` either real `<a download>` links or visibly de-emphasized static text with a *visible* "on API host" note; sidebar workspace/profile buttons — render non-interactive (`<div>`) or wire up, so they aren't focusable dead controls; bump icon action buttons (edit/delete/theme toggle) to ≥40px touch target (or add spacing) per WCAG 2.5.8.
- [ ] **README:** replace the default create-next-app README with real setup (env `NEXT_PUBLIC_API_BASE`, backend dependency on `:8000`, scripts).
- [ ] FE lint/tsc/test green. **Commit** `fix(fe): zod-validated API boundary, stable list keys, non-color status signals, larger tap targets, real README`.

---

## Final steps
- [ ] Full backend suite + ruff; full frontend lint/tsc/test — all green.
- [ ] Update `docs/BUILD-LOG.md` with a remediation entry (every batch, decisions: loop-aware bridge over nest-asyncio, safe_get chokepoint, optional API-key auth, a11y fixes).
- [ ] Update memory `progress-status.md`.
- [ ] Final code-review pass (subagent) over the whole branch.
- [ ] PR `fix/review-remediation → main` (commits as AhmedHeshamSakr, no AI trailers; remember to delete the head branch on merge per the stacked-PR lesson).
