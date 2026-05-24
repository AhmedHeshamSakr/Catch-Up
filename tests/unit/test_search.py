from __future__ import annotations

from google.genai.types import GroundingChunk, GroundingChunkWeb, GroundingMetadata

from app.core.config import Settings, SourceConfig
from app.core.domain import Category, SourceType
from app.services.search import parse_grounding

SRC = SourceConfig(
    id="s-ai",
    type=SourceType.SEARCH,
    name="AI Search",
    query="latest AI news",
    category_hint=Category.AI_TECH,
)


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


# ---------------------------------------------------------------------------
# Task 4 — collect() with injected ground boundary
# ---------------------------------------------------------------------------

from app.services import search as search_mod  # noqa: E402


def test_collect_uses_injected_ground():
    md = _md(_chunk("https://r/9", "Injected"))
    items = search_mod.collect(SRC, Settings(), ground=lambda src, s: md)
    assert [i.url for i in items] == ["https://r/9"]


def test_collect_returns_empty_when_ground_none():
    assert search_mod.collect(SRC, Settings(), ground=lambda src, s: None) == []


# ---------------------------------------------------------------------------
# Loop-aware sync->async bridge (no bare asyncio.run inside a running loop)
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402


def test_adk_ground_works_inside_running_loop(monkeypatch):
    """adk_ground must use the shared loop-aware bridge, not a bare asyncio.run.

    Driven from INSIDE a running event loop (mirrors the ADK tree path where
    collectors run via asyncio.to_thread). A bare asyncio.run here would raise
    RuntimeError; the shared bridge runs on a worker thread instead.
    """
    sentinel = GroundingMetadata(grounding_chunks=[])

    async def _fake_ground_async(agent, query, *, app_name="catchup"):
        return sentinel

    monkeypatch.setattr(search_mod, "_ground_async", _fake_ground_async)
    monkeypatch.setattr(search_mod, "ensure_api_key", lambda settings: None)
    monkeypatch.setattr(search_mod, "build_search_agent", lambda model: object())

    async def driver():
        return search_mod.adk_ground(SRC, Settings())

    result = asyncio.run(driver())
    assert result is sentinel
