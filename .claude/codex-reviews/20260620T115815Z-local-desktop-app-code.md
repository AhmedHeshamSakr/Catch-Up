# Codex Review — Local Desktop App (final CODE review)

- **Branch:** `feat/local-desktop-app`
- **HEAD reviewed:** 0e95ea1 (full `main...HEAD` diff)
- **Reviewer:** `codex exec --sandbox read-only` (codex-cli 0.140.0)
- **Date (UTC):** 2026-06-20T11:58:15Z
- **Verdict:** round 1 = **NOT READY** (2 high, 6 medium) → fixed → 4 more re-review rounds, each surfacing 1–2 medium robustness issues, all fixed → **round 5 = VERDICT: READY** (no remaining blocker/high/medium).
- **Re-review rounds (all FIXED):** r2 — launch-lock owner-PID steal + proactive shadow detection; r3 — ownerless-lock grace reclaim + `test_deploy_surface` health-marker regression; r4 — `stop.sh` validates PID is our uvicorn before kill; r5 — READY; nits fixed (Settings 422 message distinguishes `$`-in-key vs port; `frontend/README.md` dev-vs-export wording).
- **Cleared by Codex:** no DNS-rebinding/CSRF bypass in `_require_local_write` for the loopback threat model (security guard validated).

| # | Finding | Conf | Sev | Disposition |
|---|---|---|---|---|
| 1 | Static app same-origin only if built with `NEXT_PUBLIC_API_BASE=""`; plain/stale build bakes `localhost:8000` | high | high | **FIXED** — NODE_ENV-aware default (`production`→`""` same-origin) in `lib/api.ts` + `health-pill.tsx`; run.sh keeps explicit empty base; `.env.local.example` clarified |
| 2 | `upsert_env` rewrites FIRST duplicate, leaves later dups → dotenv (last wins) + `tail -1` use stale value → save ineffective | high | high | **FIXED** — rewrite first occurrence, DROP later duplicates (exactly one canonical line); test |
| 3 | dotenv quoting not round-trip safe for `${...}` (python-dotenv interpolates double-quoted) | high | medium | **FIXED** — single-quote literal style for special values w/o a single quote (no interpolation); `${HOME}` round-trip test |
| 4 | `read_port` not dotenv-compatible: ignores `export`, inline comments, no range check | high | medium | **FIXED** — shell parser handles `export `, strips inline comment, validates 1024–65535 |
| 5 | Concurrent launches race on one PID file → two servers / orphan | high | medium | **FIXED** — `mkdir` launch lock serializes; reuse short-circuit while waiting |
| 6 | `PUT /api/settings` mutates `os.environ`/settings BEFORE persist → 500 leaves live state changed | high | medium | **FIXED** — persist first, then apply live state |
| 7 | Parent dir not fsynced after `os.replace` (incomplete crash-safety) | med | medium | **FIXED** — fsync parent dir fd after rename (guarded) |
| 8 | Root `.env` shadows `app/.env`; UI says "saved" but next launch ignores it (warning-only) | high | medium | **FIXED** — `GET /api/settings` returns `shadowed_keys`; Settings page shows a warning banner |

No findings dismissed as false-positive; no deferrals. Re-review to confirm.
