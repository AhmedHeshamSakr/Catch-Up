# ADK Catch-Up Agent — Design Specification

**Status:** Approved (brainstorming) · **Date:** 2026-05-23 · **Owner:** Ahmed Hesham
**Repo:** github.com/AhmedHeshamSakr/Catch-Up

---

## 1. Overview & Vision

A production-grade, **multi-agent global news monitoring & catch-up platform** built on the Google
Agent Development Kit (ADK). It continuously collects news from multiple source types, uses Gemini
to categorize / score / summarize / enrich it, and presents fast, structured, beautiful catch-up
digests (Excel, HTML dashboard, Markdown) through a web console.

Designed to run **100% free locally (v1)** while being architected so that going to **full Google
Cloud production at low cost** is a configuration/deployment change — not a rewrite.

## 2. Goals & Non-Goals

### Goals (v1)
- Collect news from **RSS, web scraping, third-party news APIs, and Google Search grounding**.
- Cover 4 default categories: **AI & Tech, Business/Finance, World/Geopolitics, Gulf/MENA** (configurable taxonomy).
- **Scheduled monitoring** that accumulates a news store, plus **on-demand** "catch me up" runs.
- AI processing: **category, importance score, EN/AR summaries, entity extraction, sentiment**.
- **Entity/company watchlists** that boost importance.
- Output: **Excel (master + per-category sheets), HTML dashboard, Markdown**.
- A **beautiful Next.js web console** to configure sources/watchlists/categories, tune agents, run digests, and read results.
- Run free locally with config-based swap-points to GCP production.

### Non-Goals (v1, deferred)
- Email / push delivery (later phase).
- Full multi-tenant auth/RBAC enabled (architecture supports it; v1 ships single-user).
- Mobile app.
- Real-time/event-driven alerting (v1 is scheduled batch).

## 3. Functional Requirements

| # | Requirement |
|---|---|
| FR1 | Define sources declaratively (type, URL/query, category hint, enabled) via UI + config. |
| FR2 | Collect from all 4 source types on a schedule and on demand. |
| FR3 | Normalize all items into a common schema and dedup across runs. |
| FR4 | Classify category, score importance (with watchlist boosts), summarize EN/AR, extract entities, score sentiment. |
| FR5 | Generate a "what matters most" digest narrative grouped by category. |
| FR6 | Render Excel, HTML dashboard, and Markdown outputs; persist + expose them. |
| FR7 | Web console: dashboard, digests browser, sources/watchlist/categories config, pipeline view, runs & schedule, settings. |
| FR8 | Per-source failure isolation; partial-success runs recorded with diagnostics. |
| FR9 | Configurable schedule; manual "Run digest now". |
| FR10 | Switch LLM provider, storage, and scheduler via configuration only. |

## 4. Architecture (Approach A — Full ADK Pipeline)

The intelligence core is one ADK `SequentialAgent` tree, executed by an ADK `Runner` inside a
`run_digest(run_id)` job. Collectors and renderers are **thin custom `BaseAgent` wrappers** over
plain, independently-testable Python service modules. LLM is used only where it adds value.

```
NewsCatchUpPipeline (SequentialAgent)
├── Collection (ParallelAgent)        # fan-out, concurrent
│   ├── RssCollector       (BaseAgent → rss_service)
│   ├── ScrapeCollector    (BaseAgent → scrape_service)
│   ├── ApiCollector       (BaseAgent → newsapi_service)
│   └── SearchGrounding    (LlmAgent + google_search tool)
├── NormalizeDedup         (BaseAgent → pure Python)
├── Processing             (LlmAgent, batched, structured output)
├── DigestEditor           (LlmAgent → narrative)
└── Render                 (BaseAgent → excel/html/markdown services)
```

**System context:** `Next.js console ⇄ FastAPI API ⇄ run_digest()/ADK Runner ⇄ services ⇄ Storage`.
The scheduler triggers `run_digest()`; the API also triggers it on demand and serves stored data.

## 5. Technology Stack

