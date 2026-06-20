# Local Desktop App — Design Spec

**Date:** 2026-06-20
**Status:** Approved (pending spec review)
**Branch:** `feat/scheduler` → new feature branch for implementation

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
  browser). A UI key field therefore POSTs to a backend endpoint that persists it and
  reconfigures the client in-process. This is safe **only on localhost** — if the app
  were ever exposed publicly without auth, anyone could overwrite/abuse the key. The
  backend binds `127.0.0.1` by default to make that hard, and the README warns against
  exposing it.
- You cannot hot-swap the port of the server you are currently using. So **port changes
  apply on next launch** (the launcher reads the saved port on boot). The **key** can be
  applied live (in-process) with no restart.
- `app/.env` is already gitignored and is what `Settings` reads (`env_file=("app/.env", ".env")`).
  It is the natural single local config store: the Settings page writes to it, the live
  process is updated, and the launcher reads the port from it on boot.

## Architecture

```
Catch-Up.app (macOS bundle, custom icon)
  └─ scripts/run.sh
       reads port from Settings (default 8000)
       probes port → start | reuse | next-free
       (first run) builds frontend/out if missing
       uvicorn 127.0.0.1:<port>  ← ONE process
         ├─ /            → serves frontend/out (static export) + SPA fallback
         └─ /api/*       → product REST API (existing) + new /api/settings
       waits /api/health → opens browser
```

### 1. Single-port serving

- Add `output: 'export'` to `frontend/next.config.ts`. `next build` emits `frontend/out/`.
- In `app/api/app.py` `create_app()` (the `catchup serve` surface), after registering
  `/api/*` routes, mount the static export at `/` with a **SPA fallback**: any GET that
  isn't `/api/*` and doesn't map to a real exported file returns the app shell so
  client-side routing handles it.
- Backend binds **`127.0.0.1`** by default (config: `host: str = "127.0.0.1"`).

**The one real obstacle — `digests/[runId]`.** A runtime run ID can't be pre-rendered at
build time. Resolution, in order of preference:
1. Make `app/digests/[runId]/page.tsx` a **client component** that reads `runId` via
   `useParams()` and fetches via SWR; serve it through the FastAPI SPA fallback.
2. If static export still rejects the dynamic segment, refactor the route to a query
   param: `/digests?run=<id>` (no dynamic segment → export is trivially clean).
3. Last resort: keep **two-port** mode (FastAPI + `next start`) behind the same launcher.

The implementation plan will try (1), fall back to (2), and only use (3) if both fail.

### 2. New backend routes (under `/api`, localhost-only)

A small `_require_localhost` dependency rejects non-loopback clients (`request.client.host`
not in `{127.0.0.1, ::1}`) → 403. Applied to the settings routes only (`/api/health`
stays public; the rest keep their existing `_require_api_key`).

- `GET /api/settings` → **non-secret** state only:
  `{ "app_port": 8000, "gemini_key_set": true, "host": "127.0.0.1" }`.
  Never returns the key value.
- `PUT /api/settings` → body `{ "google_api_key"?: str, "app_port"?: int }`.
  - Writes provided fields to `app/.env` (upsert KEY=VALUE, preserving other lines).
  - Updates the live `Settings` instance.
  - If `google_api_key` given: set `os.environ["GOOGLE_API_KEY"]` (overwrite) and call
    `configure_genai(settings)` so the next run uses it **without restart**.
  - Validate `app_port` is an int in `1024–65535`.
  - Response: `{ "applied": ["google_api_key"], "restart_required": ["app_port"] }`
    so the UI can tell the user what takes effect when.

> Note: `configure_genai` currently only sets `GOOGLE_API_KEY` when it's unset. The
> settings endpoint must **overwrite** (set `os.environ` directly) so a changed key takes
> effect. Verify the genai client reads the env per-call (it constructs per `run_digest`);
> if it caches at import, document the restart caveat instead of claiming live apply.

### 3. Settings page (`frontend/app/settings/page.tsx`)

- Client component. On load, `GET /api/settings`.
- Fields: **Gemini API key** (`type=password`, helper "applies immediately"), **Port**
  (number, helper "restart to apply"). Shows "✓ key configured" when `gemini_key_set`.
- Save → `PUT /api/settings`; toast (sonner is already a dep) reflects the
  `applied` / `restart_required` response.
