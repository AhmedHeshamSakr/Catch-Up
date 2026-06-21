# Catch-Up × Google ADK — Architecture & Integration Guide

How this project uses the **Google Agent Development Kit (ADK)**: which ADK pieces we use, our agent tree, and exactly how we connect to ADK. Everything in the digest pipeline runs **through ADK** — `run_digest` builds and executes an ADK agent tree, and `adk run` / `adk web` drive that same tree.

> Versions: `google-adk` 1.34.x, `google-genai`, Python 3.11–3.13. Model alias: `gemini-flash-latest` (do not change).

---

## 1. ADK building blocks we use

| ADK piece | Import | Where we use it |
|---|---|---|
| `Agent` (LlmAgent) with `output_schema` | `from google.adk.agents import Agent` | The LLM agents: `news_processor`, `digest_editor`, `faithfulness_critic`, `enrichment_judge`, `youtube_summary` — each returns **structured Pydantic output**. |
| `google_search` tool | `from google.adk.tools import google_search` | The `search_collector` agent (grounded web search). Note: a `google_search` agent **cannot** also set `output_schema`. |
| `BaseAgent` (custom) | `from google.adk.agents import BaseAgent` | The 7 pipeline-stage wrappers in `app/pipeline/agents.py` (thin shells over our Python functions). |
| `SequentialAgent` | `from google.adk.agents import SequentialAgent` | The root `NewsCatchUpPipeline` — runs stages in order, sharing session state. |
| `ParallelAgent` | `from google.adk.agents import ParallelAgent` | `CollectSources` — runs the 5 source collectors concurrently. |
| `App` | `from google.adk.apps import App` | `app/agent.py` builds `app`/`root_agent` **lazily** (module `__getattr__`, no import-time I/O) for `adk run`/`adk web`. |
| `Runner` / `run_async` | `from google.adk.runners import Runner` | `run_digest` drives the tree via `Runner` + a persistent `DatabaseSessionService`. Single LLM-agent calls (`llm/runtime.run_agent_text`, search) keep `InMemoryRunner`. |
| `Session` / `ctx.session.state` | (via `InvocationContext`) | Carries data between stages; written via `state_delta`, never direct mutation. |
| `Event` / `EventActions` | `from google.adk.events import Event, EventActions` | Each `BaseAgent` yields a terminal `Event` carrying its `EventActions.state_delta`. |
| `google.genai.types` | `from google.genai import types` | `types.Content` / `types.Part` for messages; `GroundingMetadata` for search harvesting. |

---

## 2. The agent tree — `NewsCatchUpPipeline`

Built by `build_pipeline()` in `app/pipeline/agents.py`. Root = a `SequentialAgent`; collection = a nested `ParallelAgent`.

```
NewsCatchUpPipeline               (SequentialAgent)              app/pipeline/agents.py
├─ PipelineInit                   (BaseAgent)   create DigestRun → run delta (watchlist injected, not in state)
├─ CollectSources                 (ParallelAgent)
│   ├─ CollectRss                 (BaseAgent → app/services/rss.py)        → state["raws_rss"]
│   ├─ CollectScrape              (BaseAgent → app/services/scrape.py)     → state["raws_scrape"]
│   ├─ CollectApi                 (BaseAgent → app/services/newsapi.py)    → state["raws_api"]
│   ├─ CollectSearch              (BaseAgent → app/services/search.py *)   → state["raws_search"]
│   └─ CollectYoutube             (BaseAgent → app/services/youtube.py *)  → state["raws_youtube"]
├─ NormalizeDedup                 (BaseAgent → app/services/normalize.py)  → state["items"]
├─ Processing                     (BaseAgent → news_processor LLM agent)   enrich items in place
├─ Guardrail                      (BaseAgent → faithfulness_critic *)      flag/downrank unfaithful
├─ DigestEditor                   (BaseAgent → digest_editor LLM agent)    narrative → run delta
└─ Render                         (BaseAgent → render/*)                    md/xlsx/html + finalize
```
`*` = the collector/stage itself calls an LLM (search grounding, YouTube transcript summary, critique).