| Layer | v1 (free) | Production |
|---|---|---|
| Agent framework | Google ADK (Python) | same |
| LLM | Gemini `2.5-flash` via AI Studio (free tier) | Vertex AI Gemini Flash |
| Search grounding | Google Search grounding (free tier) | same (Vertex) |
| Backend API | FastAPI + Uvicorn | FastAPI on Cloud Run |
| Storage | SQLite | Firestore (→ BigQuery for analytics) |
| Scheduler | APScheduler / local cron | Cloud Scheduler → HTTP trigger |
| Frontend | Next.js + shadcn/ui + Tailwind | same (Vercel or Cloud Run) |
| Excel/HTML/MD | openpyxl, Jinja2, markdown | same |
| Resilience | custom LLM retry/backoff (`app/llm`) + `TokenBucket` rate limiter | same |

## 6. Design Principles & Patterns

- **Ports & adapters where it pays (as built):** the domain (`app/core/domain.py`) is framework-free, and **storage** is a clean port with SQLite/Firestore adapters (§12). The rest is pragmatic flat modules — ADK, FastAPI, the scheduler, and the LLM provider are integrated directly rather than behind ports (a port with a single implementation is indirection without payoff). `run_digest()` is the use-case (in `app/runner.py`), not a separate `usecases/` layer.
- **SOLID:** dependency inversion at every swap-point (interfaces in core, implementations injected).
- **Strategy pattern** for collectors (one per source type) and renderers (one per output format).
- **Repository pattern** for storage (`StorageBackend`).
- **Factory / DI container** to wire implementations from config (`Settings` → providers).
- **Single-responsibility modules**, small files, well-defined interfaces; services testable without ADK.
- **Idempotency** for runs (dedup + run_id keying).
- **Configuration over code**: sources, categories, watchlist, schedule, provider all declarative.

## 7. Domain Model (Pydantic)

```python
class SourceType(str, Enum): RSS; SCRAPE; API; SEARCH
class Category(str, Enum): AI_TECH; BUSINESS_FINANCE; WORLD_GEOPOLITICS; GULF_MENA
class Importance(int, Enum): LOW=1; MEDIUM=2; HIGH=3
class Sentiment(str, Enum): POSITIVE; NEUTRAL; NEGATIVE

class Entity(BaseModel): name: str; type: Literal["company","person","org","place"]
class NewsItem(BaseModel):
    id: str                  # sha256(url)
    org_id: str; user_id: str            # multi-tenant keys (single value in v1)
    source_id: str; source_type: SourceType; source_name: str
    url: HttpUrl; title: str; excerpt: str | None
    published_at: datetime | None; collected_at: datetime
    category: Category | None
    summary_en: str | None; summary_ar: str | None
    importance: Importance | None; importance_score: float | None  # 0..1 raw
    entities: list[Entity] = []
    sentiment: Sentiment | None
    language: str | None
    status: Literal["raw","processed","filtered"]
    digest_run_id: str | None

class DigestRun(BaseModel):
    run_id: str; org_id: str
    started_at; finished_at; status: Literal["running","success","partial","failed"]
    collected: int; new: int; processed: int; high_importance: int
    outputs: dict[str, str]              # {"xlsx": path, "html": path, "md": path}
    source_errors: list[dict]            # [{source_id, error, ts}]
    narrative: str | None
```

## 8. Source Acquisition Layer (`services/`)

Each collector is a strategy implementing a common `Collector` protocol
(`collect(source: SourceConfig) -> list[RawItem]`):
- **rss_service** — feedparser; ETag/Last-Modified caching.
- **scrape_service** — httpx + selectolax/BeautifulSoup; per-site CSS selector config; robots-aware.
- **newsapi_service** — pluggable provider adapter (GNews/NewsAPI free tiers); query + category mapping.
- **search grounding** — ADK `LlmAgent` with `google_search` for broad, current items.

All network calls go through a shared **HTTP client** with timeouts, retries, and rate limiting.

## 9. Agent Pipeline (detail)

