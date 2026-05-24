# Plan 7 Research: Google Search Grounding Collector + run_async Migration

**Date:** 2026-05-24  
**ADK Version:** 1.34.1 (installed at `.venv/lib/python3.13/site-packages/google/adk/`)  
**Scope:** Implementation-ready reference for the search collector and async migration. No code was modified.

---

## 1. ADK Version & Confirmed Imports

```
google-adk == 1.34.1
google-genai (bundled, same venv)
```

### Confirmed import paths

```python
# The singleton instance (preferred):
from google.adk.tools import google_search           # re-exported in tools/__init__.py

# The class (if you need to construct with options):
from google.adk.tools.google_search_tool import GoogleSearchTool

# The runner and session service:
from google.adk.runners import InMemoryRunner, Runner
from google.adk.agents import Agent
from google.genai import types

# Grounding types (all in genai, not adk):
from google.genai.types import GroundingMetadata, GroundingChunk, GroundingChunkWeb, GroundingSupport
```

Source files:
- `.venv/.../google/adk/tools/google_search_tool.py` — defines `GoogleSearchTool` class and `google_search` singleton
- `.venv/.../google/adk/tools/__init__.py` line 35: `from .google_search_tool import google_search`
- `.venv/.../google/adk/models/llm_response.py` line 69: `grounding_metadata: Optional[types.GroundingMetadata] = None`

---

## 2. google_search Tool Usage & Constraints

### Basic agent construction

```python
from google.adk.agents import Agent
from google.adk.tools import google_search

search_agent = Agent(
    name="search_collector",
    model="gemini-2.0-flash",   # or gemini-2.5-flash / gemini-2.0-pro
    instruction=(
        "Search for the latest news about: {query}. "
        "Return a JSON list of relevant articles with title and URL."
    ),
    tools=[google_search],
)
```

### Model support

From `google_search_tool.py` lines 74-88:
- **Gemini 1.x** (`is_gemini_1_model`): uses `types.Tool(google_search_retrieval=types.GoogleSearchRetrieval())` — only tool allowed, no others
- **Gemini 2.x and above** (`is_gemini_model`): uses `types.Tool(google_search=types.GoogleSearch())` — this is the preferred path
- Any non-Gemini model raises `ValueError`

**Confirmed supported:** `gemini-2.0-flash`, `gemini-2.5-flash`, `gemini-2.0-pro`

### The multi-tool constraint and output_schema workaround

**Constraint:** `google_search` (a built-in tool) CANNOT be combined with other tools OR with `output_schema` in the same agent — unless you use the escape hatch.

Source: `llm_agent.py` lines 148-157:
```
# Wrap google_search tool with AgentTool if there are multiple tools because
# the built-in tools cannot be used together with other tools.
if multiple_tools and isinstance(tool_union, GoogleSearchTool):
    search_tool = cast(GoogleSearchTool, tool_union)
    if search_tool.bypass_multi_tools_limit:
        return [GoogleSearchAgentTool(create_google_search_agent(model))]
```

And `_output_schema_processor.py` lines 43-66: when `output_schema` AND `tools` are both present and the model does not natively support combining them, ADK automatically injects a `set_model_response` tool — but this still cannot work with `google_search` because `google_search` must be the ONLY built-in tool.

**The two valid patterns:**

#### Pattern A — Dedicated grounding-only agent (RECOMMENDED for Plan 7)
Use a separate agent with only `google_search` and NO `output_schema`. Extract grounding metadata from events. Parse `RawItem`s from the metadata directly (not from model text).

```python
search_agent = Agent(
    name="search_collector",
    model="gemini-2.0-flash",
    instruction="Search for recent news: {query}. Summarize each result briefly.",
    tools=[google_search],
    # NO output_schema here — metadata is in event.grounding_metadata
)
```

