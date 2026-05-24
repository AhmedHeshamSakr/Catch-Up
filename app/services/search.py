from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.adk.tools import google_search
from google.genai import types

from app.core.config import Settings, SourceConfig
from app.core.domain import RawItem, SourceType
from app.llm.runtime import _run_coro_sync, ensure_api_key

if TYPE_CHECKING:
    from google.genai.types import GroundingMetadata

GroundFn = Callable[[SourceConfig, Settings], "GroundingMetadata | None"]

_INSTRUCTION = (
    "You are a news search assistant. Use Google Search to find the most recent, "
    "credible news for the user's query. Briefly summarize what you found; the cited "
    "sources are what matters."
)


def parse_grounding(metadata: GroundingMetadata | None, source: SourceConfig) -> list[RawItem]:
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
        title = getattr(web, "title", None) or getattr(web, "domain", None) or uri
        items.append(
            RawItem(
                source_id=source.id,
                source_type=SourceType.SEARCH,
                source_name=source.name,
                url=uri,
                title=title,
                category_hint=source.category_hint,
            )
        )
    return items


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
    # Loop-aware bridge: collectors run via asyncio.to_thread today, but use the
    # shared sync->async bridge so a bare asyncio.run never executes inside a
    # running event loop (same nested-loop hazard fixed in run_agent_text).
    return _run_coro_sync(_ground_async(agent, source.query))


def collect(source: SourceConfig, settings: Settings, *, ground: GroundFn = adk_ground) -> list[RawItem]:
    return parse_grounding(ground(source, settings), source)
