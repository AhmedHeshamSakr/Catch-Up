# Plan 7 — Search Grounding Collector + `run_async` Migration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. ADK specifics: consult `docs/superpowers/research/2026-05-24-plan7-search-grounding.md` (the research note) and the `/google-agents-cli-adk-code` skill.

**Goal:** Add the 4th source type — a **Google Search grounding collector** (ADK `google_search`) — and migrate the existing ADK LLM calls from the deprecated sync `runner.run` to **`run_async`**, while fixing API-key loading so live runs work.

**Architecture:** A dedicated grounding-only ADK agent (`google_search` cannot coexist with `output_schema`) runs a source's query; we harvest cited sources from `event.grounding_metadata.grounding_chunks[*].web` into `RawItem`s. All ADK calls go through one async helper bridged into the sync pipeline via `asyncio.run`. The grounding network/model call is injectable, so the parser and collector are fully offline-tested; only a final live grounding spike defers until the Gemini quota resets.

**Tech stack:** `google-adk` 1.34.x (`from google.adk.tools import google_search`), `google.genai.types.GroundingMetadata/GroundingChunk/GroundingChunkWeb`, pydantic, pytest. Run via `uv`.

**Commit identity (MANDATORY):** every commit authored `AhmedHeshamSakr <a.hesham1221@gmail.com>` — NO Claude / Co-Authored-By trailers. Verify `git log --format='%an <%ae>' -1` after each commit; amend if wrong.

---

## Key facts from research (binding)
- `google_search` is a singleton tool: `from google.adk.tools import google_search`; attach via `Agent(model=..., tools=[google_search], instruction=...)`.
- **Constraint:** an agent with `google_search` **cannot** also set `output_schema` (ADK raises). So the grounding agent is search-only; we read structured data from grounding metadata, not from a JSON response.
- Grounding lives at: `event.grounding_metadata.grounding_chunks[i].web.uri` (a **Vertex redirect URL**, not the publisher URL), `.web.title`, `.web.domain` (often `None` on the Gemini API backend). Also `grounding_metadata.web_search_queries`. The metadata may appear on a non-final event → keep the **last non-None** `grounding_metadata` seen across the stream.
- `run_async` pattern: `session = await runner.session_service.create_session(app_name=.., user_id="system")`; `async for event in runner.run_async(user_id="system", session_id=session.id, new_message=msg): ...`. Exceptions propagate cleanly (no worker-thread escape like sync `runner.run`).
- Bridge into the sync `run_digest` pipeline with `asyncio.run(...)` (safe: `run_digest` runs in a sync context / FastAPI BackgroundTasks threadpool — no running loop).
- `RawItem.published_at` is **not** available from grounding metadata → always `None` for search results.
- **Config bug (found in the Plan 6 smoke test):** `GOOGLE_API_KEY` lives in `app/.env`, but `Settings` reads only `./.env` and `serve` runs from repo root → key never loads ("No API key" at runtime). ADK's google client reads `GOOGLE_API_KEY` from `os.environ`.

---

## File structure

```
app/pipeline/adk_runtime.py     # NEW: ensure_api_key(); async run helper; run_agent_text() sync bridge
app/pipeline/processing.py      # MODIFY: adk_enrich → use adk_runtime (run_async)
app/pipeline/digest_editor.py   # MODIFY: adk_narrate → use adk_runtime (run_async)
app/services/search.py          # NEW: parse_grounding(); build_search_agent(); adk_ground(); collect()
app/runner.py                   # MODIFY: _collect dispatch SEARCH → search.collect; drop stale comment
app/core/config.py              # MODIFY: Settings reads ('.env','app/.env')
config/sources.yaml             # MODIFY: add a disabled SEARCH source
tests/unit/test_search.py       # NEW: parse_grounding + collect (injected ground) offline tests
tests/unit/test_config.py       # NEW/MODIFY: Settings loads key from app/.env
README.md                       # MODIFY: document search sources
docs/BUILD-LOG.md               # MODIFY: Plan 7 entry
```

---

### Task 1: Reliable API-key loading + shared ADK runtime helper

**Files:**
- Modify: `app/core/config.py`
- Create: `app/pipeline/adk_runtime.py`
- Create/modify test: `tests/unit/test_config.py`

- [ ] **Step 1: Failing test for key loading** — `tests/unit/test_config.py`:

```python
from app.core.config import Settings

def test_settings_loads_key_from_app_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / ".env").write_text("GOOGLE_API_KEY=from_app_env\n", encoding="utf-8")
    # No ./.env present; key must still load from app/.env
    s = Settings()
    assert s.google_api_key == "from_app_env"
```
Run: `uv run pytest tests/unit/test_config.py -q` → FAIL.

