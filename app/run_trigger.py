"""Single-flight digest-run starter, shared by POST /api/runs and the scheduler.

One process-wide lock guards run_digest so a scheduled run and a manual trigger
can never fan out two pipelines onto one SQLite file. (Multi-instance needs a
shared cross-process lock — production milestone.)
"""
from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

from app.core.config import Settings
from app.runner import run_digest

_run_lock = threading.Lock()


def _run_digest_guarded(
    run_digest_fn: Callable[..., object], *, settings: Settings, run_id: str
) -> None:
    try:
        run_digest_fn(settings=settings, run_id=run_id)
    finally:
        _run_lock.release()


def try_start_run(
    settings: Settings, *, run_digest_fn: Callable[..., object] = run_digest
) -> str | None:
    """Start a digest on a daemon thread if none is running; return its run_id,
    or None if a run is already in flight. The lock is released by
    _run_digest_guarded's finally (even on client disconnect)."""
    if not _run_lock.acquire(blocking=False):
        return None
    run_id = uuid.uuid4().hex[:12]
    try:
        threading.Thread(
            target=_run_digest_guarded,
            kwargs={"run_digest_fn": run_digest_fn, "settings": settings, "run_id": run_id},
            daemon=True,
        ).start()
    except BaseException:
        # The thread never started, so its finally won't release the lock —
        # release here, else every future run would 409 / be skipped forever.
        _run_lock.release()
        raise
    return run_id