#### Pattern B — bypass_multi_tools_limit=True
Use `GoogleSearchTool(bypass_multi_tools_limit=True)` to allow google_search alongside other tools. ADK wraps it in a `GoogleSearchAgentTool` sub-agent internally. This is less predictable for grounding metadata extraction since the sub-agent handles it.

**Chosen workaround for Plan 7:** Pattern A. The search collector's sole job is to fire the query and harvest grounding metadata → `RawItem` list. No need for `output_schema` in the search agent.

---

## 3. Grounding Metadata Shape

### Where it lives on events

The `Event` class extends `LlmResponse` (source: `models/llm_response.py` line 69):

```python
event.grounding_metadata  # Optional[types.GroundingMetadata]
```

This is populated from `candidate.grounding_metadata` (line 191 of `llm_response.py`), which maps directly to the genai `GenerateContentResponse.candidates[0].grounding_metadata`.

### Full type hierarchy (from `google/genai/types.py`)

```
GroundingMetadata
├── grounding_chunks: list[GroundingChunk] | None
│   └── GroundingChunk
│       ├── web: GroundingChunkWeb | None          ← Google Search results live here
│       │   ├── uri: str | None                    ← the source URL (see redirect caveat)
│       │   ├── title: str | None                  ← page title
│       │   └── domain: str | None                 ← domain (Vertex AI only, not Gemini API)
│       ├── image: GroundingChunkImage | None
│       ├── maps: GroundingChunkMaps | None
│       └── retrieved_context: GroundingChunkRetrievedContext | None
├── grounding_supports: list[GroundingSupport] | None
│   └── GroundingSupport
│       ├── grounding_chunk_indices: list[int]     ← which chunks support this claim
│       ├── confidence_scores: list[float]          ← 0.0–1.0 per chunk
│       └── segment: Segment                        ← text offset in response
├── web_search_queries: list[str] | None           ← actual queries sent to Google
├── search_entry_point: SearchEntryPoint | None    ← rendered HTML snippet for "Google it"
└── retrieval_metadata: RetrievalMetadata | None
```

### Exact attribute paths (copy-paste ready)

```python
# On the event:
gm = event.grounding_metadata           # GroundingMetadata | None

if gm and gm.grounding_chunks:
    for chunk in gm.grounding_chunks:
        if chunk.web:
            uri   = chunk.web.uri      # str | None  ← REDIRECT URL (see §4)
            title = chunk.web.title    # str | None
            domain = chunk.web.domain  # str | None  ← only on Vertex AI, None on Gemini API

# Queries used:
queries = gm.web_search_queries         # list[str] | None
```

### Concrete synthetic example object

```python
from google.genai.types import (
    GroundingMetadata, GroundingChunk, GroundingChunkWeb, GroundingSupport, Segment
)

example_gm = GroundingMetadata(
    web_search_queries=["AI news May 2026"],
    grounding_chunks=[
        GroundingChunk(web=GroundingChunkWeb(
            uri="https://vertexaisearch.cloud.google.com/grounding-api-redirect/...",
            title="OpenAI announces GPT-5 Turbo",
            domain=None,  # None on Gemini API, populated on Vertex AI
        )),
        GroundingChunk(web=GroundingChunkWeb(
            uri="https://vertexaisearch.cloud.google.com/grounding-api-redirect/...",
            title="Google releases Gemini Ultra 3",
            domain=None,
        )),
    ],
    grounding_supports=[
        GroundingSupport(
            grounding_chunk_indices=[0],
            confidence_scores=[0.92],
            segment=Segment(start_index=0, end_index=42, text="OpenAI announced GPT-5 Turbo today"),
        )
    ],
)
```

---

## 4. Redirect-URL Caveat

**The problem:** `chunk.web.uri` values are NOT publisher URLs. They are Vertex AI redirect links of the form:

```
https://vertexaisearch.cloud.google.com/grounding-api-redirect/AZnLqXxxx...
```