- Add a nav link to Settings in the existing layout.

### 4. Launcher — `scripts/run.sh` + `Catch-Up.app`

`scripts/run.sh` (the real logic; the `.app` just calls it):
1. Resolve repo root; ensure deps (`uv` present; `agents-cli install` / `uv sync` as needed).
2. Read port: `uv run python -c "from app.core.config import Settings; print(Settings().app_port)"`
   (default 8000).
3. Probe port:
   - `curl -s 127.0.0.1:<port>/api/health` OK → **already running**, `open` browser, exit 0.
   - Port bound by something else → scan upward for the next free port, use it, print a notice.
   - Free → use it.
4. First run: if `frontend/out` missing → `(cd frontend && npm ci && npm run build)`.
5. `uv run uvicorn app.api.app:create_app --factory --host 127.0.0.1 --port <port>` (background).
6. Poll `/api/health` until healthy (timeout ~30s), then `open http://127.0.0.1:<port>`.
7. Trap to stop uvicorn on exit.

`Catch-Up.app` — minimal macOS bundle:
```
Catch-Up.app/Contents/
  Info.plist                 (CFBundleExecutable=run, CFBundleIconFile=AppIcon)
  MacOS/run                  (exec's scripts/run.sh, no visible Terminal)
  Resources/AppIcon.icns
```
A `scripts/make_app.sh` generates the bundle so it isn't a committed binary blob (keeps the
repo clean and lets users rebuild it). Desktop placement = user copies/aliases it.

### 5. PWA polish

- `frontend/public/manifest.webmanifest` (`name`, `short_name`, `display: standalone`,
  `start_url: /`, `theme_color`, icons 192/512).
- `frontend/public/` icons (PNG) + `frontend/app/layout.tsx` `<link rel="manifest">` (Next
  metadata `manifest` field).
- No service worker required for installability of a same-origin app; skip it (YAGNI). The
  manifest alone gives Chrome/Edge "Install app" → standalone windowed icon, as a bonus on
  top of the `.app` launcher.

### 6. App icon

Generate a simple placeholder icon (a "CU"/newspaper glyph) via a small script
(`scripts/make_icon.sh` using `sips`/`iconutil`, or a committed 1024×1024 PNG → `.icns` +
PWA PNGs). User can swap the source PNG later.

### 7. README "Run it yourself"

New top section in `README.md`:
- Prereqs: `uv`, Node 20+.
- Get a **free Gemini API key** (link to Google AI Studio).
- `git clone …`
- Build the launcher: `./scripts/make_app.sh` (or just `./scripts/run.sh`).
- Double-click `Catch-Up.app` (or run `./scripts/run.sh`) → browser opens.
- Open **Settings**, paste your Gemini key, Save. Optionally "Install app" for a PWA window.
- **Bold warning:** localhost-only, single-user. Do not expose to the internet without
  adding real authentication. Each self-hoster uses their own key.

## Testing

- **Backend (`tests/unit`, `tests/integration`):**
  - `GET /api/settings` returns non-secret shape; never leaks the key.
  - `PUT /api/settings` upserts `app/.env` (uses a tmp env path), updates live Settings,
    reports `applied`/`restart_required`; validates port range.
  - localhost guard: non-loopback client → 403.
  - Static serving: `/` returns the export index; unknown non-API path → SPA fallback;
    `/api/health` still works.
- **Frontend (`vitest`):** settings page renders, loads state, submits PUT; api-client method.
- **Launcher:** manual smoke check (documented in the plan); port-probe logic kept small
  and shell-testable where practical.

## Out of scope (YAGNI)

- Auth / multi-user / hosted URL.
- Service worker / offline mode.
- Windows/Linux launchers (macOS `.app` only; `run.sh` works cross-platform as fallback).
- Editing GNews/other keys in the UI (stay in `.env`).

## Risks

| Risk | Mitigation |
|---|---|
| Static export rejects `digests/[runId]` | Client-render → query-param refactor → two-port fallback (ordered) |
| genai client caches key at import | Verify per-call construction; else document restart caveat for key too |
| Port auto-pick confuses the PWA (pinned to default) | README notes PWA assumes default port; `.app`/`run.sh` always open the actual port |
| User exposes localhost app publicly | Bind `127.0.0.1`; localhost guard on settings; bold README warning |