**Design choice — wrappers, not native sub-agents.** Each stage is a thin `BaseAgent` that calls our **existing, well-tested Python function** (`rss.collect`, `normalize_and_dedup`, `process_items`, `apply_verdicts`, `adk_narrate`, the render writers). The tree provides ADK orchestration (ordering, parallelism, shared state, observability, deployability); the proven functions do the work. This keeps one implementation and keeps every LLM/network call behind an **injectable boundary** so the whole suite runs offline.

### State flow (`EventActions.state_delta`)
`SequentialAgent` passes the **same session** to each child, and the runner applies each child's `EventActions.state_delta` to the session **before the next child runs**. Every cross-stage value travels via `state_delta` as **JSON-serializable** data, so the tree is correct under a persistent session service (`DatabaseSessionService`) — only `state_delta` survives a session reload, so direct `ctx.session.state` mutation would be lost across processes. Keys: `run_id` (str) → `run` (DigestRun dict) · `raws_rss|scrape|api|search|youtube` (one per parallel collector — **distinct keys**, so `ParallelAgent` deltas merge conflict-free) · `errors_raws_*` · `items` (list of NewsItem dicts). Stages read via the tolerant `_read_run`/`_read_items`/`_read_raws` helpers and write via `_run_delta`/`_items_delta`. `settings`/`storage`/`watchlist` are **constructor fields** on the wrapper agents (config/infra, never in session state). See `docs/superpowers/specs/2026-06-17-durable-session-state-design.md`.

---

## 3. The LLM agents

Structured-output agents use `Agent(model=settings.llm_model, instruction=<prompt>, output_schema=<Pydantic>, output_key=...)`, run via `llm.runtime.run_agent_text`, and are validated with `Model.model_validate_json`. `search_collector` is the tool-only exception (`tools=[google_search]`, no `output_schema`).

| Agent | File | Prompt | `output_schema` | Role |
|---|---|---|---|---|
| `news_processor` | `app/pipeline/processing.py` | `app/prompts/processing.md` | `ProcessingResult` | category, importance 0–1, EN+AR summary, entities, sentiment |
| `digest_editor` | `app/pipeline/digest_editor.py` | `app/prompts/digest_editor.md` | `DigestNarrative` | "what matters most" briefing |
| `faithfulness_critic` | `app/pipeline/critic.py` | `app/prompts/critic.md` (+ shared rubric) | `FaithfulnessVerdicts` | runtime fact-check of HIGH/watchlisted summaries |
| `enrichment_judge` | `app/pipeline/judge.py` | `app/prompts/judge.md` (+ shared rubric) | `EnrichmentVerdicts` | **offline eval** scoring (faithfulness/category/importance/AR) |
| `youtube_summary` | `app/services/youtube.py` | `app/prompts/youtube_summary.md` | `DigestNarrative` | summarize a video transcript |
| `search_collector` | `app/services/search.py` | inline | **none** (has `tools=[google_search]`) | grounded web search; we harvest `grounding_metadata` |

The critic and judge **share one rubric** — `app/prompts/faithfulness_rubric.md` is composed into both prompts via a `{{RUBRIC}}` placeholder (single source of truth).

---

## 4. Exactly how we connect to ADK

