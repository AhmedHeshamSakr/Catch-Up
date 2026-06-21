import logging

from app.core.config import Settings
from app.services.scheduler import build_scheduler


def _s(**kw):
    return Settings(_env_file=None, **kw)


def test_disabled_returns_none():
    assert build_scheduler(_s(schedule_enabled=False), lambda: "x") is None


def test_empty_cron_returns_none():
    assert build_scheduler(_s(schedule_enabled=True, schedule_cron=""), lambda: "x") is None


def test_enabled_has_one_cron_job():
    from apscheduler.triggers.cron import CronTrigger
    sched = build_scheduler(_s(schedule_enabled=True, schedule_cron="0 7 * * *"), lambda: "x")
    assert sched is not None
    jobs = sched.get_jobs()
    assert len(jobs) == 1
    assert isinstance(jobs[0].trigger, CronTrigger)


def test_bad_cron_disables_scheduling_not_crash(caplog):
    """A bad cron must NOT crash app startup (build_scheduler runs in the FastAPI
    lifespan) — it logs and returns None (scheduling disabled) instead of raising."""
    with caplog.at_level(logging.ERROR):
        result = build_scheduler(
            _s(schedule_enabled=True, schedule_cron="not a cron"), lambda: "x"
        )
    assert result is None
    assert any("schedule_cron" in r.message for r in caplog.records)


def test_job_calls_trigger_fn():
    calls = []

    def fake_trigger():
        calls.append(1)
        return "runid1234567"  # truthy run_id → no skip log

    sched = build_scheduler(_s(schedule_enabled=True, schedule_cron="0 7 * * *"), fake_trigger)
    sched.get_jobs()[0].func()  # invoke the registered job directly (scheduler not started)
    assert calls == [1]


def test_job_logs_skip_when_run_in_progress(caplog):
    sched = build_scheduler(_s(schedule_enabled=True, schedule_cron="0 7 * * *"), lambda: None)
    with caplog.at_level(logging.INFO):
        sched.get_jobs()[0].func()
    assert any("skipped" in r.message for r in caplog.records)
