import threading

import pytest

from app.core.config import Settings
from app.run_trigger import _run_lock, try_start_run


@pytest.fixture(autouse=True)
def _ensure_lock_free():
    yield
    if _run_lock.locked():
        try:
            _run_lock.release()
        except RuntimeError:
            pass


def _s():
    return Settings(_env_file=None)


def test_try_start_run_returns_run_id_and_runs_fn():
    ran = threading.Event()
    seen = {}

    def fake_run(*, settings, run_id):
        seen["run_id"] = run_id
        ran.set()

    rid = try_start_run(_s(), run_digest_fn=fake_run)
    assert rid is not None and len(rid) == 12
    assert ran.wait(timeout=2)
    assert seen["run_id"] == rid


def test_try_start_run_single_flight_returns_none_when_locked():
    assert _run_lock.acquire(blocking=False)
    try:
        assert try_start_run(_s(), run_digest_fn=lambda **kw: None) is None
    finally:
        _run_lock.release()