### a) Driving the whole pipeline — `run_digest` runs the tree
`app/runner.py`:
```python
def run_digest(settings=None, storage=None, processor=None, narrator=None, critic=None) -> DigestRun:
    settings = settings or Settings(); storage = storage or build_storage(settings)
    run_id = uuid.uuid4().hex[:12]
    tree = build_pipeline(settings, storage, processor=processor, narrator=narrator, critic=critic)  # run_id seeded via session state
    session_service = make_session_service(settings)   # "database" (default) → DatabaseSessionService; "memory" → InMemory
    try:
        asyncio.run(_run_and_close())                  # run the ADK tree, then dispose the session DB engine
    except Exception as exc:                            # unexpected error (e.g. render) → FAILED
        run = storage.get_run(run_id)
        if run: run.status = RunStatus.FAILED; run.finished_at = now(); run.source_errors.append({...}); storage.finalize_run(run)
        raise
    return storage.get_run(run_id)                     # RenderAgent finalized it

async def _run_tree(tree, run_id, session_service):
    runner = Runner(agent=tree, app_name="catchup", session_service=session_service)
    session = await session_service.create_session(app_name="catchup", user_id="system", state={"run_id": run_id})
    msg = types.Content(role="user", parts=[types.Part.from_text(text="run")])
    async for _ in runner.run_async(user_id="system", session_id=session.id, new_message=msg): pass
```
- The runtime uses a **persistent** `DatabaseSessionService` by default (`session_backend`/`session_db_url`; SQLite via `aiosqlite`+`greenlet`); tests force `session_backend=memory`. The per-run async engine is disposed in a `finally` so the long-running API process doesn't accumulate connection pools.
- `run_id` is seeded into the **initial session state**; `PipelineInit` reads it and creates the `DigestRun` (so the delegator can read the finalized run back from storage).
- The async tree is bridged into sync code with `asyncio.run` (safe — CLI/API run in a sync/threadpool context). The CLI (`app/cli.py`) and the FastAPI endpoint (`POST /api/runs`) both call `run_digest`, so **they run through ADK**.

### b) Driving a single LLM agent — `run_agent_text`
`app/llm/runtime.py` is the shared sync bridge over `run_async`, with a per-attempt timeout + exponential-backoff retry:
```python
def run_agent_text(agent, payload, settings) -> str:
    ensure_api_key(settings)                           # exports GOOGLE_API_KEY for the genai client
    for attempt in range(1 + settings.llm_max_retries):
        try:                                            # _run_coro_sync = loop-aware bridge
            return _run_coro_sync(                      # (asyncio.run, or a worker loop if one is running)
                _run_text_async(agent, payload, timeout=settings.llm_timeout))
        except Exception:
            ...                                         # backoff + retry; re-raise the last on exhaustion

async def _run_text_async(agent, payload, *, app_name="catchup", timeout=None):
    async def _consume():
        runner = InMemoryRunner(agent=agent, app_name=app_name)   # one-off: in-memory is fine
        session = await runner.session_service.create_session(app_name=app_name, user_id="system")
        msg = types.Content(role="user", parts=[types.Part.from_text(text=payload)])
        text = ""
        async for event in runner.run_async(user_id="system", session_id=session.id, new_message=msg):
            if event.is_final_response() and event.content and event.content.parts:
                text = event.content.parts[0].text or ""
        return text
    return await (_consume() if timeout is None else asyncio.wait_for(_consume(), timeout))
```
The processing/editor/critic/judge agents call this and parse the returned JSON against their `output_schema`. (These are stateless single-agent calls, so they keep `InMemoryRunner`; only the durable pipeline uses the persistent session service.)

### c) A custom stage agent — the `BaseAgent` pattern
```python
class NormalizeDedupAgent(BaseAgent):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")
    settings: Settings
    storage: StorageBackend
    async def _run_async_impl(self, ctx) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        run = _read_run(state)                            # tolerant: JSON dict OR live object
        all_raws = [r for st in COLLECTED_SOURCE_TYPES
                    for r in _read_raws(state, state_key_for(st))]
        run.collected = len(all_raws)
        items = normalize_and_dedup(all_raws, self.storage, run.run_id)
        run.new = len(items)
        # Durable values travel via state_delta (JSON) — never direct mutation:
        yield _make_event(ctx, self.name, {**_run_delta(run), **_items_delta(items)})
```

### d) Exposure to `adk run` / `adk web`
`app/agent.py` exports `app = App(root_agent=build_pipeline(...), name="app")`. The ADK loader (and `agents-cli-manifest.yaml`'s `agent_directory: "app"`) resolves the `app` attribute first, so `adk run app` / `adk web` drive the **real** `NewsCatchUpPipeline`. (`App.name` stays `"app"`; the tree's root agent is named `NewsCatchUpPipeline`.)

