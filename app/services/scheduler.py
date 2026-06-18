"""In-process digest scheduler (APScheduler) for `catchup serve`.

build_scheduler returns a NOT-started BackgroundScheduler (the caller .start()s
and .shutdown()s it) or None when scheduling is disabled/unconfigured. The job
calls trigger_fn (the single-flight starter), which spawns its own daemon
thread, so the scheduler thread never blocks on a digest.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from app.core.config import Settings

log = logging.getLogger(__name__)


def build_scheduler(settings: Settings, trigger_fn: Callable[[], object]):
    if not settings.schedule_enabled:
        return None
    cron = settings.schedule_cron.strip()
    if not cron:
        log.warning("schedule_enabled but schedule_cron is empty; no schedule set")
        return None

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    def _job() -> None:
        if trigger_fn() is None:
            log.info("scheduled digest skipped — a run is already in progress")

    scheduler = BackgroundScheduler(timezone=settings.schedule_timezone)
    trigger = CronTrigger.from_crontab(cron, timezone=settings.schedule_timezone)
    scheduler.add_job(_job, trigger, id="digest", replace_existing=True)
    return scheduler
