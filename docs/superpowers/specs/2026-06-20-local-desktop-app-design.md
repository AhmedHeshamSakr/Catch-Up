# Local Desktop App — Design Spec

**Date:** 2026-06-20
**Status:** Revised after Codex review (round 1) — pending re-review
**Branch:** `feat/local-desktop-app`

## Goal

Make Catch-Up runnable as a **single-user, local desktop app** on macOS with the
least possible "production" overhead:

1. **One double-clickable icon** on the desktop boots the whole stack and opens the console.
2. **Single port** — FastAPI serves the built Next.js console *and* `/api/*` from one process.
3. **Gemini API key + port configurable from the UI** (no editing files by hand).
4. **Public-repo instructions** so anyone can clone and run it the same way.

Explicit non-goal: this is **localhost-only, single-user**. No multi-tenant hosting,
no per-user auth, no shared cloud URL. The README must say so in bold.

## Constraints & honest framing

- The Gemini key is consumed **server-side** (the Python process calls Gemini, not the
  browser). A UI key field therefore PUTs to a backend endpoint that persists it and
  reconfigures the client in-process. This is safe **only on localhost**.
- You cannot hot-swap the port of the server you are currently using. **Port changes apply
  on next launch**; the **key** applies on the **next run / next LLM client** (not mid-run).
