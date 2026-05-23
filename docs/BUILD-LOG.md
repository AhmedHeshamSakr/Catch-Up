# Build Log — Catch-Up (News Intelligence Agent)

> **Purpose:** A traceable, chronological record of every significant decision, step, and change —
> so we can always reconstruct *how we got here, what was done, and why*. Updated as work proceeds;
> each entry links to the relevant commit(s). Git history is the ground truth; this is the narrative.

---

## 2026-05-23 — Session 1: Brainstorming → Foundation

### Phase: Brainstorming (design)
Explored the idea via the superpowers brainstorming workflow + a browser visual companion.

**Approved product:** production-grade, multi-agent **global news monitoring & catch-up platform** on
Google ADK. Collects from RSS / web scraping / news APIs / Google Search grounding across 4 categories
(AI&Tech, Business/Finance, World/Geopolitics, Gulf/MENA); Gemini categorizes, importance-scores,
summarizes (EN/AR), extracts entities; renders Excel + HTML dashboard + Markdown; scheduled + on-demand.

**Key decisions (with rationale):**
- **Architecture = Approach A** (full ADK `SequentialAgent` pipeline; collectors/renderers as thin
  custom `BaseAgent` wrappers over plain Python services). *Why:* determinism + cost control for a
  scheduled batch, with unified ADK observability and a single deployable.
- **Cost = free v1, config-swappable to GCP prod.** Swap-points behind interfaces: storage
  (SQLite→Firestore), scheduler (APScheduler→Cloud Scheduler), LLM provider (AI Studio↔Vertex). *Why:*
  run free now, scale to low-cost serverless prod without a rewrite.
- **Frontend = Next.js + shadcn/ui + Tailwind**; **FastAPI** bridges UI ↔ ADK pipeline.
- **Tenancy = architect multi-tenant (org_id/user_id from day 1), ship single-user v1.**
- **UI design language = "Signal"**: Inter + IBM Plex Mono numerics, emerald/cyan accents, light+dark
  with Auto=system default, enterprise sidebar, Lucide outline icons (no emoji). *Chosen over Editorial
  and Enterprise-Clean directions after side-by-side mockups.*
- **Seed sources:** ship curated defaults now; Ahmed swaps his list later.
- **Excel schema:** Date, Title, Summary(EN/AR), Category, Source, URL, Importance, Entities, Sentiment;
  master + per-category sheets.

### Phase: Foundation (setup)
- Initialized git repo; **local identity AhmedHeshamSakr `<a.hesham1221@gmail.com>`**; remote →
  `github.com/AhmedHeshamSakr/Catch-Up` (private). **Hard rule: no Claude signatures on any commit/PR.**
- Added `.gitignore`, `README.md`.
- Wrote design spec → `docs/superpowers/specs/2026-05-23-adk-catchup-agent-design.md`.
  - Commit: *"docs: project scope, README, and approved design spec"* (initial commit, pushed to `main`).
  - Commit: *"docs: resolve seed-source and Excel-schema decisions in design spec"*.
- Loaded ADK skills (`google-agents-cli-workflow`, `-scaffold`); verified tooling: **uv 0.11.3,
  agents-cli 0.2.0, Node 22.22, Python (uv-managed)**.
- Identified near-match reference samples: **`ambient-expense-agent`** (scheduled, no interactive user),
  **`deep-search`** (multi-agent + grounding + report), **`safety-plugins`** (guardrails).
- Inspected `agents-cli` scaffold output (temp reference project) to ground the implementation plan.

### Phase: Planning
- Confirmed structural decisions: **repo layout = agents-cli project at the repo root** (`app/` with
  `frontend/` as a sibling, exactly as agents-cli expects); **build approach = incremental "walking
  skeleton"** (6 plans, each ships working, testable software).
- Captured scaffold conventions: `Agent(...) + App(name="app")`, model alias `gemini-flash-latest`
  (preserve), monorepo-aware `pyproject.toml` (`packages=["app","frontend"]`),
  `tests/{unit,integration,eval}`, ruff + ty lint, Python 3.11–3.13.
- Wrote **Plan 1 — Walking Skeleton** →
  `docs/superpowers/plans/2026-05-23-plan1-walking-skeleton.md`: scaffold→relocate, domain model,
  Settings + source loader, SQLite storage behind a port (+ reusable contract tests), RSS collector,
  normalize/dedup, Markdown renderer, `run_digest()` orchestrator (per-source isolation), and CLI —
  full bite-sized TDD. Outcome when executed: `python -m app.cli run` produces a real Markdown digest
  from live RSS feeds. No LLM yet.
- **Plan decomposition:** P1 skeleton · P2 intelligence (LLM processing + digest editor + eval) ·
  P3 sources+outputs breadth (API/scrape/search + Excel/HTML) · P4 orchestration (ADK agent tree) +
  scheduler + FastAPI · P5 Next.js "Signal" console · P6 hardening + GCP production.