| Stage | ADK type | Responsibility | LLM? |
|---|---|---|---|
| Collection | ParallelAgent | Fan out to collectors; write raw items to storage + `state["raw_items"]`; isolate failures into `source_errors`. | only SearchGrounding |
| NormalizeDedup | custom BaseAgent | Map raw → `NewsItem`; dedup vs storage (url-hash + title similarity); keep new. | no |
| Processing | LlmAgent | Batched structured-output call → category, importance_score, summary_en/ar, entities, sentiment; apply watchlist boosts; filter < threshold. | yes |
| DigestEditor | LlmAgent | Compose grouped "what matters most" narrative from top items. | yes |
| Render | custom BaseAgent | Excel (master + per-category), HTML dashboard, Markdown → `output/`; record paths. | no |

State flows through `session.state` and the storage layer. Processing uses `output_schema` for
validated structured output.

## 10. Prompt Engineering Strategy

- **Versioned, file-based prompts** (`prompts/*.md`) loaded at runtime; never hardcoded inline.
- **Role + task + constraints + few-shot + output contract** structure for each LLM agent.
- **Structured output** via Pydantic `output_schema` (no brittle parsing).
- **Determinism controls:** low temperature for classification/extraction; slightly higher only for the digest narrative.
- **Batching** items per call (token-budget aware) for cost + consistency.
- **Bilingual handling:** detect language; produce EN + AR summaries; preserve original named entities.
- **Grounding/citation:** keep source URL with every item; digest references sources.
- **Injection defenses:** treat fetched content as untrusted data, delimited and clearly labeled; instructions never taken from article text (see §13).
- **Eval harness** (ADK eval): golden set of items with expected category/importance to catch regressions.

## 11. Orchestration & State

- Deterministic pipeline order via `SequentialAgent`; concurrency via `ParallelAgent` for collection.
- Run lifecycle owned by `run_digest(run_id)`: create `DigestRun(running)` → run pipeline → finalize status.
- Idempotent: dedup ensures re-runs don't duplicate; `run_id` keys outputs.
- Cancellation/timeout budget per stage; partial results persisted progressively.

## 12. Swap-Points

The one place that earns a port/adapter split — two real implementations — is
**storage**:

```
app/core/ports/storage.py                # StorageBackend (ABC): existing_ids, save_items,
                                         #   get_items_for_run, create_run, finalize_run,
                                         #   get_run, list_runs, list_news
app/adapters/storage/sqlite_backend.py | firestore_backend.py
```

`build_storage(settings)` (in `app/runner.py`) wires the concrete backend from
`STORAGE_BACKEND`. The other two "swaps" need no port — they're an env toggle or
an HTTP call, so adding a port would be indirection without payoff:

- **LLM provider** — AI Studio ↔ Vertex via the env toggle `GOOGLE_GENAI_USE_VERTEXAI`
  (`app/llm/runtime.py:configure_genai`). No `llm.py` port.
- **Scheduler** — local APScheduler (`app/services/scheduler.py`, opt-in via
  `SCHEDULE_ENABLED`) ↔ Cloud Scheduler, which simply calls **`POST /api/runs`**.
  No scheduling adapter.

**No business logic differs between v1 and prod.** *(The earlier draft of this
section listed `scheduler.py`/`llm.py` ports and a `scheduling/` adapter; those
were never built — see §21.)*

## 13. Fault Tolerance & Resilience

- **Per-source isolation:** a failing source is logged to `source_errors`; the run continues (partial success).
- **Retries with exponential backoff + jitter** on **LLM** calls (a custom retry loop in
  `app/llm`, not tenacity; `llm_max_retries` / `llm_backoff_base`). *(Collector/network
  fetches currently rely on per-call timeouts + per-source isolation, not retries.)*
- **Circuit breaker** per source — **planned, not yet implemented**; per-source isolation
  (above) already stops one failing source from failing the whole run.
- **Timeouts** on every external call; overall stage time budget.
- **Structured-output validation** with one retry; on failure item stays `raw` (never crashes the run).
- **Graceful degradation:** if LLM quota is exhausted, collection + dedup + storage still complete; processing resumes next run.
- **Idempotent, resumable runs**; progressive persistence so a crash loses at most the in-flight batch.

## 14. Rate Limiting & Cost Controls