- [ ] **Step 2: Make Settings read both env files** — in `app/core/config.py`, change:
```python
    model_config = SettingsConfigDict(env_file=(".env", "app/.env"), extra="ignore")
```
(pydantic-settings merges multiple env files; a value present in either is loaded. Verify ordering with the test — if `./.env` should win when both define the key, confirm pydantic-settings precedence and adjust the tuple order so the test plus a second test `./.env overrides app/.env` both pass. Add that second test if you change order.)
Run the test → PASS. Run full suite `uv run pytest tests -q` → still green (62+).

- [ ] **Step 3: Create `app/pipeline/adk_runtime.py`** — shared ADK execution helper:
```python
from __future__ import annotations

import asyncio
import os

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.core.config import Settings


def ensure_api_key(settings: Settings) -> None:
    """ADK's google client reads GOOGLE_API_KEY from the process env."""
    if settings.google_api_key and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key


async def _run_text_async(agent: Agent, payload: str, *, app_name: str = "catchup") -> str:
    runner = InMemoryRunner(agent=agent, app_name=app_name)
    session = await runner.session_service.create_session(app_name=app_name, user_id="system")
    message = types.Content(role="user", parts=[types.Part.from_text(text=payload)])
    text = ""
    async for event in runner.run_async(
        user_id="system", session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            text = event.content.parts[0].text or ""
    return text


def run_agent_text(agent: Agent, payload: str, settings: Settings, *, app_name: str = "catchup") -> str:
    """Sync bridge for the sync run_digest pipeline. Real LLM call (needs GOOGLE_API_KEY)."""
    ensure_api_key(settings)
    return asyncio.run(_run_text_async(agent, payload, app_name=app_name))
```
(No offline unit test for `run_agent_text` — it's the live boundary, validated by the existing fakes + the deferred live spike. `ensure_api_key` MAY get a tiny test: set `settings.google_api_key`, clear env, call, assert `os.environ["GOOGLE_API_KEY"]`.)

- [ ] **Step 4: Commit** — `git add app/core/config.py app/pipeline/adk_runtime.py tests/unit/test_config.py && git commit -m "feat(adk): load GOOGLE_API_KEY from app/.env + shared async runtime helper"`

---

### Task 2: Migrate `adk_enrich` and `adk_narrate` to `run_async`

**Files:**
- Modify: `app/pipeline/processing.py`, `app/pipeline/digest_editor.py`

- [ ] **Step 1: Migrate `adk_enrich`** — replace the body (keep signature + `build_processing_agent` + `_items_json` unchanged):
```python
from app.pipeline.adk_runtime import run_agent_text
# remove the now-unused: from google.adk.runners import InMemoryRunner; from google.genai import types

def adk_enrich(items: list[NewsItem], settings: Settings) -> ProcessingResult:
    """Real LLM call. Validated by the live smoke (needs GOOGLE_API_KEY)."""
    agent = build_processing_agent(settings.llm_model)
    text = run_agent_text(agent, _items_json(items), settings)
    return ProcessingResult.model_validate_json(text)
```
Remove imports that become unused (`InMemoryRunner`, `types`) — run ruff to confirm.

- [ ] **Step 2: Migrate `adk_narrate`** — in `digest_editor.py`, same treatment:
```python
from app.pipeline.adk_runtime import run_agent_text
# remove unused InMemoryRunner/types imports

def adk_narrate(items: list[NewsItem], settings: Settings) -> str:
    agent = build_editor_agent(settings.llm_model)
    payload = json.dumps(
        [{"title": i.title, "summary": i.summary_en,
          "category": (i.category.value if i.category else None)} for i in items],
        ensure_ascii=False,
    )
    text = run_agent_text(agent, payload, settings)
    return DigestNarrative.model_validate_json(text).narrative
```

- [ ] **Step 3: Verify** — `uv run pytest tests -q` (all existing tests use injected `EnrichFn`/`NarrateFn` fakes, so they stay green and offline) and `uv run --extra lint ruff check app tests` clean.

- [ ] **Step 4: Commit** — `git commit -m "refactor(adk): migrate adk_enrich/adk_narrate from sync runner.run to run_async"`

---

### Task 3: `parse_grounding` — pure harvester (TDD, offline)

**Files:**
- Create: `app/services/search.py` (partial — just `parse_grounding`)
- Create test: `tests/unit/test_search.py`

- [ ] **Step 1: Failing tests** — `tests/unit/test_search.py`:
```python
from google.genai.types import GroundingChunk, GroundingChunkWeb, GroundingMetadata

from app.core.config import SourceConfig
from app.core.domain import Category, SourceType
from app.services.search import parse_grounding

SRC = SourceConfig(id="s-ai", type=SourceType.SEARCH, name="AI Search",
                   query="latest AI news", category_hint=Category.AI_TECH)

def _md(*chunks):
    return GroundingMetadata(grounding_chunks=list(chunks))

def _chunk(uri, title=None, domain=None):
    return GroundingChunk(web=GroundingChunkWeb(uri=uri, title=title, domain=domain))

def test_parse_grounding_maps_chunks_to_rawitems():
    md = _md(_chunk("https://r/1", "Title One"), _chunk("https://r/2", "Title Two"))
    items = parse_grounding(md, SRC)
    assert [i.url for i in items] == ["https://r/1", "https://r/2"]
    assert items[0].title == "Title One"
    assert items[0].source_type == SourceType.SEARCH
    assert items[0].source_name == "AI Search"
    assert items[0].category_hint == Category.AI_TECH
    assert items[0].published_at is None

def test_parse_grounding_dedupes_by_uri():
    md = _md(_chunk("https://r/1", "A"), _chunk("https://r/1", "A again"))
    assert len(parse_grounding(md, SRC)) == 1

def test_parse_grounding_skips_chunks_without_web_uri():
    md = _md(_chunk("", "blank"), GroundingChunk(web=None))
    assert parse_grounding(md, SRC) == []

def test_parse_grounding_title_falls_back_to_domain_then_uri():
    md = _md(_chunk("https://r/3", title=None, domain="example.com"))
    assert parse_grounding(md, SRC)[0].title == "example.com"

def test_parse_grounding_handles_none_metadata():
    assert parse_grounding(None, SRC) == []
```
Run: `uv run pytest tests/unit/test_search.py -q` → FAIL (module/func missing).

- [ ] **Step 2: Implement `parse_grounding`** — `app/services/search.py`:
```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import SourceConfig
from app.core.domain import RawItem, SourceType

if TYPE_CHECKING:
    from google.genai.types import GroundingMetadata


def parse_grounding(metadata: "GroundingMetadata | None", source: SourceConfig) -> list[RawItem]:
    """Harvest cited web sources from grounding metadata into RawItems. Pure; offline-testable."""
    if metadata is None:
        return []
    items: list[RawItem] = []
    seen: set[str] = set()
    for chunk in (metadata.grounding_chunks or []):
        web = getattr(chunk, "web", None)
        uri = getattr(web, "uri", None) if web else None
        if not uri or uri in seen:
            continue
        seen.add(uri)
        title = (getattr(web, "title", None) or getattr(web, "domain", None) or uri)
        items.append(RawItem(
            source_id=source.id,
            source_type=SourceType.SEARCH,
            source_name=source.name,
            url=uri,
            title=title,
            category_hint=source.category_hint,
        ))
    return items
```
Run tests → PASS.

- [ ] **Step 3: Commit** — `git commit -m "feat(search): parse_grounding harvests RawItems from ADK grounding metadata"`

---

### Task 4: Search collector + pipeline wiring

**Files:**
- Modify: `app/services/search.py` (add `build_search_agent`, `adk_ground`, `collect`)
- Modify: `app/runner.py` (`_collect` dispatch)
- Modify: `config/sources.yaml` (add a disabled SEARCH source)
- Modify test: `tests/unit/test_search.py` (collect with injected ground)

- [ ] **Step 1: Failing test for `collect` with an injected ground boundary** — append to `tests/unit/test_search.py`:
```python
from app.core.config import Settings
from app.services import search as search_mod

def test_collect_uses_injected_ground(monkeypatch):
    md = _md(_chunk("https://r/9", "Injected"))
    items = search_mod.collect(SRC, Settings(), ground=lambda src, s: md)
    assert [i.url for i in items] == ["https://r/9"]

def test_collect_returns_empty_when_ground_none():
    assert search_mod.collect(SRC, Settings(), ground=lambda src, s: None) == []
```
Run → FAIL (`collect` missing).

- [ ] **Step 2: Implement the collector** — add to `app/services/search.py`:
```python
import asyncio
from collections.abc import Callable

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.adk.tools import google_search
from google.genai import types

from app.core.config import Settings
from app.pipeline.adk_runtime import ensure_api_key

GroundFn = Callable[[SourceConfig, Settings], "GroundingMetadata | None"]

_INSTRUCTION = (
    "You are a news search assistant. Use Google Search to find the most recent, "
    "credible news for the user's query. Briefly summarize what you found; the cited "
    "sources are what matters."
)


def build_search_agent(model: str) -> Agent:
    # NOTE: google_search cannot be combined with output_schema — search-only agent.
    return Agent(name="search_collector", model=model, instruction=_INSTRUCTION, tools=[google_search])


async def _ground_async(agent: Agent, query: str, *, app_name: str = "catchup"):
    runner = InMemoryRunner(agent=agent, app_name=app_name)
    session = await runner.session_service.create_session(app_name=app_name, user_id="system")
    message = types.Content(role="user", parts=[types.Part.from_text(text=query)])
    metadata = None
    async for event in runner.run_async(user_id="system", session_id=session.id, new_message=message):
        if getattr(event, "grounding_metadata", None):
            metadata = event.grounding_metadata  # keep last non-None
    return metadata


def adk_ground(source: SourceConfig, settings: Settings):
    """Real ADK google_search call (needs GOOGLE_API_KEY). Live-validated when quota resets."""
    if not source.query:
        return None
    ensure_api_key(settings)
    agent = build_search_agent(settings.llm_model)
    return asyncio.run(_ground_async(agent, source.query))


def collect(source: SourceConfig, settings: Settings, *, ground: GroundFn = adk_ground) -> list[RawItem]:
    return parse_grounding(ground(source, settings), source)
```
Run tests → PASS. Run ruff.

- [ ] **Step 3: Wire into the pipeline** — `app/runner.py`: add `from app.services import ... search` to the services import, and update `_collect`:
```python
    if source.type == SourceType.SCRAPE:
        return scrape.collect(source)
    if source.type == SourceType.SEARCH:
        return search.collect(source, settings)
    return []
```
Delete the stale `# SEARCH grounding arrives in Plan 5` comment.

- [ ] **Step 4: Add a disabled SEARCH source** — in `config/sources.yaml`, append (match the existing item style):
```yaml
  - id: search-ai-breakthroughs
    type: search
    name: AI Breakthroughs (Search)
    query: "most important AI and technology breakthroughs this week"
    category_hint: ai_tech
    enabled: false   # enable once Gemini quota is available — consumes model calls
```

- [ ] **Step 5: Verify** — `uv run pytest tests -q` (all green, offline; SEARCH source is disabled so `run_digest` tests don't touch it). `uv run --extra lint ruff check app tests` clean.

- [ ] **Step 6: Commit** — `git commit -m "feat(search): grounding collector + wire SourceType.SEARCH into run_digest"`

---

### Task 5: Docs, final review, PR

**Files:**
- Modify: `README.md`, `docs/BUILD-LOG.md`

- [ ] **Step 1: README** — in the Sources paragraph, add **`search`** to the source-type list: "(Search grounding; set a `query`; uses ADK `google_search`, needs `GOOGLE_API_KEY`, disabled by default as it consumes model calls)." Note that search results carry no publish date and link via Google grounding-redirect URLs.

- [ ] **Step 2: BUILD-LOG** — append `### Phase: Execution — Plan 7 (Search grounding + run_async) ✅` with: the dedicated-grounding-agent design (google_search ⊥ output_schema), the `event.grounding_metadata.grounding_chunks[*].web` harvest, the run_async migration (kills the deprecation + threaded-exception noise), the `app/.env` key-loading fix, commits, test count, and the deferred live spike (verify which event carries grounding_metadata; redirect-URL resolvability; `domain` null on Gemini API). Update `### Next` (Plan 8 orchestration · Plan 9 GCP prod).

- [ ] **Step 3: Commit docs** — `git commit -m "docs: document search sources + log Plan 7 execution"`

- [ ] **Step 4: Final review + PR** — dispatch a final reviewer over the whole `feat/search-grounding` diff, then push + open **PR #7** (`feat/search-grounding` → `main`). PR body: search collector + run_async migration + key fix; note the live grounding spike is the only deferred item (Gemini quota). All commits authored AhmedHeshamSakr.

---

## Deferred to the live spike (when Gemini quota resets)
1. Confirm **which event** in the `run_async` stream carries `grounding_metadata` (intermediate vs final) — `_ground_async` keeps the last non-None, which should be robust, but verify chunks actually arrive.
2. Confirm `web.domain` behavior on the Gemini API backend (research says often `None`).
3. Confirm redirect-URL (`vertexaisearch.cloud.google.com/grounding-api-redirect/...`) resolvability / expiry — decide later whether to resolve to the publisher URL.
4. Real chunk-count distribution per news query (tune query phrasing / source defaults).

## Self-review checklist
- **Offline:** every test mocks/injects the model boundary (`parse_grounding` pure; `collect` takes `ground=`; enrich/narrate use injected fakes in existing tests). No test needs quota. ✓
- **Constraint honored:** search agent has `tools=[google_search]` and NO `output_schema`. ✓
- **Field names:** `RawItem(source_type=SourceType.SEARCH, url=web.uri, title=web.title||domain||uri, published_at=None)`. ✓
- **run_async bridge** via `asyncio.run` is safe in the sync pipeline; exceptions now propagate into `run_digest`'s try/except (cleaner degradation). ✓
- **Key fix** unblocks live "Run now"/CLI; `ensure_api_key` only sets when present and unset. ✓
- **Commit identity** AhmedHeshamSakr, no AI trailers. ✓