### Phase: Execution — Plan 1 (Walking Skeleton) ✅
Executed subagent-driven on branch `feat/walking-skeleton` (fresh implementer per batch + spec/quality review gate).
- **Tasks 0–1** (controller): scaffolded ADK project to repo root (prototype, AI Studio), set project identity, `uv sync`, added `feedparser/httpx/pyyaml/pydantic-settings`. Commits `8c9747a`, `798ea56`.
- **Batch A — Tasks 2–3** (domain model + Settings/source loader): commits `064bf8b`, `ed827ad`. Reviewed: APPROVED.
- **Batch B — Tasks 4–5** (StorageBackend port + reusable contract + SQLite adapter): commits `1f1e5ee`, `84d4237`. Reviewed: APPROVED.
- **Batch C — Tasks 6–8** (RSS collector, normalize/dedup, Markdown renderer): commits `5c36f47`, `890ac8c`, `21f0d29`. Reviewed: APPROVED (2 ruff nits noted).
- **Batch D — Tasks 9–10** (`run_digest()` + CLI + lint): commits `38220e2`, `47b615e`. Review: CHANGES_REQUIRED.
- **Fixes** (commit `1d5e498`): finalize runs as `FAILED` on unexpected errors (was leaving orphaned `RUNNING`); correct RSS UTC parsing (`calendar.timegm` vs `time.mktime` — mattered on non-UTC hosts); graceful CLI errors; documented title-dedup tradeoff. Added regression test for the FAILED-finalize path. Enums upgraded to `StrEnum` (values preserved) during lint.
- **Result:** `uv run pytest tests -q` → **16 passed**; `uv run --extra lint ruff check app tests` → clean; live `python -m app.cli run` → 80 items, real Markdown digest in `output/`. All commits authored solely by AhmedHeshamSakr, no AI trailers.
- Note: lint tools live in the `lint` optional extra — run lint via `uv run --extra lint ruff check app tests`.

### Phase: Plan 2 — Intelligence (planning)
- **PR #1 merged → `main`** (mergeCommit `a8f7b4f`). Branched `feat/intelligence`.
- Consulted ADK code patterns: `Agent(output_schema=PydanticModel, output_key=…)` run via `InMemoryRunner` for structured output.
- Wrote **Plan 2 — Intelligence** → `docs/superpowers/plans/2026-05-23-plan2-intelligence.md`: enrichment schemas, watchlist boosts, processing agent (category / importance / EN-AR summaries / entities / sentiment), digest-editor narrative, richer Markdown, and `run_digest` integration with graceful degradation. LLM sits behind an injectable boundary (`EnrichFn`/`NarrateFn`) so deterministic logic is TDD-tested with fakes (no network); the real Gemini call is validated by a live smoke. Formal `agents-cli eval` deferred to post-Plan-4 (needs the conversational root agent).

### Phase: Execution — Plan 2 (Intelligence) ✅
Executed subagent-driven on `feat/intelligence` (implementer per batch + spec/quality review gate).
- **Batch E — Tasks 1–2** (enrichment schemas + intelligence settings; watchlist loader + boost): commits `45074b1`, `6056038`; lint fix `7709257`. Reviewed: APPROVED.
- **Batch F — Tasks 3–4** (processing agent + merge/boost/threshold; digest-editor narrative): commits `5a26070`, `5c7d788`. Reviewed: APPROVED. Follow-up fix `9294352`: moved item data to the user message (rules stay in the agent instruction) so the model never sees a literal `{items_json}` placeholder.
- **Batch G — Tasks 5–6** (richer Markdown: narrative + summaries + importance badge; `run_digest` integration with two-level graceful degradation): commits `4017321`, `ff03438`. Reviewed: APPROVED.
- **Task 7** docs (`fe3faff`): processing golden seed + README run instructions.
- **Live smoke (real Gemini, AI Studio key):** 3 sample items enriched correctly — categories right, importance calibrated (0.70 / 0.80 / 0.05 for a trivial typo), accurate EN + Arabic(MSA) summaries, entities (OpenAI, Qatar Investment Authority), and a coherent "what matters most" narrative. The real LLM path is validated.
- **Result:** `uv run pytest tests -q` → **30 passed**; `uv run --extra lint ruff check app tests` → clean. All commits authored solely by AhmedHeshamSakr.
- **Known follow-up:** ADK sync `runner.run` is deprecated; migrate `adk_enrich`/`adk_narrate` to `run_async` in Plan 4 (async agent tree).

### Next
- **PR #2 open** → https://github.com/AhmedHeshamSakr/Catch-Up/pull/2 (`feat/intelligence` → `main`), awaiting review/merge.
- After merge → **Plan 3 — Sources & outputs breadth:** API + scrape + Search-grounding collectors (rate limiting, SSRF, resilience) + Excel + HTML renderers.