- **Token-bucket rate limiter** (`app/services/ratelimit.py`) — currently guards the
  expensive API endpoints (`POST /runs`, `/sources/resolve`); per-source / per-host buckets
  are future work.
- LLM runs **only on new (deduped) items**, **batched**, on **Gemini Flash**.
- **Importance threshold** filters items before the (more expensive) narrative step.
- **Caching:** RSS conditional GETs; grounding results cached within a run; HTTP response cache.
- **Quota-aware scheduling** respects free-tier RPM/RPD; backoff on 429.

## 15. Security & Multi-Tenancy

- **Multi-tenant data model** from day 1 (`org_id`/`user_id` on all records); v1 uses a single default tenant; enabling auth later is a toggle, not a migration.
- **AuthN/Z (prod):** Firebase Auth / Identity Platform; RBAC roles (admin, editor, viewer); per-org data isolation enforced in the repository layer.
- **Secrets:** never in code/repo; `.env` locally, Secret Manager in prod; `.gitignore` covers keys/SA JSON.
- **Input sanitization & SSRF protection** for user-provided source URLs (allowlist schemes, block internal IP ranges, size/time limits on fetches).
- **Prompt-injection defense:** fetched article content is data, not instructions — delimited, labeled untrusted; system prompts forbid following embedded instructions; outputs schema-constrained.
- **Output safety:** sanitize/escape rendered HTML to prevent stored XSS in the dashboard.
- **Audit logging** of config changes and runs (prod).
- **Least-privilege** service accounts in prod.

## 16. Observability

- **Structured logging** (JSON) with run_id/source_id correlation.
- **ADK tracing** over the whole pipeline (Cloud Trace in prod).
- **Run metrics** surfaced in the console (collected/new/processed/high, durations, error rate, per-source health).
- Optional integrations later (Phoenix/MLflow) per ADK observability skill.

## 17. Web Console (UI/UX)

### Design language — "Signal"
- Typography: **Inter** (UI) + **IBM Plex Mono** (numerics, tabular figures).
- Accents: **emerald** (`#059669` light / `#34D399` dark) + **cyan** (`#0891B2`); semantic red/amber/green for importance/health.
- **Light + Dark**, default **Auto = system** (`prefers-color-scheme`).
- **Lucide outline icons** (no emoji); 8-pt spacing grid; AA contrast; shared component system (shadcn/ui).
- Enterprise left sidebar: brand lockup + **workspace switcher** (multi-tenant entry) + grouped nav + profile footer.

### Information architecture (screens)
1. **Dashboard** — stats, "what matters most", by-category breakdown, recent-run health.
2. **Digests** — browse past digests; open HTML view; download Excel/MD.
3. **Sources** — CRUD sources (RSS/scrape/API/search), category hints, enable/disable, health/last-result.
4. **Watchlist** — companies/people/keywords with importance boosts.
5. **Categories** — manage taxonomy.
6. **Pipeline** — view the agent tree; per-agent config (model, temperature, prompt version); run-now; recent traces.
7. **Runs & Schedule** — schedule config; run history + per-source diagnostics.
8. **Settings** — provider toggle (AI Studio/Vertex), API keys, output prefs; (Organization/Members — later).

### API surface (FastAPI, illustrative)
```
GET  /api/dashboard
GET  /api/digests            POST /api/digests/run
GET  /api/runs  /api/runs/{id}
CRUD /api/sources  /api/watchlist  /api/categories
GET/PUT /api/pipeline/config   GET /api/settings  PUT /api/settings
GET  /api/news  (search/filter)
```

## 18. Configuration

- `config/app.yaml` + `.env` — provider toggle, model, storage/scheduler choice, cron, importance threshold, output dir, API keys.
- `config/sources.yaml` — source definitions (also editable via UI; UI writes through to the same store).
- `config/watchlist.yaml` — boosted entities/keywords.
- `.env.example` documents all variables.

## 19. Deployment Phasing

