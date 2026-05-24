# Catch-Up — News Intelligence Agent

A production-grade, **multi-agent global news monitoring & catch-up platform** built on the
Google Agent Development Kit (ADK). It collects news from RSS, web scraping, news APIs, and
Google Search grounding; uses Gemini to categorize, importance-score, summarize (EN/AR), and
extract entities; and delivers structured catch-up digests as **Excel, an HTML dashboard, and
Markdown** through a **Next.js** web console.

Built **free to run locally**, architected to scale to **Google Cloud production** (Cloud Run +
Cloud Scheduler + Vertex AI + Firestore) by configuration — not a rewrite.

## Status

🚧 Early development. Design is approved — see
[`docs/superpowers/specs/2026-05-23-adk-catchup-agent-design.md`](docs/superpowers/specs/2026-05-23-adk-catchup-agent-design.md).

## Architecture (at a glance)

```
Next.js console  ⇄  FastAPI API  ⇄  run_digest()/ADK Runner  ⇄  services  ⇄  Storage

NewsCatchUpPipeline (ADK SequentialAgent)
  CollectSources (ParallelAgent: RSS · Scrape · API · Search · YouTube)
  → NormalizeDedup → Processing (LLM) → Guardrail (critic) → DigestEditor (LLM) → Render (xlsx/HTML/MD)
```

**Everything runs through ADK:** `run_digest` builds and executes this agent tree via an ADK `Runner`, and `adk run app` / `adk web` drive the same tree. See **[docs/ADK-GUIDE.md](docs/ADK-GUIDE.md)** for the full ADK architecture & integration guide.

## Tech

ADK · Gemini (AI Studio → Vertex) · FastAPI · SQLite → Firestore · APScheduler → Cloud Scheduler ·
Next.js + shadcn/ui + Tailwind.

## Running locally

```bash
uv sync                                   # install deps
uv run pytest tests -q                    # run the test suite (no API key needed)
uv run --extra lint ruff check app tests  # lint

# Run a digest (collects RSS → enriches with Gemini → writes output/digest-<id>.md)
# Requires a Google AI Studio key for the LLM enrichment + narrative:
export GOOGLE_API_KEY=...   # or put it in .env (gitignored)
uv run python -m app.cli run
```

Sources live in `config/sources.yaml` — each has a `type`: **`rss`**, **`api`** (GNews; set `query`, optional `lang`/`country`), **`scrape`** (set a CSS `selector`), **`search`** (Google Search grounding via ADK `google_search`; set a `query`), or **`youtube`** (monitor a channel; set its `channel_id`, the `UC…` id). Search sources need `GOOGLE_API_KEY` and consume model calls, so they ship **disabled by default**; their results link via Google grounding-redirect URLs and carry no publish date. YouTube sources detect new uploads via the channel's free RSS feed (no key) and summarize each video's transcript (`youtube-transcript-api`, with an optional Whisper fallback behind the `whisper` extra; the transcript summary needs `GOOGLE_API_KEY`) — also disabled by default. The GNews collector needs `GNEWS_API_KEY` (`export GNEWS_API_KEY=...` or `.env`). Importance-boost entities/keywords live in `config/watchlist.yaml`. In the **console** you don't need the exact technical value — paste a YouTube **channel URL / @handle** or a newspaper **homepage URL** in the Sources form and click **Resolve** to auto-fill the `channel_id` / discovered RSS feed.
Without keys, collection/dedup/storage still run and the digest degrades gracefully (items unenriched); scrape URLs are SSRF-guarded (public hosts only).

## Quality & faithfulness

Two LLM-as-judge safeguards protect summary quality (both build/test offline; live runs need `GOOGLE_API_KEY`):

- **Offline eval loop** — `uv run python scripts/eval_enrichment.py --live` scores enrichment against a reference dataset (`tests/eval/fixtures/`) on four dimensions: **summary faithfulness** (no hallucination/obeyed-injection), category accuracy, importance calibration, and Arabic translation quality, with pass/fail thresholds. See `docs/eval/README.md` for the eval-fix loop.
- **Runtime faithfulness guardrail** — at digest time a critic fact-checks **HIGH-importance and watchlisted** items against their source; unfaithful summaries are **down-ranked + flagged** (never shown), configurable via `critic_*` settings. Both the judge and the critic share one rubric (`app/prompts/faithfulness_rubric.md`).

Each run emits three output files: `output/digest-<id>.md`, `output/digest-<id>.xlsx` (master + per-category sheets), and `output/digest-<id>.html` (Signal-themed dashboard). To generate sample outputs with no API key:

```bash
uv run python scripts/render_smoke.py
```

## API

Start the REST API server (no API key needed for health/dashboard reads):

```bash
uv run python -m app.cli serve          # http://127.0.0.1:8000
uv run python -m app.cli serve --host 0.0.0.0 --port 8080
```

| Endpoint | Description |
|---|---|
| `GET /api/health` | Liveness check — returns `{"status":"ok"}` |
| `GET /api/dashboard` | Latest run, recent runs, category counts, total items |
| `GET /api/news` | News items (filterable by `category` + `importance`) |
| `GET /api/runs` | Recent digest runs |
| `GET /api/runs/{run_id}` | Run detail + its news items |
| `GET /api/sources` | Configured news sources |
| `PUT /api/sources` | Update sources config (YAML round-trip) |
| `POST /api/sources/resolve` | Resolve a pasted link → `channel_id` (youtube) or RSS feed `url` (rss) |
| `GET /api/watchlist` | Watchlist entities + keywords |
| `PUT /api/watchlist` | Update watchlist |
| `POST /api/runs` | Trigger a new digest run (async) |
| `GET /docs` | FastAPI auto-generated interactive docs (OpenAPI) |

## Web Console

A **Next.js** console (in `frontend/`) in the "Signal" design language — Inter + IBM Plex Mono, emerald/cyan accents, light + dark with **Auto = system default**, Lucide icons, enterprise sidebar. It reads digests and configures the agent over the REST API above.

```bash
# 1. Start the API (separate terminal, from the repo root)
uv run python -m app.cli serve            # http://127.0.0.1:8000

# 2. Start the console
cd frontend
npm install
cp .env.local.example .env.local          # NEXT_PUBLIC_API_BASE=http://localhost:8000
npm run dev                                # http://localhost:3000
```

Screens:

| Screen | What it does |
|---|---|
| **Dashboard** | Stats, "what matters most" narrative, by-category breakdown, latest-run health |
| **Digests** | Browse past runs; open a run to see grouped, summarized items + output files |
| **News** | Filterable feed of collected items (category · importance · limit) |
| **Sources** | Add/edit/delete sources (RSS · scrape · API · search), category hints, live enable toggle |
| **Watchlist** | Manage entities & keywords that boost importance (+0.25) |

"Run now" triggers a digest via `POST /api/runs`; full enrichment (summaries, scores) needs a Google AI Studio key on the API host. The frontend test suite runs fully offline (`cd frontend && npm test`) — `fetch` is mocked, no backend or quota needed.

## License

Private.
