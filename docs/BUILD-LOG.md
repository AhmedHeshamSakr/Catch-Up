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

### Phase: Plan 3 — Output breadth (planning)
- **PR #2 merged → `main`** (`3ba019a`). Branched `feat/outputs`.
- **Lint regression caught on `main`:** `markdown.py` had an unused `Importance` import and `test_markdown_intel.py` an unsorted import (2 ruff F401/I001 errors). Root cause: the IDE auto-fixed the *working tree* on save *after* the implementer committed, so the "ruff clean" checks ran on the fixed working copy while the committed/merged blob kept the errors. Captured the IDE fix as the first commit on `feat/outputs` (`b4e00eb`); ruff now clean on the committed state. (Process note: run lint on a clean tree / in CI, not just the working copy.)
- **Scope decision:** split the original "sources & outputs" — do **outputs first** (Excel + HTML; no keys, fully testable, immediate visible value), then source breadth next. Roadmap shifts: **Plan 3 outputs · Plan 4 source breadth (API/scrape/search) · Plan 5 orchestration+API · Plan 6 console · Plan 7 prod.**
- Wrote **Plan 3 — Output breadth** → `docs/superpowers/plans/2026-05-23-plan3-outputs.md`: Excel workbook (master + per-category sheets via openpyxl), Signal-themed XSS-safe HTML dashboard, `run_digest` writes md+xlsx+html, no-key render smoke. Full TDD, no API keys.

### Phase: Execution — Plan 3 (Output breadth) ✅
Executed subagent-driven on `feat/outputs` (implementer per batch + spec/quality review gate).
- **Batch H — Tasks 1–3** (openpyxl dep; Excel workbook master + per-category sheets; Signal-themed XSS-safe HTML dashboard): commits `91e017d`, `5103c3d`, `6c6d9c6`. Reviewed: APPROVED (HTML escaping audit confirmed every dynamic field escaped via `_esc`).
- **Batch I — Tasks 4–5** (write xlsx+html in `run_digest`; no-key render smoke + README): commits `b119f1a`, `b5775e6`. Reviewed: APPROVED.
- Also fixed the `main` lint regression as the branch's first commit (`b4e00eb`).
- **Result:** `uv run pytest tests -q` → **36 passed**; `uv run --extra lint ruff check app tests scripts` → clean; `uv run python scripts/render_smoke.py` → `output/digest-smoke01.{md,xlsx,html}`. Each `run_digest` now emits all three formats. All commits authored solely by AhmedHeshamSakr.

### Phase: Plan 4 — Source breadth (planning)
- **PR #3 merged → `main`**. Branched `feat/sources`.
- **Decision:** news-API provider = **GNews** (generous free tier, search + lang/country, good for Arabic/Gulf).
- Wrote **Plan 4 — Source breadth** → `docs/superpowers/plans/2026-05-23-plan4-sources.md`: token-bucket rate limiter, SSRF URL guard (scheme + private-IP rejection), GNews API collector, web-scrape collector (CSS selector, SSRF-guarded), and `run_digest._collect` dispatch by `SourceType` (RSS/API/scrape). All deterministic parts TDD-tested (injectable fetch, no network); live GNews smoke-validated with the key.
- **Scoped out to Plan 5:** Google Search grounding (needs an ADK grounding-metadata spike) + the sync `runner.run` → `run_async` migration (shares the runner work). Roadmap: **Plan 4 sources(GNews+scrape) · Plan 5 search-grounding + async · Plan 6 orchestration+API · Plan 7 console · Plan 8 prod.**

