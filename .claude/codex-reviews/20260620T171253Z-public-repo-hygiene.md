# Codex Review — Public-repo hygiene (Apache-2.0 license, expanded README, drop internal review tags)

- **Branch:** `feat/local-desktop-app`
- **Commit reviewed:** `2829362` (original) → fixes folded into `03b392d`
- **Reviewer:** `codex exec --sandbox read-only` · codex-cli 0.140.0 · gpt-5.5
- **Date (UTC):** 2026-06-20T17:12:53Z
- **Scope:** the public-repo hygiene milestone — `LICENSE` (Apache-2.0) + `NOTICE`, expanded `README.md`, added `ARCHITECTURE.md`, removal of inline `Codex #N` tags from `app/api/app.py` / `scripts/run.sh` / two test files, `.gitignore` entry.

## Findings ledger

| # | Finding | Confidence | Path / severity | Disposition |
|---|---------|-----------|-----------------|-------------|
| 1 | `NOTICE` named 5 Google-scaffold files but `Dockerfile` also carries a `Copyright 2026 Google LLC` Apache header and was omitted; the "All other source files are Ahmed's copyright" catch-all therefore contradicted the Dockerfile. | Medium/High | `NOTICE` / Med (licensing accuracy) | **FIXED** — added `Dockerfile` to the affected-files list and softened the catch-all to "Except where a file's own header states otherwise, all other files … are Copyright 2026 Ahmed Hesham." Verified: `git grep -l "Copyright.*Google LLC"` → all six files now listed, and the catch-all defers to any file's own header, so the statement is robust even if a file were missed. |
| 2 | README's new "kept for learning" section surfaces `docs/BUILD-LOG.md`, which at line 37 still says the remote is "(private)" (now public) and states a "no Claude signatures" commit rule. | Low/Medium | `docs/BUILD-LOG.md:37` / Low | **WON'T-FIX (historical-by-design)** — the line is an accurate point-in-time record (the repo *was* private when written), not a current-state contradiction. The user explicitly chose to keep `BUILD-LOG` as a portfolio artifact, and the README's "kept for learning" section explicitly frames these docs as a historical build record, which contextualizes it for readers. Not a critical-path (money/auth/data) issue, so the gate's hard line does not apply. Editing the journal would undermine its point-in-time integrity. |

## Verification performed (by Codex, read-only)
- README endpoints, config-var names, CLI commands, and the new repository-layout map were spot-checked against the actual code/tree — **matched**.
- README + ARCHITECTURE internal markdown links — **all resolve**.
- Google copyright headers present in all NOTICE-listed source files — **confirmed**.
- `Codex #N` removals are **comment/docstring-only** — Python `ast.parse` of the three changed `.py` files passed; `bash -n scripts/run.sh` passed; `git diff --check` clean.

## Post-fix state
- Finding 1 FIXED and re-verified locally (all Google-header files covered).
- Finding 2 dispositioned WON'T-FIX with reasoning (historical, user-directed keep, non-critical).
- No high-confidence or money/auth/data findings remained open.

**Gate result after fixes: READY** (the single Medium/High finding is fixed; the remaining finding is a verified, low-severity historical-by-design keep).
