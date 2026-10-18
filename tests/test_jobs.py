from datetime import UTC, date, datetime, time

import pytest
from sqlmodel import Session, SQLModel, create_engine, func, select

from skycal.api.routes.entities import EntityCreate, birth_to_utc, create_entity_row
from skycal.db.models import Event, TimeKnown, User
from skycal.jobs.recompute import recompute_all, refresh_moon
from skycal.jobs.scheduler import build_scheduler

NOW = datetime(2026, 10, 18, 7, 0, tzinfo=UTC)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed(session) -> None:
    user = User(email="t@example.com", prefs={"timezone": "America/New_York"})
    session.add(user)
    session.commit()
    create_entity_row(
        session,
        user.id,
        EntityCreate(
            name="t",
            birth_date=date(1990, 7, 15),
            birth_time=time(14, 30),
            birth_tz="America/New_York",
            birth_lat=40.7128,
            birth_lon=-74.006,
        ),
    )


def test_recompute_all_is_idempotent(session):
    _seed(session)
    first = recompute_all(session, now=NOW)
    uids1 = set(session.exec(select(Event.uid)).all())
    second = recompute_all(session, now=NOW)
    uids2 = set(session.exec(select(Event.uid)).all())
    assert list(first.values()) == list(second.values())
    assert uids1 == uids2
    assert session.exec(select(func.count()).select_from(Event)).one() == len(uids2)
    latest = session.exec(select(func.max(Event.start))).one()
    assert latest.date() <= date(2027, 1, 16)  # nothing starts past +90 days
    # 90-day window reaches the full tier range
    assert set(session.exec(select(Event.tier)).all()) == {1, 2, 3, 4}


def test_refresh_moon_only_touches_moon(session):
    _seed(session)
    recompute_all(session, now=NOW)
    before = session.exec(select(Event.uid).where(Event.transiting_point != "Moon")).all()
    refresh_moon(session, now=NOW)
    after = session.exec(select(Event.uid).where(Event.transiting_point != "Moon")).all()
    assert sorted(before) == sorted(after)


def test_scheduler_jobs():
    sched = build_scheduler()
    jobs = {j.id: j for j in sched.get_jobs()}
    assert set(jobs) == {"nightly", "hourly_moon"}
    assert "hour='2'" in str(jobs["nightly"].trigger)


def test_unknown_birth_time_cast_at_noon_local():
    dt, tk = birth_to_utc(date(1990, 1, 1), None, "Asia/Kolkata", TimeKnown.exact)
    assert tk == TimeKnown.unknown
    assert dt == datetime(1990, 1, 1, 6, 30, tzinfo=UTC)
