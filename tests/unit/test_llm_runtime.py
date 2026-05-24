import asyncio

import pytest

from app.core.config import Settings
from app.llm import runtime


def _fast_settings(**kw):
    # Tiny backoff so retry tests stay fast.
    return Settings(
        llm_timeout=0.5,
        llm_max_retries=2,
        llm_backoff_base=0.0,
        **kw,
    )


def test_settings_have_llm_resilience_defaults():
    s = Settings()
    assert s.llm_timeout == 60.0
    assert s.llm_max_retries == 2
    assert s.llm_backoff_base == 0.5
    assert s.llm_temperature == 0.0


def test_run_agent_text_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    async def flaky(agent, payload, *, app_name="catchup", timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "OK"

    monkeypatch.setattr(runtime, "_run_text_async", flaky)
    monkeypatch.setattr(runtime.time, "sleep", lambda _s: None)

    out = runtime.run_agent_text(object(), "payload", _fast_settings(google_api_key="x"))
    assert out == "OK"
    assert calls["n"] == 3  # failed twice, succeeded on the 3rd


def test_run_agent_text_raises_after_exhausting_retries(monkeypatch):
    async def always_fail(agent, payload, *, app_name="catchup", timeout=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(runtime, "_run_text_async", always_fail)
    monkeypatch.setattr(runtime.time, "sleep", lambda _s: None)

    with pytest.raises(RuntimeError, match="boom"):
        runtime.run_agent_text(object(), "payload", _fast_settings(google_api_key="x"))


def test_run_agent_text_retries_on_timeout_then_raises(monkeypatch):
    calls = {"n": 0}

    async def timing_out(agent, payload, *, app_name="catchup", timeout=None):
        # Simulate asyncio.wait_for firing: the same signal the retry loop sees
        # when a real per-attempt timeout is exceeded.
        calls["n"] += 1
        raise TimeoutError("timed out")

    monkeypatch.setattr(runtime, "_run_text_async", timing_out)
    monkeypatch.setattr(runtime.time, "sleep", lambda _s: None)

    s = _fast_settings(google_api_key="x")
    with pytest.raises(asyncio.TimeoutError):
        runtime.run_agent_text(object(), "payload", s)
    assert calls["n"] == 1 + s.llm_max_retries  # one initial + retries


def test_run_text_async_applies_timeout(monkeypatch):
    # Exercise the real wait_for path inside _run_text_async (no monkeypatch of it).
    import app.llm.runtime as rt

    class _NeverRunner:
        def __init__(self, *a, **k):
            self.session_service = self

        async def create_session(self, **k):
            class _S:
                id = "s"
            return _S()

        async def run_async(self, **k):
            await asyncio.sleep(10)
            if False:  # pragma: no cover — make this an async generator
                yield None

    monkeypatch.setattr(rt, "InMemoryRunner", _NeverRunner)

    async def _go():
        await rt._run_text_async(object(), "p", timeout=0.05)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_go())
