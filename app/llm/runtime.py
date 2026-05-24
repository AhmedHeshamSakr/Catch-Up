from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.core.config import Settings

_T = TypeVar("_T")


def _run_coro_sync(coro: Coroutine[object, object, _T]) -> _T:
    """Run a coroutine to completion from sync code, loop-aware.

    If no event loop is running in this thread, use ``asyncio.run``. If a loop
    is already running (we're inside the ADK tree driven by ``asyncio.run``),
    run the coroutine on a worker thread with its own loop so we never call
    ``asyncio.run`` inside a running loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coro)).result()


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
    return _run_coro_sync(_run_text_async(agent, payload, app_name=app_name))