These redirects DO resolve (HTTP 302) to the real publisher URL if you follow them via HTTP — but:
1. Following them requires an HTTP round-trip per chunk (latency).
2. The redirect link may expire.
3. During offline testing, they are meaningless.

**Practical implications for `RawItem`:**

| Field | What to store |
|---|---|
| `RawItem.url` | Store the redirect URI as-is. It is technically valid (followable). Alternatively, follow the redirect at harvest time with `httpx.get(..., follow_redirects=False)` and store the `Location` header. |
| `RawItem.title` | Always use `chunk.web.title` — this is the real page title. |
| `RawItem.source_name` | Use `chunk.web.domain` if non-None (Vertex); otherwise parse from title or set to the source config name. |
| `RawItem.excerpt` | Set from the `GroundingSupport.segment.text` that references this chunk's index, OR from the model's response text near this chunk's citation. |

**Recommended approach for Plan 7:** Store redirect URI in `url`. In the UI/render layer, display `web.title` and `web.domain`. Do not follow the redirect at harvest time (adds latency; the spike can validate if real URLs are needed).

---

## 5. run_async Migration Pattern

### What the sync `runner.run(...)` actually does

From `runners.py` lines 463-499: `runner.run()` spins up a background thread, runs `asyncio.run(_invoke_run_async())` inside it, and proxies events through a `queue.Queue`. The `create_session_sync()` emits the deprecation warning (line 101 of `in_memory_session_service.py`). Exceptions in the thread escape the caller's `try/except` because they surface on the background thread's stack.

### Canonical async pattern

```python
import asyncio
from google.adk.runners import InMemoryRunner
from google.adk.agents import Agent
from google.genai import types

async def run_agent_async(agent: Agent, app_name: str, prompt: str) -> tuple[str, types.GroundingMetadata | None]:
    """Returns (final_text, grounding_metadata). grounding_metadata is None for non-search agents."""
    runner = InMemoryRunner(agent=agent, app_name=app_name)

    # Must await create_session (not create_session_sync)
    session = await runner.session_service.create_session(
        app_name=app_name, user_id="system"
    )
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt)]
    )

    text = ""
    grounding_metadata = None

    async for event in runner.run_async(
        user_id="system",
        session_id=session.id,
        new_message=message,
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                text = event.content.parts[0].text or ""
            if event.grounding_metadata:
                grounding_metadata = event.grounding_metadata

    return text, grounding_metadata
```

### Bridging into sync callers (adk_enrich, adk_narrate, pipeline)

The existing `adk_enrich` and `adk_narrate` are called from the sync `run_digest` pipeline. Two valid approaches:

**Option A — asyncio.run() wrapper (zero refactor to callers):**
```python
def adk_enrich(items: list[NewsItem], settings: Settings) -> ProcessingResult:
    return asyncio.run(_adk_enrich_async(items, settings))

async def _adk_enrich_async(items: list[NewsItem], settings: Settings) -> ProcessingResult:
    agent = build_processing_agent(settings.llm_model)
    text, _ = await run_agent_async(agent, "catchup", _items_json(items))
    return ProcessingResult.model_validate_json(text)
```

**Option B — make the pipeline async end-to-end** (cleaner long-term; FastAPI supports `async def` route handlers natively). The `run_digest` function becomes `async def run_digest(...)` and all callers `await` it.

**Recommendation:** Start with Option A (least diff, unblocks Plan 7 immediately). Plan the Option B refactor as a separate task.

### Exception propagation

With `run_async`, any model error raises as a standard Python exception inside the `async for` loop — caught by the enclosing `try/except` normally. With the sync `runner.run()`, the exception originates inside the background thread and, depending on Python version and the thread implementation, may not propagate cleanly.

---

## 6. Offline Testing Strategy

### Why it's needed

Plan 7 must be fully testable without network/model calls. The key function to test is:

```python
def parse_grounding(
    metadata: types.GroundingMetadata,
    source_id: str,
    source_name: str,
    category_hint: Category | None,
) -> list[RawItem]:
    """Convert GroundingMetadata → list[RawItem]. No network, no model."""
    ...
```

### Constructing synthetic GroundingMetadata in pytest

`GroundingMetadata` and friends are standard Pydantic `BaseModel` subclasses (via `_common.BaseModel`). Construct them directly:

```python
# tests/unit/services/test_search.py
import pytest
from google.genai.types import (
    GroundingMetadata, GroundingChunk, GroundingChunkWeb, GroundingSupport, Segment
)
from app.core.domain import Category, RawItem, SourceType
from app.services.search import parse_grounding   # the function under test


def make_grounding_metadata() -> GroundingMetadata:
    return GroundingMetadata(
        web_search_queries=["AI news May 2026"],
        grounding_chunks=[
            GroundingChunk(web=GroundingChunkWeb(
                uri="https://vertexaisearch.cloud.google.com/grounding-api-redirect/ABC123",
                title="OpenAI announces GPT-5 Turbo",
                domain=None,
            )),
            GroundingChunk(web=GroundingChunkWeb(
                uri="https://vertexaisearch.cloud.google.com/grounding-api-redirect/DEF456",
                title="Google Gemini Ultra 3 released",
                domain=None,
            )),
            # chunk with no web (e.g. Maps chunk) — must be skipped:
            GroundingChunk(web=None),
        ],
        grounding_supports=[
            GroundingSupport(
                grounding_chunk_indices=[0],
                confidence_scores=[0.95],
                segment=Segment(start_index=0, end_index=35, text="OpenAI announced GPT-5 Turbo"),
            ),
            GroundingSupport(
                grounding_chunk_indices=[1],
                confidence_scores=[0.88],
                segment=Segment(start_index=36, end_index=70, text="Google released Gemini Ultra 3"),
            ),
        ],
    )


def test_parse_grounding_returns_raw_items():
    gm = make_grounding_metadata()
    items = parse_grounding(gm, source_id="gs_ai_tech", source_name="Google Search", category_hint=Category.AI_TECH)

    assert len(items) == 2  # chunk with no .web must be skipped
    assert all(i.source_type == SourceType.SEARCH for i in items)
    assert items[0].title == "OpenAI announces GPT-5 Turbo"
    assert "vertexaisearch" in items[0].url
    assert items[0].excerpt == "OpenAI announced GPT-5 Turbo"  # from segment text
    assert items[0].published_at is None  # no date in grounding metadata


def test_parse_grounding_skips_chunks_without_web():
    gm = GroundingMetadata(grounding_chunks=[GroundingChunk(web=None)])
    items = parse_grounding(gm, "src", "Test", None)
    assert items == []


def test_parse_grounding_empty_metadata():
    gm = GroundingMetadata()
    items = parse_grounding(gm, "src", "Test", None)
    assert items == []
```

### Synthetic event fixture for run_async event-loop tests

```python
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai import types

def make_grounding_event(gm: GroundingMetadata) -> Event:
    """Fake final-response event carrying grounding metadata."""
    return Event(
        author="search_collector",
        invocation_id="test-invocation-001",
        content=types.Content(
            role="model",
            parts=[types.Part(text="Here are the results...")],
        ),
        grounding_metadata=gm,
        actions=EventActions(),
    )
```

You can then test the event-processing loop in isolation by passing this synthetic event list to the harvest function without running a real `Runner`.

---

## 7. Open Questions / What the Live Spike Must Confirm

1. **Do grounding chunks always appear on the FINAL response event?**
   In streaming, `grounding_metadata` may appear on a non-final intermediate event. The spike should log ALL events and confirm which one carries populated `grounding_metadata`. The current plan is to collect it from the first non-None occurrence.

2. **Number of grounding chunks per query.** The Gemini API typically returns 3–10 chunks. The spike should characterise the real distribution for news queries and determine if multiple queries per source config are needed.

