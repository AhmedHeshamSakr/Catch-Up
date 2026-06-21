from __future__ import annotations

import asyncio
import os
import random
import time
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


def configure_genai(settings: Settings) -> None:
    """Configure the google-genai client env for AI Studio (default) or Vertex.

    Never overwrites a value already in os.environ (respects operator-set env).
    Uses getattr defaults so minimal test settings-stubs (which only define
    google_api_key) keep working — see tests/integration/test_pipeline_live_bridge.py.
    """
    if getattr(settings, "use_vertexai", False):
        project = getattr(settings, "google_cloud_project", "")
        if not project:
            raise ValueError("use_vertexai=True requires google_cloud_project")
        location = getattr(settings, "google_cloud_location", "global")
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", location)
        return
    # AI Studio (unchanged): the google client reads GOOGLE_API_KEY from the env.
    if settings.google_api_key and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key


# Back-compat alias — existing call-sites/tests import ``ensure_api_key``.
ensure_api_key = configure_genai


async def _run_text_async(
    agent: Agent, payload: str, *, app_name: str = "catchup", timeout: float | None = None
) -> str:
    async def _consume() -> str:
        runner = InMemoryRunner(agent=agent, app_name=app_name)
        session = await runner.session_service.create_session(
            app_name=app_name, user_id="system"
        )
        message = types.Content(role="user", parts=[types.Part.from_text(text=payload)])
        text = ""
        async for event in runner.run_async(
            user_id="system", session_id=session.id, new_message=message
        ):
            if event.is_final_response() and event.content and event.content.parts:
                text = event.content.parts[0].text or ""
        return text

    if timeout is None:
        return await _consume()
    return await asyncio.wait_for(_consume(), timeout=timeout)


def _is_retryable(exc: Exception) -> bool:
    """Retry only TRANSIENT failures (timeouts, rate limits, 5xx, transport).

    Fail fast on PERMANENT ones — auth, model-not-found, invalid request,
    config/validation — so a misconfiguration surfaces immediately instead of
    being masked as a slow 'transient' across every retry+backoff.
    """
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        # config / programming / validation errors won't fix on retry
        return False
    # google.genai APIError (and many HTTP clients) expose the status as .code /
    # .status_code; httpx transport errors have neither and fall through to retry.
    code = getattr(exc, "status_code", None)
    if not isinstance(code, int):
        code = getattr(exc, "code", None)
    if isinstance(code, int):
        if code in (408, 429) or 500 <= code <= 599:
            return True
        if 400 <= code <= 499:
            return False  # auth / not-found / invalid request — permanent
    return True  # unknown → treat as transient (favor availability)


def run_agent_text(
    agent: Agent, payload: str, settings: Settings, *, app_name: str = "catchup"
) -> str:
    """Sync bridge for the sync run_digest pipeline. Real LLM call (needs GOOGLE_API_KEY).

    Applies a per-attempt timeout and retries TRANSIENT failures (timeouts, rate
    limits, 5xx, transport) with exponential backoff plus jitter. Permanent
    failures (auth/not-found/invalid-request/config — see ``_is_retryable``) are
    re-raised immediately rather than retried.
    """
    configure_genai(settings)
    attempts = 1 + max(0, settings.llm_max_retries)
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return _run_coro_sync(
                _run_text_async(agent, payload, app_name=app_name, timeout=settings.llm_timeout)
            )
        except Exception as exc:
            last_exc = exc
            if attempt == attempts - 1 or not _is_retryable(exc):
                break
            sleep = settings.llm_backoff_base * (2**attempt) + random.uniform(
                0, settings.llm_backoff_base
            )
            time.sleep(sleep)
    assert last_exc is not None
    raise last_exc