- **v1 (free, local):** AI Studio key + SQLite + APScheduler; `adk web`/CLI + `next dev`. $0.
- **Production:** flip `GOOGLE_GENAI_USE_VERTEXAI=TRUE`; Dockerize; deploy API to **Cloud Run**; **Cloud Scheduler** → `/api/digests/run`; **Firestore** backend; Secret Manager; frontend on Vercel/Cloud Run. Lowest-cost serverless, scale-to-zero.

## 20. Testing Strategy (TDD)

- Unit tests per service with fixtures (sample feeds/HTML/API JSON).
- **Storage contract tests** run against SQLite + Firestore emulator (same suite).
- Pipeline agents tested with mocked LLM responses; schema-validation tests.
- **ADK eval set** for processing quality (category/importance golden data).
- API integration tests; frontend component tests; E2E happy path (run → digest → outputs).
- CI gates: lint (ruff), type-check (mypy), tests, coverage threshold.

## 21. Project Structure

As built — a flat `app/` package (not the deeper `backend/catchup/` tree this
section originally sketched):

```
.
├── app/
│   ├── agent.py                 # ADK root agent (lazy-built)
│   ├── fast_api_app.py          # ADK Agent Engine surface (web UI + /api)
│   ├── web_app.py               # Cloud Run product app = create_app()
│   ├── cli.py                   # `catchup` CLI: run / serve
│   ├── runner.py                # run_digest() job + build_storage()
│   ├── core/                    # domain.py, config.py, env_store.py, ports/storage.py
│   ├── pipeline/                # agents.py (ADK tree), wiring.py, processing, critic,
│   │                            #   judge, digest_editor, eval_score, eval_schema
│   ├── llm/                     # Gemini runtime + structured-output schema/parse
│   ├── services/               # rss, scrape, newsapi, search, youtube, normalize,
│   │   │                        #   watchlist, scheduler, ratelimit, net, config_store
│   │   └── render/             # excel, html, markdown
│   ├── adapters/storage/       # sqlite_backend.py, firestore_backend.py
│   ├── api/                    # FastAPI product API + static console mount
│   ├── app_utils/             # telemetry, typing
│   └── prompts/               # versioned prompt files (*.md)
├── frontend/                   # Next.js + shadcn/ui + Tailwind console
├── config/                     # sources.yaml, watchlist.yaml
├── tests/                      # unit, integration, eval
├── docs/                       # ADK-GUIDE, eval, specs, plans, BUILD-LOG
├── Dockerfile  firestore.indexes.json  pyproject.toml  agents-cli-manifest.yaml
└── README.md
```

> There is no `core/usecases/` or `core/domain/` package, and no
> `adapters/scheduling/` — `run_digest()` (the use-case) lives in `runner.py`,
> the domain is a single `core/domain.py` module, and only storage needed a
> port/adapter split (§12). The flat layout proved sufficient.

## 22. Milestones

1. **Foundation** — domain schema, config/DI, SQLite storage + contract tests.
2. **Collection** — services + collector agents (RSS → API → scrape → search grounding) with rate limiting/resilience.
3. **Normalize & dedup**.
4. **Intelligence** — Processing + DigestEditor LLM agents + prompts + eval set.
5. **Rendering** — Markdown → Excel → HTML.
6. **Orchestration & jobs** — `run_digest`, local scheduler, CLI, end-to-end run.
7. **API** — FastAPI surface over use-cases.
8. **Web console** — Signal design system + screens.
9. **Hardening** — security, observability, full resilience.
10. **(Later) Production** — Firestore, Cloud Run, Cloud Scheduler, Vertex; email delivery.

## 23. Resolved Decisions & Future Work

**Resolved (2026-05-23):**
- **Seed sources:** v1 ships a **curated default set** of reputable RSS/API/search sources across
  the 4 categories (including Gulf/MENA + Arabic) so it works out of the box; Ahmed replaces them
  with his curated list later (sources are editable via UI/config).
- **Excel schema:** **approved** — `Date, Title, Summary (EN), Summary (AR), Category, Source, URL,
  Importance, Entities, Sentiment`; master sheet + one sheet per category.

**Future work:**
- Email / push delivery (deferred phase).
- Multi-tenant auth rollout timing (architecture ready; enable when needed).
