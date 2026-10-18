"""Background schedule: nightly full recompute (02:00 local) and hourly Moon refresh."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session

from skycal.db.session import get_engine
from skycal.jobs.recompute import recompute_all, refresh_moon
from skycal.settings import get_settings

log = logging.getLogger(__name__)


def nightly() -> None:
    with Session(get_engine()) as session:
        counts = recompute_all(session)
    log.info("nightly recompute done: %d entities, %d events", len(counts), sum(counts.values()))


def hourly_moon() -> None:
    with Session(get_engine()) as session:
        n = refresh_moon(session)
    log.info("hourly moon refresh: %d events", n)


def build_scheduler() -> BackgroundScheduler:
    tz = get_settings().app_timezone
    sched = BackgroundScheduler(timezone=tz)
    sched.add_job(
        nightly, CronTrigger(hour=2, minute=0, timezone=tz), id="nightly", coalesce=True,
        misfire_grace_time=3600, max_instances=1,
    )  # fmt: skip
    sched.add_job(
        hourly_moon, CronTrigger(minute=5, timezone=tz), id="hourly_moon", coalesce=True,
        misfire_grace_time=600, max_instances=1,
    )  # fmt: skip
    return sched