### Phase: Execution — Plan 4 (Source breadth) ✅
Executed subagent-driven on `feat/sources` (implementer per batch + spec/quality review gate).
- **Batch J — Tasks 1–4** (TokenBucket rate limiter; SSRF URL guard; GNews API collector + api/scrape config fields; web-scrape collector): commits `fb468ee`, `a251f96`, `0078679`, `3624aa7`. Reviewed: APPROVED (confirmed `scrape.fetch_page` calls the SSRF guard before httpx).
- **SSRF hardening** (`0a6fd5f`): reject empty DNS resolution + added multicast/reserved/unspecified test coverage (from the review's minor finding).
- **Batch K — Task 5** (wire RSS/API/scrape dispatch into `run_digest._collect(source, settings)` + disabled example sources): commit `744fd93`. Reviewed: APPROVED, no issues.
- **Task 6** docs (`eda83ab`): README source types + GNews key.
- **Live GNews smoke:** `newsapi.collect` with a real key returned 10 current AI headlines (title + source + URL). API path validated.
- **Result:** `uv run pytest tests -q` → **52 passed**; `uv run --extra lint ruff check app tests scripts` → clean. `run_digest` now collects from RSS + GNews + scraped pages. All commits authored solely by AhmedHeshamSakr.

### Phase: Pivot — quota wall → API + Console (planning)
- **PR #4 merged → `main`.** Started a Plan 5 (search-grounding) spike to learn ADK's `google_search` grounding-metadata shape; confirmed `from google.adk.tools import google_search` imports, but hit **Gemini `429 RESOURCE_EXHAUSTED`** — AI Studio free-tier quota exhausted for the day. Live LLM validation blocked until reset.
- **Decision (with Ahmed):** pivot to **quota-free** work — the **FastAPI API** then the **Next.js console** (both operate on stored data + config; only "Run now" needs Gemini). Search-grounding + the `run_async` migration deferred until quota resets.
- Reused the branch as `feat/api`. Wrote **Plan 5 — FastAPI API** → `docs/superpowers/plans/2026-05-24-plan5-api.md`: extend storage with `list_runs`/filterable `list_news`; `config_store` (sources/watchlist write); `create_app()` factory with CORS + `/api` router (health, dashboard, runs, news, sources/watchlist CRUD, run trigger); `catchup serve` CLI. TestClient TDD; run trigger injected so tests need no Gemini quota.
- **Roadmap now:** Plan 5 API · Plan 6 Next.js console · Plan 7 search-grounding + async · Plan 8 orchestration (ADK agent tree) · Plan 9 GCP prod.

### Phase: Execution — Plan 5 (FastAPI API) ✅
Executed subagent-driven on `feat/api` (implementer per batch + spec/quality review gate). Fully quota-free.
- **Batch L — Tasks 1–2** (storage `list_runs`/filterable `list_news` + columns; `config_store` write): commits `c78cbbd`, `ae6f701`, `8e55c7b`. Review: CHANGES_REQUIRED → **fixed** (`fbba973`): added a PRAGMA-based `ADD COLUMN` migration to `init_schema` (existing dev DBs no longer crash), created the missing indexes, and added combined-filter/ordering + migration tests.
- **Batch M — Tasks 3–4** (`create_app()` factory: CORS + `/api` router — health, dashboard, runs, news, sources/watchlist CRUD, run trigger; TestClient tests): commits `7921d35`, `9f81536`. Reviewed: APPROVED (run trigger injected → no test touches Gemini). Minor forward-looking notes: add CORS `allow_credentials` when auth lands; use `COUNT` for dashboard at scale.
- **Batch N — Task 5** (`catchup serve` CLI + README API table): commit `7ede503` + doc fix `…` (auto-docs at `/docs`).
- **Result:** `uv run pytest tests -q` → **62 passed**; `uv run --extra lint ruff check app tests scripts` → clean. `uv run python -m app.cli serve` boots; `/api/health` + `/docs` return 200. All commits authored solely by AhmedHeshamSakr.

### Phase: Plan 6 — Next.js "Signal" console (planning)
- **PR #5 merged → `main`** (34 commits). Synced `main`, branched `feat/console`. Wrote **Plan 6** → `docs/superpowers/plans/2026-05-24-plan6-console.md`: a Next.js console (`frontend/`, sibling of `app/`) consuming the FastAPI, in the "Signal" design language.
- **Scope decision (API-backed slice):** ship the 4 screens the API fully supports today — **Dashboard, Digests (list + detail), Sources (CRUD), Watchlist** — plus a filterable **News** feed (the `/api/news` endpoint is already rich) and a global **Run now** action. The spec's other screens (Categories, Pipeline, Schedule, Settings) need new backend endpoints → deferred to later plans. Keeps Plan 6 quota-free and shippable.

### Phase: Execution — Plan 6 (Next.js Console) ✅
Executed subagent-driven on `feat/console` (fresh implementer per task + a review gate each). Stack: **Next.js 16** (App Router, React 19), TypeScript, Tailwind v4, **shadcn/ui on `@base-ui/react`** (not Radix — surfaced during scaffold), `next-themes` (Auto = system default), SWR, Lucide, Inter + IBM Plex Mono, Vitest + RTL. All tests offline (mocked `fetch`).
- **T1 — Scaffold + Signal shell** (`e898804`): enterprise sidebar, theme toggle (light/dark/system), fonts, Signal CSS tokens (light/dark), health pill. Review fixes: moved `shadcn` CLI to devDeps, deleted boilerplate `public/*.svg`, HealthPill unmount guard.
- **T2 — API client + hooks** (`ca2bc61`): typed `lib/api.ts` (+`ApiError`), `lib/hooks.ts` (SWR), `lib/format.ts`. 18 offline tests. Review fixes: header-merge order in `request()`, `useNews` default `{}` + normalized SWR key.
- **T3 — Dashboard** (`0e2275c`): stat cards, "what matters most" narrative, category breakdown bars, run-health card, **Run now** button (toasts, `mutate`). Shared `ImportanceBadge`/`StatusBadge`/`EmptyState`/`ErrorState`. Review fixes: `"use client"` on ErrorState, `font-sans` on StatusBadge.
- **T4 — Digests** (`cc240c2`): runs table + run detail (`useParams` under Next 16) with items grouped by category, defensive `source_errors`, `OutputLinks` (read-only server paths), reusable `NewsCard`. Carry-over polish landed in T7.
- **T5 — Sources CRUD** (`834bafc`): type-aware add/edit dialog (native `<select>` + key-remount form state), live enable toggle; **every mutation sends the full list** via `putSources` (backend replaces wholesale). Pure `lib/sources.ts` (`fieldsForType`/`validateSource`) with 16 tests. Review fix: literal `&apos;` in a JSX attribute.
- **T6 — Watchlist + News** (`5b43c88`): tag editor (case-insensitive dedupe, tested `addTag`) with dirty-tracked save; filterable news feed (category/importance/limit). Key-remount seeding avoids the repo's `react-hooks/set-state-in-effect` lint error.
- **T7 — Polish + docs** (`240dff9`, this commit): full-row click nav on the digests table (keyboard links preserved); emoji/`dangerouslySetInnerHTML` sweep clean; README "Web Console" section; this log.
- **Result:** `cd frontend && npm test` → **39 passed (5 files)**; `npx tsc --noEmit`, `npm run lint`, `npm run build` all clean (7 routes). Every commit authored solely by AhmedHeshamSakr.

### Phase: Plan 6 merged + live smoke
- **PR #6 merged → `main`.** Ran a live stack smoke (`app.cli serve` + curl). Findings: API + all 6 console endpoints return valid JSON (confirmed via `node JSON.parse`); a real digest collected **80 RSS items**, run finalized `partial` (graceful degradation worked). Surfaced two issues that motivated Plan 7's scope: (a) **`GOOGLE_API_KEY` lives in `app/.env`** but `serve` (from repo root) read only `./.env` → "No API key"; (b) the deprecated sync `runner.run` runs the LLM in a worker thread, so its error escaped as a noisy unhandled traceback (run still degraded correctly, just ugly).

### Phase: Plan 7 — Search grounding + run_async (research + planning)
- Branched `feat/search-grounding`. Researched ADK `google_search` grounding offline (no quota) → `docs/superpowers/research/2026-05-24-plan7-search-grounding.md`. Key facts: `from google.adk.tools import google_search`; **`google_search` cannot coexist with `output_schema`** (search-only agent); cited sources at `event.grounding_metadata.grounding_chunks[*].web.{uri,title,domain}` (uri is a Vertex redirect URL; metadata may be on a non-final event → keep last non-None); `run_async` propagates exceptions cleanly; fully offline-testable via synthetic `GroundingMetadata` Pydantic objects. Wrote **Plan 7** → `docs/superpowers/plans/2026-05-24-plan7-search-grounding.md`.

### Phase: Execution — Plan 7 (Search grounding + run_async) ✅
Executed subagent-driven on `feat/search-grounding`. Fully offline (model boundary injected); only a final live grounding spike defers until the Gemini quota resets.
- **T1 — Key loading + ADK runtime** (`bdc93c1`): `Settings.env_file=("app/.env",".env")` (root `.env` wins when both set the key; merges so `app/.env` loads when `./.env` lacks it); new `app/pipeline/adk_runtime.py` — `ensure_api_key()` (sets `os.environ` for ADK's google client), async `_run_text_async`, sync bridge `run_agent_text()` via `asyncio.run`. Confirmed `create_session` is the async API in ADK 1.34.x.
- **T2 — run_async migration** (`2122cc3`): `adk_enrich`/`adk_narrate` now call `run_agent_text` (kills the sync-runner deprecation + worker-thread exception escape); dropped unused `InMemoryRunner`/`types` imports. 65 tests stay green (existing tests inject `EnrichFn`/`NarrateFn` fakes).
- **T3 — `parse_grounding`** (`1cc77a7`): pure harvester in `app/services/search.py` — `grounding_chunks[*].web` → `RawItem` (url=uri, title=title||domain||uri, `published_at=None`, dedup by uri, defensive getattr). 5 offline tests with synthetic `GroundingMetadata`.
- **T4 — Collector + wiring** (`145a968`): `build_search_agent` (`tools=[google_search]`, NO `output_schema`), `adk_ground` (run_async, keeps last non-None grounding_metadata), `collect(..., ground=adk_ground)` injectable boundary; wired `SourceType.SEARCH` into `runner._collect` (removed the stale "Plan 5" comment); added a **disabled** `search-ai-breakthroughs` source to `config/sources.yaml`. 2 injected-ground tests.
- **Result:** `uv run pytest tests -q` → **72 passed**; `uv run --extra lint ruff check app tests` clean. Every commit authored solely by AhmedHeshamSakr.
- **Deferred (needs Gemini quota):** live grounding spike — confirm which stream event carries `grounding_metadata`, redirect-URL resolvability, `web.domain` null on the Gemini API backend; then flip the search source `enabled: true`.

### Phase: Plan 7 merged + social-monitoring discussion
- **PR #7 merged → `main`.** Discussed agent architecture with Ahmed: current product agents are `news_processor`/`digest_editor`/`search_collector` (3 specialists) + a dead scaffold `root_agent`; orchestration is plain-Python `run_digest`, not yet an ADK tree (Plan 8). Agreed the core 3 are right; the valuable additions are a **quality safety net** (offline eval/judge + a *selective* faithfulness guardrail) and semantic dedup — designed but **parked** (see `~/.claude/plans/frolicking-sauteeing-forest.md`).
- **New must-have feature raised:** monitor followed **social/video accounts** (LinkedIn, X, YouTube). Scoped by feasibility — **YouTube only for v1** (clean & free); X (paid/bridge) and LinkedIn (no clean API; ToS/legal risk) deferred behind the same pluggable collector port. Transcript approach: caption lib + Whisper fallback (Ahmed's ASR expertise).

### Phase: Execution — YouTube channel monitoring ✅
Executed subagent-driven on `feat/youtube-source` (off merged `main`). Fully offline (every external call injected); summary/Whisper live paths defer to quota/infra.
- **Y1 — Backend collector** (`1f9e1cb`): `SourceType.YOUTUBE`; `SourceConfig.channel_id` + `Settings.youtube_whisper_enabled`/`whisper_model`; `app/services/youtube.py` — `fetch_channel_feed` (free channel RSS `feeds/videos.xml?channel_id=`), `parse_channel_feed` (feedparser `yt_videoid`/`media_description`, UTC via `calendar.timegm`), `get_transcript` (youtube-transcript-api v1.2.4 → lazy Whisper fallback → None), `build_youtube_summary_agent`/`adk_summarize` (via `adk_runtime`), `collect(..., storage=, fetch=, transcript=, summarize=)` that **dedups against storage BEFORE transcribing/summarizing** (no wasted cost on seen videos); `app/services/youtube_resolve.py` (`@handle`/URL→`UC…`, SSRF-guarded); `app/prompts/youtube_summary.md` (anti-injection); wired `SourceType.YOUTUBE` into `runner._collect` (threaded `storage`); disabled MKBHD example in `sources.yaml`; deps `youtube-transcript-api` (core) + `whisper` optional extra (`yt-dlp`/`faster-whisper`, lazy-imported). 21 offline tests. Review fixes: SSRF guard on resolver, real-error log level, dead-code removal.
- **Y2 — Console support** (`977c53b`): frontend `youtube` SourceType + `channel_id` field + label; `fieldsForType`/`REQUIRED_BY_TYPE`/`validateSource` extended; type-aware Channel ID input in the Sources form; table target fallback. 42 frontend tests.
- **Result:** backend `uv run pytest tests -q` → **93 passed**, ruff clean; frontend `npm test` → **42 passed**, tsc/lint/build clean. Every commit authored solely by AhmedHeshamSakr.
- **Deferred (needs Gemini quota / opt-in infra):** live `adk_summarize` transcript→summary; the Whisper fallback (`whisper` extra, for Arabic/no-caption); live end-to-end against a real channel.

### Phase: Execution — Quality Safety Net (eval/judge + faithfulness guardrail) ✅
Executed subagent-driven on `feat/quality-safety-net` (stacked on PR #8). Plan: `docs/superpowers/plans/2026-05-24-quality-safety-net.md`. Decision: a **custom offline eval harness** (not native `agents-cli eval`, which targets the conversational scaffold `root_agent` — mismatch for our structured-output agents; the repo had already deferred it). Both safeguards build/test fully offline (judge/critic injected); live runs defer to quota.
- **Q-A — Eval/judge loop** (`f0de92e`): `app/pipeline/eval_schema.py` (`DimensionVerdict`/`EnrichmentVerdict(s)`/`FaithfulnessVerdict(s)`); `app/prompts/faithfulness_rubric.md` (single rubric source — faithfulness incl. obeyed-injection, category, importance band, AR); `app/pipeline/judge.py` (`build_judge_agent` `output_schema=EnrichmentVerdicts`, `adk_judge` via `adk_runtime`, `JudgeFn`); `app/pipeline/eval_score.py` (`aggregate`/`compare`, thresholds — faithfulness 0.9 strictest); `tests/eval/fixtures/enrichment_reference.json` (10 cases, ≥1 adversarial per dimension); `scripts/eval_enrichment.py` (`run_eval` offline / `--live`). 33 offline tests. Review fixes: rubric composed into judge prompt via `{{RUBRIC}}` placeholder (single source), `_dim_verdict` annotation, `--live` key guard.
- **Q-B — Faithfulness guardrail** (`8fbbf6d`): `app/pipeline/critic.py` (`build_critic_agent` `output_schema=FaithfulnessVerdicts` reusing the rubric via `{{RUBRIC}}`; `select_for_critique` — HIGH-importance OR watchlisted, via `watchlist_matched` extracted from `apply_boost`; `apply_verdicts` — flag/downrank/replace, default **downrank+flag** so hallucinated summaries are never shown; `adk_critique`/`CriticFn`); `Settings.critic_*` knobs; `DigestRun.flagged`/`critic_verdicts`; new graceful-degradation **critic stage** in `run_digest` after processing (counts recomputed post-critic; render fallback no longer resurrects flagged items). 26 offline tests. Review fix: guarded 4 more `run_digest` integration calls against a latent live-critic path (`critic=` injected).
- **Result:** `uv run pytest tests -q` → **152 passed** (offline); `uv run --extra lint ruff check app tests scripts` clean. Every commit authored solely by AhmedHeshamSakr.
- **Deferred (needs Gemini quota):** live `adk_judge`/`adk_critique`; `scripts/eval_enrichment.py --live`; AR-dimension judging (Arabic-capable judge model).

### Phase: Live dev test + "paste-a-link" source resolution ✅
- Ran the full stack for the user (`app.cli serve` :8000 + `npm run dev` :3000). UX question surfaced: adding a newspaper/YouTube channel via the console required the exact RSS feed URL / `UC…` id — not a plain link. (Also noticed: the console's PUT round-trip reformats `config/sources.yaml` and drops comments — known YAML-writer limitation; reverted the test-time reformat.)
- Built **paste-a-link resolution** on `feat/source-resolve` (stacked on #9). Plan: `docs/superpowers/plans/2026-05-24-source-resolve.md`.
  - **L1 — Backend** (`16f3fa8`): `app/services/feed_discovery.py` (`discover_feed` — SSRF-guarded, BeautifulSoup `<link rel=alternate type=rss/atom>` → absolute feed URL, injectable fetch); `POST /api/sources/resolve` (`ResolveIn`/`ResolveOut`; youtube→`resolve_channel_id`, rss→`discover_feed`; both injectable into `create_app`; errors mapped to 422). 14 offline tests.
  - **L2 — Console** (`78c5c64`): `api.resolveSource(type,url)`; a "paste a link" row + **Resolve** button in the Sources form (youtube/rss) that auto-fills `channel_id`/`url` (+name), with toasts. 43 frontend tests.
  - **Result:** backend **166 passed**, frontend **43 passed**; ruff/tsc/lint/build clean. Commits authored AhmedHeshamSakr.

### Phase: Stacked-merge fixup
- PRs #9/#10 were stacked with non-main bases and their head branches weren't deleted on merge, so they merged into intermediate branches — `main` had only #8. **PR #11** brought #9+#10 onto `main` (clean linear FF from `feat/source-resolve`). Lesson: delete the head branch on each stacked-PR merge so GitHub auto-retargets the next PR to `main`.

### Phase: Execution — Plan 8 (ADK agent-tree orchestration) ✅
Goal (Ahmed): **everything must be ADK**. Branched `feat/orchestration` off the now-complete `main`. **Approach = Option B** (the tree IS the orchestration; `run_digest` runs it) so the CLI/API run *through* ADK. Plan: `docs/superpowers/plans/2026-05-24-plan8-orchestration.md`.
- **O1 — Tree wrappers** (`f3bd9fc`): `app/pipeline/agents.py` — 7 `BaseAgent` wrappers (PipelineInit, 5×SourceCollector, NormalizeDedup, Processing, Guardrail, DigestEditor, Render) each wrapping the existing proven function + sharing `ctx.session.state`; `build_pipeline()` → `SequentialAgent("NewsCatchUpPipeline")` with a `ParallelAgent("CollectSources")` (distinct `raws_*` keys, parallel-safe); extracted `select_rendered`; `pytest asyncio_mode=auto`. 27 wrapper tests. Review fix: `PipelineInitAgent` run_id fallback bug.
- **O2 — run_digest runs the tree** (`253bbb8`): `run_digest` builds the tree and executes it via `InMemoryRunner.run_async` (bridged by `asyncio.run`), seeding `run_id` into session state and reading the finalized `DigestRun` back from storage; unexpected errors (e.g. render) → FAILED+finalize+re-raise in the delegator. **Retired the dead weather `root_agent`** → `app/agent.py` now `App(root_agent=build_pipeline(...), name="app")`, so `adk run`/`adk web` drive the real pipeline. All **166 contract tests preserved** + tree integration tests.
- **O3 — ADK guide** (`docs/ADK-GUIDE.md`): detailed — ADK pieces used, the agent-tree diagram, each agent's role/IO/file, the LLM agents (model/prompt/output_schema), exactly how we connect (run_digest drives the tree; `run_agent_text` bridge; session-state flow; `App` for adk web/run), the injectable-boundary pattern, AI-Studio↔Vertex swap, how to run.
- **Result:** `uv run pytest tests -q` → **195 passed** (offline); ruff clean. Every commit authored solely by AhmedHeshamSakr.
- **Deferred (needs Gemini quota):** live `adk run`/`adk web` driving the tree's Gemini nodes; a live end-to-end tree run.

### Phase: Deep code review + full remediation ✅
After Plan 8 merged (PR #14), ran a **deep multi-agent code review** (4 parallel reviewers: backend architecture, backend services/security, frontend engineering, frontend UI/UX). Then fixed **every** Critical/High/Medium/A11y finding, subagent-driven on `fix/review-remediation` (off clean `main`). Plan: `docs/superpowers/plans/2026-05-24-review-remediation.md`. Each batch: TDD, kept the green baseline, one commit, authored AhmedHeshamSakr.
- **Headline (verified) bug — `dcc2683`:** Plan 8 introduced a **nested `asyncio.run`** — `run_digest` wraps the tree in `asyncio.run(_run_tree)`, and `run_agent_text` called `asyncio.run` *again* from inside it → every live enrich/critic/narrate raised `RuntimeError`, was swallowed (agents.py), and produced **unenriched PARTIAL digests on every real run**. Tests passed only because they inject fake callables. Fixed with a **loop-aware sync bridge** (`_run_coro_sync`: `asyncio.run` when no loop, else a 1-worker thread with its own loop). Added an integration test driving `run_agent_text` from inside a running loop (stubbed model). Removed unused `nest-asyncio`.
- **Architecture — `5b04759`:** broke the `services↔pipeline` import cycle by extracting the LLM runtime to a neutral `app/llm/` package (`runtime.py` + `schema.py`); removed the deferred in-function imports it forced. Made `CollectSources` genuinely concurrent — `SourceCollectorAgent` runs its blocking collector via `await asyncio.to_thread(...)` and writes a **per-source `errors_*` state key** (no more shared-`DigestRun.source_errors` race); `NormalizeDedup` merges them.
- **Security — SSRF (`3e710b4`):** one SSRF-safe `safe_get` chokepoint in `net.py` (validates **every redirect hop**, `follow_redirects=False`); routed **all** collectors through it (rss/youtube×2/newsapi/scrape/feed_discovery/youtube_resolve) — closed the unguarded RSS/YouTube/GNews holes and the redirect/rebinding bypass.
- **Security — API (`fix(security): optional API-key auth…`):** optional bearer/`X-API-Key` auth on mutating + `/runs` + `/resolve` (open when `api_key` unset, so local dev/console unaffected); wired the previously-dead `TokenBucket` to rate-limit `/runs` & `/resolve` (429); **href scheme whitelist** in the HTML renderer (`javascript:`/`data:` → `#`); pydantic field-validators reject non-`http(s)` url at the API boundary (422); stopped reflecting `str(exc)` to clients (generic message + server-side log).
- **Medium backend — `fba6e34`:** documented `app/fast_api_app.py` as the ADK-deployment entrypoint vs `app/api/app.py` (canonical product REST API); **comment-preserving YAML round-trip** via `ruamel.yaml` (PUT /sources no longer strips `sources.yaml` comments); paginated/capped `list_runs`/`list_news` (`limit` `Query(ge=1,le=200)` + `offset`, threaded to SQLite); removed dead `state_delta={}` plumbing and documented the in-process-session decision (Plan 9 will need `state_delta` for Firestore/Vertex).
- **Frontend a11y — `f8434fb`:** dedicated `--link` token at AA contrast (light `#0E7490` / dark `#67E8F9`) + underlines on text links; explicit `focus-visible` rings on nav/news-title/detail links; global `prefers-reduced-motion` block; darker amber error text.
- **Frontend resilience — `cc87d20`:** `app/error.tsx` + `app/not-found.tsx` route boundaries (handles Next 16.2.6 `unstable_retry`); shared `<AsyncBoundary>` (4 tests) DRYing the loading/error/empty ladder across 3 pages; documented the intentional client-rendered-SWR decision.
- **Frontend boundary/a11y — `d74f0a8`:** **zod-validated** API responses (6 read paths; malformed → normalized `ApiError`, no raw-body leak into toasts); stable list keys (tags, entities); **non-color** status signals (sentiment trend icons; dead sidebar buttons made presentational; output-links de-emphasized with visible "on API host filesystem" note); larger tap targets (28→32px + spacing); real frontend README.
- **Result:** backend `uv run pytest tests -q` → **214 passed** (195 → +19), ruff clean, `import app.agent`/`create_app(Settings())` ok; frontend `npm test` → **48 passed** (43 → +5), eslint + tsc clean.

### Next
- **PR** `fix/review-remediation` → `main` (commits AhmedHeshamSakr, no AI trailers; **delete branch on merge** per the stacked-PR lesson).
- Then **Plan 9 — GCP prod** (Vertex via `GOOGLE_GENAI_USE_VERTEXAI`, Firestore, Cloud Run/Agent Engine deploy of the `App`, Cloud Scheduler, observability/auth) — note the documented `state_delta` requirement for persistent sessions, and set `api_key` in prod.
- **Deferred:** X (paid API / RSS bridge) + LinkedIn (compliant provider); console screens needing new endpoints; live spikes (Plan 7 grounding; YouTube summary + Whisper; eval/critic live) — now safe to run live since the nested-`asyncio.run` bug is fixed.
- **Follow-up (Low, not blocking):** full DNS-pinning for `safe_get` (TOCTOU window noted in code); migrate remaining pages to `AsyncBoundary`; `RawItem`/DTO `frozen=True`.

### Phase: AI-engineering deep review + hardening ✅
Ran a 3-agent **AI-engineering review** (orchestration, prompt engineering, AI-pipeline robustness) on top of `fix/review-remediation`, then fixed every finding subagent-driven (TDD, green throughout) — commits joined PR #15. Plan: `docs/superpowers/plans/2026-05-24-ai-pipeline-hardening.md`. Headline (verified): the faithfulness **guardrail could be bypassed 3 ways** — the AI-system analog of the async bug.
- **G1 — Guardrail integrity** (`6741e96`): **fail-closed critic** (`Settings.critic_fail_mode="closed"` → on critic LLM error, flag+redact all selected HIGH/watchlisted items, run degraded); **API never serves flagged items** (projected `status` column + NULL-safe `status != 'flagged'` filter in `get_items_for_run`/`list_news`, `include_flagged=False` for audit); **redact unfaithful text** (`redact_unfaithful` blanks `summary_en`/`summary_ar` on flag/downrank so hallucinations never persist/serve). +10 tests.
- **G2 — Robust LLM layer** (`c2e8567`): `app/llm/parse.py parse_model_json` (strip ``` fences, extract first balanced JSON, typed `LLMOutputError` on empty/garbage) at all parse sites; `run_agent_text` gains per-call `asyncio.wait_for` timeout + bounded retry/exponential-backoff (`llm_timeout`/`llm_max_retries`/`llm_backoff_base`); **per-batch enrichment isolation** (one bad batch no longer voids the stage); **`temperature=0`** via `GenerateContentConfig` on enricher/critic/judge/editor (kwarg `generate_content_config` verified in ADK 1.34.1). +22 tests.
- **G3 — Eval rigor** (`2e91acd`): **judge calibration vs gold `expectations`** (per-dimension confusion matrix; FP = lenient judge surfaced) so the eval validates the JUDGE, not just the enricher; **faithfulness gated on perfect pass_rate** (a single hallucination fails the gate, not averaged away); `compare()` wired to a committed `tests/eval/baseline.json` (`--check-regression`/`--update-baseline`); **reference set 10→35** balanced cases (categories, 7 faithfulness/3 injection negatives, 5 AR negatives, edge cases); configurable distinct `judge_model`. +18 tests.
- **G4a — Reflection loop** (`dd0f1bb`): bounded **detect→re-enrich-with-feedback→re-critique** (`critic_max_reflections=1`); new injectable `ReprocessFn`/`adk_reprocess` (feeds the critic's `issues` back into a re-summarize pass via `app/prompts/reprocess.md`); survivors flagged+redacted; DRY `_apply_enrichment`. Kept the tree shape (no ADK LoopAgent restructure) and offline by threading a fake `reprocessor=` into the unfaithful-path tests. +5 tests.
- **G4b — Orchestration fixes** (`ea811fd`): unified `search.adk_ground` onto `_run_coro_sync` (no more bare `asyncio.run` outside `runtime.py`/the `runner.py` entrypoint); single `COLLECTED_SOURCE_TYPES` + `state_key_for` map driving both collectors and the NormalizeDedup merge (keys unchanged) so a new source can't be silently dropped; optional `run_timeout` wall-clock cap (→ FAILED, no hang); `DatabaseSessionService` Plan-9 portability test (skips here — `greenlet` absent — documents the `state_delta` requirement). +5 tests (1 skip).
- **G5 — Prompt engineering** (`1e90f1f`): **shared `truncate_excerpt`/`EXCERPT_CHARS=600`** so producer, critic, judge AND reprocess score the IDENTICAL source (stated in the rubric); **anchored 4-band importance scale** (routine/notable/major/globally-critical, mirrored in code); **governed fields** — `EntityType` StrEnum via a synonym-mapping validator (backward-compatible), sentiment-appropriateness check added to the shared rubric; **Arabic first-class** (independent MSA summary of the source, register/number/proper-noun guidance; YouTube summarizes in the transcript's language; `narrative_ar` deferred); judge/critic prompts now **echo the exact output contract + per-dimension pass bars**. +19 tests.
- **Result:** `uv run pytest tests -q` → **293 passed, 1 skipped** (214 → +79), ruff clean, imports ok, `asyncio.run` contained. Frontend untouched (48). Every commit authored AhmedHeshamSakr, no AI trailers.
- **Deferred:** add `greenlet`+`aiosqlite` to dev deps to actually run the persistent-session test (then implement `state_delta` for Plan 9); a stronger distinct judge model in prod (`judge_model`); set `critic_action="replace"`/tune `critic_max_reflections` once live.

### Phase: News display redesign (Prioritized Briefing) ✅
Researched news-feed/card UX first (hierarchy, scannability, progressive disclosure, graceful media), then redesigned how articles display: triage-first **Prioritized Briefing** with an optional per-article image and EN/AR by user preference. Branch `feat/news-display` off `main`. Plan: `docs/superpowers/plans/2026-05-25-news-display.md` (records the 10 UI/UX principles applied). Subagent-driven, TDD, green throughout; each FE batch read the local Next 16.2.6 docs per `frontend/AGENTS.md`.
- **N1 — Backend image extraction** (`1735fd7`): `image_url: str | None` on `RawItem`/`NewsItem` (+`from_raw`), extracted per source — RSS `media_thumbnail`/`media_content`/image `enclosures`, YouTube video thumbnail, GNews `image`, scrape `og:image`/`twitter:image` — each validated http(s) via new `net.is_http_url` (stored, never server-fetched; browser loads it). Round-trips through normalize/storage/API (no DB column). +15 tests.
- **test isolation** (`d01ad6d`): `test_settings_has_intelligence_defaults` now builds `Settings(_env_file=None)` so a developer's local `app/.env` `LLM_MODEL` override doesn't break the default-model assertion (surfaced by the free-tier `gemini-2.5-flash-lite` override).
- **N2 — Language preference** (`7baf718`): `lib/use-language.ts` `useLanguage()` via **`useSyncExternalStore`** (`en|ar`, default `en`, localStorage `catchup.lang`, SSR-safe snapshot — no `set-state-in-effect`); accessible EN/العربية toggle in the sidebar footer beside the theme toggle; `image_url` added to the `NewsItem` TS type + zod `newsItemSchema`. +8 tests.
- **N3 — Briefing NewsCard + image + grouping** (`5ef27c0`): redesigned `NewsCard` — importance badge + colored category chip + sentiment icon, bold headline link, **takeaway promoted to primary text, `line-clamp-3`**, in the preferred language (`ar`→`summary_ar` RTL; fallback chain to other lang→excerpt); compact `source · time` + subtle score; **expand-on-demand** (`<button aria-expanded>`) reveals full summary, the other-language summary, all entities, score. Graceful **plain-`<img>` thumbnail** (only valid http(s); fixed box, lazy/async, `onError`→hide; documented why not `next/image` — `remotePatterns` would 400 on arbitrary news hosts + proxy them through our server). **Importance grouping** (shared `lib/grouping.ts`): Top stories/Notable/More (LOW collapsed), score-sorted — applied to BOTH the News page and Digest detail; `lib/categories.ts` AA-contrast category colors; skeleton updated. +15 tests.
- **Result:** backend `uv run pytest tests -q` → **308 passed, 1 skipped** (with the local flash-lite override active); ruff clean; frontend `npm test` → **71 passed** (48 → +23), lint + tsc + `npm run build` clean. Every commit authored AhmedHeshamSakr, no AI trailers.
- **Follow-up:** server-side `og:image` fetch for RSS items that only carry it on the article page (today only the scrape collector reads og:image); optional image for the search-grounding source.

### Phase: Critical & medium remediation 🚧
Deep review (workflow + Codex cross-check) of the whole app surfaced 3 critical + ~10 medium defects; plan at `docs/superpowers/plans/2026-06-17-critical-medium-remediation.md`. Executing on `fix/critical-medium-remediation` with a per-task Codex review gate.
- **R0 — Security/prereqs:** added `app/.env.example`; confirmed `.env`/`app/.env` gitignored & never committed (live keys to be rotated by the operator).
- **R-Whisper — feature removed (user decision):** dropped the optional Whisper transcription fallback — deleted the yt-dlp/faster-whisper branch in `app/services/youtube.py` `get_transcript` (now youtube-transcript-api only; no transcript → `None`), removed `youtube_whisper_enabled`/`whisper_model` from `Settings`, removed the `[whisper]` optional-dependency group from `pyproject.toml`, and updated the README. The historical Y1/G4b entries above are left intact as the build record. youtube + config tests green; ruff clean.
- **R2 — Eval regression gate (Codex-gated):** `compare()` now mirrors the faithfulness acceptance gate — a safety-critical **pass_rate drop** is a regression (one new hallucination: pass_rate 1.0→0.971 with sub-0.05 mean drop previously passed `--check-regression`); mean stays a secondary signal only when pass_rate is unchanged; an improvement is never flagged. +3 tests.
- **R3 — Configurable CORS (Codex-gated):** added `Settings.allow_origins` (ALLOW_ORIGINS env, comma-split via pydantic-settings `NoDecode` + validator; default `http://localhost:3000`). +2 tests.
- **R1 — Deploy serves the product API (CRITICAL, Codex-gated):** the Dockerfile entrypoint served ONLY the ADK agent surface, so a deployed frontend 404'd every `/api/*` call. Extracted `register_product_routes(app, settings)` (routes only, no CORS) shared by `create_app()` (standalone `catchup serve`) and `app/fast_api_app.py` (the deployed container now mounts `/api/*` on the SAME app). Unified one CORS origin allowlist (`Settings.allow_origins`) across ADK's CORS + origin-check and the product API (no duplicate CORSMiddleware). `Dockerfile` now `COPY ./config`. +2 deploy-surface tests; all existing API tests green.
- **R4 — POST /api/runs hardening (Codex-gated):** endpoint now returns `{status, run_id}` (12-hex id, injected into `run_digest(run_id=)` and threaded through the pipeline) so the client can poll the run it launched, and is **single-flight** — a concurrent trigger returns **409** instead of fanning out N pipelines onto one SQLite file. Runs on a daemon thread started synchronously in the handler (not Starlette BackgroundTasks) so the lock-releasing `finally` always executes even on client disconnect (no lock leak). +2 tests (run_id + real concurrent single-flight).