- `app/.env` is the local config store the Settings page writes and the launcher reads.
  **Precedence caveat (Codex #4):** `Settings` uses `env_file=("app/.env", ".env")`, and
  pydantic-settings gives the **later** file priority — so a root `.env`, if present, shadows
  `app/.env`. Mitigation: the desktop config is authoritative in `app/.env`; on startup the
  app logs a warning if a root `.env` also defines `google_api_key`/`app_port`. (We do not
  reorder the tuple to avoid changing existing server behavior.)
- **Import side effects (Codex #5):** importing the `app` package runs `app/__init__.py` →
  `from .agent import app`, and `app/agent.py` builds the full ADK pipeline + SQLite storage
  at module import. So nothing on the hot path (e.g. the launcher's port read) may import the
  `app` package. The launcher parses `app/.env` directly instead.

## Architecture

```
Catch-Up.app (macOS bundle, custom icon)
  └─ scripts/run.sh
       reads port by parsing app/.env directly (NO python import) — default 8000
       probes port → start | reuse-if-our-app | next-free-if-busy
       (first run) builds frontend/out if missing
       uvicorn 127.0.0.1:<port>  ← ONE process
         ├─ /api/*       → product REST API (existing) + new /api/settings
         └─ /  (catch-all, registered LAST)  → Next-aware static resolver over frontend/out
       waits /api/health (validates app marker) → opens browser
```

### 1. Single-port serving

- Add `output: 'export'` to `frontend/next.config.ts`. `next build` emits `frontend/out/`.
- **Desktop/static build uses same-origin URLs (Codex #3).** Build with
  `NEXT_PUBLIC_API_BASE=""` so `lib/api.ts` and `health-pill.tsx` issue **relative** requests
  (`/api/...`) against whatever origin/port served the page. Fix `health-pill.tsx` (and any
  other hardcoded default) to honor the empty base. `NEXT_PUBLIC_API_BASE` stays meaningful
  only for dev / two-port mode.
- **Next-aware static serving (Codex #2).** A plain `StaticFiles(html=True)` mount is wrong:
  with default `trailingSlash:false`, export emits `digests.html`, not `digests/index.html`.
  Implement a small catch-all (registered **after** `/api/*`) that resolves in order:
  1. exact file in `frontend/out`
  2. `<path>.html`
  3. `<path>/index.html`
  4. SPA fallback → `frontend/out/index.html`
  Never serve the fallback for `/api/*` (those 404 normally). Guard against path traversal
  (resolve and confirm the target stays inside `frontend/out`).

**The dynamic-route blocker — RESOLVED (Codex #1).** `digests/[runId]` cannot be statically
exported (a runtime run id has no `generateStaticParams`, and `"use client"` does not change
that). **Primary design: replace it with `/digests?run=<id>`** — a single static `digests`
page that reads the `run` query param client-side and fetches via SWR. This removes the only
dynamic segment, so `output:'export'` is clean. Update all links that point to
`/digests/<id>` to `/digests?run=<id>` and move the page logic from `[runId]/page.tsx` to the
`digests` page. (No `generateStaticParams` gymnastics; the query-param route is the design,
not a fallback.)

Backend binds **`127.0.0.1`** by default (`Settings.app_host = "127.0.0.1"`).

### 2. New backend routes (under `/api`)

**Settings security (Codex #6).** The settings routes write secrets to disk, so loopback bind
alone is insufficient (DNS-rebinding can hit `127.0.0.1` with an attacker-controlled `Host`).
Defense in depth on the **settings write** path:
- `TrustedHostMiddleware` (or an equivalent dependency) allowing only `localhost`,
  `127.0.0.1`, `[::1]` Host headers.
- A `_require_local_write` dependency on `PUT /api/settings` that additionally (a) confirms
  `request.client.host` is loopback and (b) rejects the request unless `Origin`/`Referer`,
  when present, is same-origin/loopback. 403 otherwise.
- `/api/health` stays public; existing `/api/*` keep their current `_require_api_key`.

Routes:
- `GET /api/settings` → **non-secret** state only:
  `{ "app_port": 8000, "app_host": "127.0.0.1", "gemini_key_set": true }`. Never the key value.
- `PUT /api/settings` → body `{ "google_api_key"?: str, "app_port"?: int }`.
  - Validate `app_port` ∈ `1024–65535`.
  - Persist via the atomic env writer (below).
  - Update the live `Settings` instance.
  - If `google_api_key` given: set `os.environ["GOOGLE_API_KEY"]` **directly (overwrite)** and
    call `configure_genai(settings)`. **Semantics (Codex #7):** `configure_genai` only sets the
    env var when unset, so the endpoint must overwrite `os.environ` itself; the change takes
    effect on the **next run / next genai client construction**, not mid-run. Response field
    names this honestly.
  - Response: `{ "applied": ["google_api_key"], "restart_required": ["app_port"] }`.

**Atomic env writer (Codex #8)** — `app/core/env_store.py` (or similar):
- Upsert `KEY=VALUE` lines, preserving all other lines/comments.
- dotenv-safe quoting/escaping of values (handle `#`, spaces, quotes, `=`, newlines).
- Write to a temp file in the same dir, `os.replace` for atomicity, `chmod 0600`.
- Process-level lock to serialize concurrent writes.
- Unit tests: values containing `#`, quotes, spaces; concurrent writes; crash leaves the
  original intact (temp-file pattern).

### 3. Settings page (`frontend/app/settings/page.tsx`)

- Client component. On load, `GET /api/settings`.
- Fields: **Gemini API key** (`type=password`, helper "applies on next run"), **Port**
  (number, helper "restart to apply"). Shows "✓ key configured" when `gemini_key_set`.
- Save → `PUT /api/settings`; sonner toast reflects `applied` / `restart_required`.
- Add a Settings nav link in the existing layout.

### 4. Launcher — `scripts/run.sh` + `Catch-Up.app`

`scripts/run.sh`:
1. Resolve repo root; ensure `uv` present (and `node`/`npm` for the first-run build).
2. **Read port without importing the `app` package (Codex #5):** parse `app/.env` directly
   (e.g. `grep '^APP_PORT=' app/.env | cut -d= -f2`), default `8000`.
3. Probe the port:
   - GET `127.0.0.1:<port>/api/health` and **validate the app marker** (Codex #9, see below).
     Match → **our app already running**: `open` the browser, exit 0. (No duplicate.)
   - Port answers but marker mismatches, or port is bound by something else → scan upward for
     the next free port, use it, print a one-line notice.
   - Free → use it.
4. First run: if `frontend/out` missing → `(cd frontend && npm ci && NEXT_PUBLIC_API_BASE="" npm run build)`.
5. Start `uv run uvicorn app.api.app:create_app --factory --host 127.0.0.1 --port <port>`
   (background). **Bind-race handling:** if uvicorn exits immediately with "address in use"
   (lost the race), retry the next free port.
6. Poll `/api/health` (marker-validated) until healthy (~30s timeout), then
   `open http://127.0.0.1:<port>`.
7. Trap to stop uvicorn on exit.

**Health marker (Codex #9).** Extend `/api/health` from `{"status":"ok"}` to
`{"status":"ok","app":"catch-up","version":"<pkg version>"}`. The launcher only treats a port
as "reuse" when `app == "catch-up"`, preventing false positives from unrelated local services.

`Catch-Up.app` — minimal macOS bundle generated by `scripts/make_app.sh` (not a committed
binary):
```
Catch-Up.app/Contents/
  Info.plist        (CFBundleExecutable=run, CFBundleIconFile=AppIcon)
  MacOS/run         (exec's scripts/run.sh, no visible Terminal)
  Resources/AppIcon.icns
```

### 5. PWA polish

- `frontend/public/manifest.webmanifest` (`display:standalone`, `start_url:/`, theme color,
  icons 192/512) + `<link rel="manifest">` via Next metadata. No service worker (YAGNI).
- README notes the PWA window assumes the **default** port; if the launcher had to pick a
  free port, use the browser the launcher opened.

### 6. App icon

`scripts/make_icon.sh` turns a committed 1024×1024 source PNG (simple "CU"/newspaper glyph)
into `AppIcon.icns` (`iconutil`) + PWA PNGs (`sips`). User can swap the source later.

### 7. README "Run it yourself"

New top section: prereqs (`uv`, Node 20+); get a **free Gemini key** (AI Studio link);
`git clone`; `./scripts/make_app.sh` (or just `./scripts/run.sh`); double-click `Catch-Up.app`;
open **Settings**, paste key, Save; optional PWA "Install app". **Bold warning:** localhost-only,
single-user — do not expose to the internet without real authentication; each self-hoster uses
their own key.

### Two-port fallback (Codex #10)

Only if single-port serving proves infeasible: run FastAPI + `next start` behind the same
launcher. This requires a **build without `output:'export'`** (export + `next start` is invalid),
so the fallback uses a separate Next config / disables export, and the launcher wires the backend
URL into the frontend. Single-port is the design; this is documented contingency, not a parallel
code path we build now.

## Testing

- **Backend (`tests/unit`, `tests/integration`):**
  - `GET /api/settings` shape; never leaks the key.
  - `PUT /api/settings` writes via the atomic env writer (tmp path), updates live Settings,
    overwrites `os.environ["GOOGLE_API_KEY"]`, reports `applied`/`restart_required`; port range
    validation.
  - env writer: `#`/quote/space values, concurrent writes, crash-safety, `0600`.
  - settings write guard: non-loopback client → 403; cross-origin `Origin` → 403; bad `Host` → 403.
  - static serving: `/` → index; `/digests?run=x` → digests page; `<path>.html` resolution;
    unknown path → SPA fallback; `/api/*` never falls back; path-traversal blocked;
    `/api/health` returns the marker.
- **Frontend (`vitest`):** settings page renders/loads/submits PUT; `/digests?run=` reads the
  query param and fetches; api-client + health-pill use the relative base when
  `NEXT_PUBLIC_API_BASE=""`.
- **Launcher:** port-read parses `app/.env` without importing `app`; marker validation logic;
  manual smoke check documented in the plan.

## Out of scope (YAGNI)

- Auth / multi-user / hosted URL; service worker / offline; Windows/Linux launchers
  (`run.sh` is the cross-platform fallback); editing GNews/other keys in the UI.

## Codex review #1 — dispositions

All 10 findings FIXED in this revision: #1 query-param route (blocker); #2 Next-aware
resolver; #3 same-origin build; #4 `app_port`/`app_host` + precedence note; #5 launcher reads
`.env` without importing `app`; #6 TrustedHost + Origin check on writes; #7 overwrite
`os.environ` + "next run" semantics; #8 atomic/quoted/0600 env writer; #9 health app marker;
#10 fallback disables export. Ledger persisted at `.claude/codex-reviews/`.