---

## 5. The injectable-boundary pattern (why the tests are offline)
Every place ADK would call Gemini or the network is a `Callable` boundary with a real default:
- `EnrichFn` → `adk_enrich` · `NarrateFn` → `adk_narrate` · `CriticFn` → `adk_critique` · `JudgeFn` → `adk_judge` · `GroundFn` → `adk_ground` · collector `fetch`/`transcript`/`summarize`/`ground` · `run_digest(processor=, narrator=, critic=)`.
Tests inject fakes (synthetic Pydantic results / fixtures), so the **full suite runs with zero network and zero Gemini quota**. The real `adk_*` functions are the live path, validated by a live smoke when a key is present.

---

## 6. Free tier vs. production (provider swap)
- **Free / local (v1):** a Google **AI Studio** key in `app/.env` as `GOOGLE_API_KEY`. `configure_genai()` (aliased `ensure_api_key()`) exports it for the `google-genai` client. SQLite storage; the pipeline runs on a persistent SQLite-backed `DatabaseSessionService` by default (`session_backend`; tests force `memory`).
- **Vertex AI (opt-in):** set `use_vertexai=True` (+ `google_cloud_project`, `google_cloud_location` default `"global"`). `configure_genai()` then sets `GOOGLE_GENAI_USE_VERTEXAI=TRUE`/project/location and skips the API key. Fails fast if the project is empty.
- **Firestore storage (opt-in):** set `storage_backend="firestore"` + install the `[firestore]` extra. `build_storage()` returns a `FirestoreBackend` (behind the same `StorageBackend` port) wrapping a real `firestore.Client`; an actionable error fires if the extra is missing. The adapter is contract-tested offline against an in-memory `FakeFirestoreClient` — it satisfies the same `StorageContract` as the SQLite backend. **Caveat — not validated against live Firestore:** composite indexes, `FieldFilter` migration, and `is_flagged` backfill are pre-deploy steps gated by the skipped `tests/integration/test_firestore_emulator.py`.
- **Scheduling (opt-in):** set `schedule_enabled=True` + `schedule_cron` (5-field cron, e.g. `"0 7 * * *"`) + `schedule_timezone`. `catchup serve` then runs the digest in-process on that cadence via APScheduler, sharing the single-flight guard (`app/run_trigger.try_start_run`) with manual `POST /api/runs` — a scheduled run while one is in flight is skipped, never doubled. In production, instead point **Cloud Scheduler** at the existing endpoint (no in-process code):
  ```bash
  gcloud scheduler jobs create http catchup-digest \
    --schedule="0 7 * * *" --time-zone="UTC" \
    --uri="https://<host>/api/runs" --http-method=POST --headers="X-API-Key=<key>"
  ```
- **Deploy:** three paths (see README "Deployment") — local desktop, the Cloud Run **product** image (`app/web_app.py`: console + `/api`), and ADK **Agent Engine** (`app/fast_api_app.py`, behind Cloud Run IAM/IAP). No pipeline rewrite — storage swaps behind its port; LLM/scheduler swap via env toggle / `POST /api/runs`.

---

## 7. How to run

```bash
# Through ADK's own tooling (drives NewsCatchUpPipeline):
uv run adk run app            # one-shot
uv run adk web                # browser playground

# Through our CLI / API (also run the same ADK tree via run_digest):
uv run python -m app.cli run
uv run python -m app.cli serve         # FastAPI :8000 → POST /api/runs

# Offline eval (LLM-as-judge) + tests (no quota):
uv run python scripts/eval_enrichment.py --live   # live scoring (needs key)
uv run pytest tests -q                            # fully offline
```

Enrichment, narrative, critique, search grounding, and YouTube summaries all need `GOOGLE_API_KEY`; collection/dedup/storage/render degrade gracefully without it.
