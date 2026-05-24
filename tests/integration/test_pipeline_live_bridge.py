"""Integration test: run_agent_text must work whether or not an event loop is running.

Regression guard for the nested-asyncio.run bug: the ADK tree is driven by
asyncio.run(_run_tree), so the default processor/critic/narrator call
run_agent_text from *inside* a running loop. Calling asyncio.run there raises
RuntimeError. These tests stub the model layer (_run_text_async) so they never
hit Gemini, and verify the sync bridge works in both contexts.
"""
from __future__ import annotations

import asyncio

import pytest

from app.llm import runtime as adk_runtime

_CANNED = "canned model output"


class _SettingsStub:
    """Minimal stand-in: ensure_api_key only reads ``google_api_key``."""

    google_api_key = None


@pytest.fixture
def stub_model(monkeypatch):
    async def _fake_run_text_async(agent, payload, *, app_name="catchup"):
        return _CANNED

    monkeypatch.setattr(adk_runtime, "_run_text_async", _fake_run_text_async)


def test_run_agent_text_works_inside_running_loop(stub_model):
    """Called from within asyncio.run(...) — mirrors the live ADK tree path."""

    async def driver():
        return adk_runtime.run_agent_text(object(), "payload", _SettingsStub())

    result = asyncio.run(driver())
    assert result == _CANNED


def test_run_agent_text_works_without_loop(stub_model):
    """Called from plain sync code — no running loop."""
    result = adk_runtime.run_agent_text(object(), "payload", _SettingsStub())
    assert result == _CANNED
