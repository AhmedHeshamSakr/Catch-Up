# Codex Review — Local Desktop App spec

- **Branch:** `feat/local-desktop-app`
- **HEAD reviewed:** d955e5b (spec round 1)
- **Reviewer:** `codex exec --sandbox read-only` (codex-cli 0.140.0)
- **Date (UTC):** 2026-06-20T10:44:38Z
- **Verdict:** round 1 = NOT READY (1 blocker, 6 high, 3 medium). All FIXED in spec revision (commit 96cf625).
- **Round 2 re-review:** **VERDICT: READY** — no remaining blocker/high. Codex confirmed `NEXT_PUBLIC_API_BASE=""` stays `""` (relative, via `??`), `/digests?run=` removes the export blocker, resolver/traversal/`/api` exclusion sound, TrustedHost+Origin guard sufficient for the localhost threat model, `os.environ` overwrite required, atomic env writer + health marker adequate, uvicorn importing `app` at start is status quo (not a regression).

| # | Finding | Codex conf | Severity | Disposition |
|---|---|---|---|---|
| 1 | `digests/[runId]` cannot static-export; `"use client"`+`useParams` doesn't fix it | high | blocker | **FIXED** — primary route is now `/digests?run=<id>` (no dynamic segment); spec §1 |
| 2 | `StaticFiles(html=True)` not Next-aware (`trailingSlash:false` → `$path.html`) | high | high | **FIXED** — custom resolver exact→`.html`→`/index.html`→SPA fallback; never `/api/*`; traversal-guarded; spec §1 |
| 3 | Frontend hardcodes `http://localhost:8000` (`lib/api.ts:43`, `health-pill.tsx:8`) | high | high | **FIXED** — desktop build sets `NEXT_PUBLIC_API_BASE=""` (same-origin relative); fix health-pill default; spec §1 |
| 4 | No `app_port`/`app_host` in Settings; root `.env` shadows `app/.env` | high | high | **FIXED** — add fields; document pydantic env_file precedence; writer targets `app/.env`; startup warning; spec Constraints |
| 5 | `app/__init__.py` import builds ADK pipeline + SQLite at import time | med | high | **FIXED** — launcher reads port by parsing `app/.env` directly, no `app` import; spec Constraints/§4 |
| 6 | Loopback bind + `client.host` insufficient vs DNS-rebinding/CSRF on secret-writing PUT | high | high | **FIXED** — TrustedHost (loopback Host) + Origin/Referer check on write path; spec §2 |
| 7 | `configure_genai` doesn't overwrite `GOOGLE_API_KEY`; live apply caveat correct | high | medium | **FIXED** — endpoint overwrites `os.environ` + mutates Settings; "next run" semantics; test; spec §2 |
| 8 | `.env` upsert underspecified (atomicity/quoting/perms) | high | medium | **FIXED** — atomic `os.replace`, dotenv quoting, `0600`, lock, tests; spec §2 |
| 9 | `/api/health` `{"status":"ok"}` too generic for reuse-if-healthy | high | medium | **FIXED** — add `app`/`version` marker; launcher validates; bind-race retry; spec §4 |
| 10 | Two-port fallback invalid while `output:"export"` enabled | med | medium | **FIXED** — fallback disables export / separate config; documented contingency only; spec §Two-port fallback |

**Verified-OK by Codex:** no `next/image` blocker; no cookies/headers/server-actions in frontend; serving at `/` needs no `basePath`/`assetPrefix`; `create_app()` signature is factory-compatible (the import side effect, #5, is the real risk).

No findings dismissed as false-positive; no deferrals. Re-review to confirm before implementation.