3. **Redirect URL resolution.** Confirm whether redirect URLs are followable with a simple `httpx.head(url, follow_redirects=False)` → `Location` header. If so, Plan 7+ can do async batch resolution cheaply.

4. **`domain` field population.** The type definition says `domain` is not supported in Gemini API — only Vertex AI. The live spike should confirm `chunk.web.domain` is always `None` when using Gemini API key (not Vertex endpoint), so fallback logic (parse from title or URL) is required.

5. **output_schema + google_search via SetModelResponseTool.** The `_output_schema_processor.py` shows that ADK 1.34.1 has a partial workaround (SetModelResponseTool injection). However this still requires the model to call a function tool AND a built-in tool in the same turn — not guaranteed to work with all Gemini 2.x versions. The spike should test `GoogleSearchTool(bypass_multi_tools_limit=True)` with an `output_schema` agent and verify grounding metadata survives the `GoogleSearchAgentTool` wrapper.

6. **Published dates.** Confirmed: `GroundingMetadata` has no date fields. `RawItem.published_at` will always be `None` for search results. A future enhancement could attempt to parse dates from `segment.text` or by fetching and parsing the destination page.

7. **Quota / pricing.** Google Search grounding is a paid feature on Vertex AI (free tier on Gemini API has a cap). Confirm the quota situation before enabling in production.

---

## Appendix: Minimal search collector skeleton

```python
# app/services/search.py  (to be created in Plan 7)
from __future__ import annotations

import asyncio
from datetime import datetime

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.adk.tools import google_search
from google.genai import types

from app.core.config import SourceConfig
from app.core.domain import RawItem, SourceType, make_item_id


def parse_grounding(
    metadata: types.GroundingMetadata,
    source_id: str,
    source_name: str,
    category_hint=None,
) -> list[RawItem]:
    """Convert GroundingMetadata → list[RawItem]. Pure, no I/O."""
    if not metadata or not metadata.grounding_chunks:
        return []

    # Build a map: chunk_index → excerpt (from grounding_supports)
    excerpts: dict[int, str] = {}
    if metadata.grounding_supports:
        for support in metadata.grounding_supports:
            if support.grounding_chunk_indices and support.segment and support.segment.text:
                for idx in support.grounding_chunk_indices:
                    if idx not in excerpts:
                        excerpts[idx] = support.segment.text

    items: list[RawItem] = []
    for i, chunk in enumerate(metadata.grounding_chunks):
        if not chunk.web or not chunk.web.uri or not chunk.web.title:
            continue
        url = chunk.web.uri
        items.append(RawItem(
            source_id=source_id,
            source_type=SourceType.SEARCH,
            source_name=source_name,
            url=url,
            title=chunk.web.title.strip(),
            excerpt=excerpts.get(i),
            published_at=None,           # grounding metadata has no date
            category_hint=category_hint,
        ))
    return items


async def _collect_async(source: SourceConfig, model: str) -> list[RawItem]:
    agent = Agent(
        name="search_collector",
        model=model,
        instruction=f"Search for recent news about: {source.name}. Be comprehensive.",
        tools=[google_search],
    )
    runner = InMemoryRunner(agent=agent, app_name="catchup")
    session = await runner.session_service.create_session(
        app_name="catchup", user_id="system"
    )
    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=f"Latest news: {source.name}")]
    )
    grounding_metadata = None
    async for event in runner.run_async(
        user_id="system", session_id=session.id, new_message=message
    ):
        if event.grounding_metadata:
            grounding_metadata = event.grounding_metadata

    if grounding_metadata is None:
        return []
    return parse_grounding(grounding_metadata, source.id, source.name, source.category_hint)


def collect(source: SourceConfig, model: str = "gemini-2.0-flash") -> list[RawItem]:
    """Sync entry point matching the collector interface."""
    return asyncio.run(_collect_async(source, model))
```
