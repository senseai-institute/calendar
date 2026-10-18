"""Compute and persist charts and events. Used by the API, the scheduler and scripts."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlmodel import Session, col, select

from skycal.charts.models import ChartData
from skycal.charts.natal import compute_natal
from skycal.core.ephemeris import Point
from skycal.db.models import Chart, ChartKind, Entity, Event, System, Technique, User
from skycal.settings import get_settings
from skycal.techniques.base import Window, birth_from_entity
from skycal.techniques.transits import TransitGenerator

log = logging.getLogger(__name__)


def systems_on(user: User | None) -> list[System]:
    raw = (user.prefs if user else {}).get("systems_on") or [s.value for s in System]
    return [System(s) for s in raw]


def store_natal_charts(session: Session, entity: Entity, user: User | None = None) -> list[Chart]:
    """(Re)compute and upsert the natal chart for every system. Both systems are
    always stored; `systems_on` only filters what surfaces show."""
    prefs = user.prefs if user else {}
    rows = []
    for system in System:
        data: ChartData = compute_natal(
            birth_from_entity(entity), system, include_lilith=bool(prefs.get("lilith"))
        )
        row = session.exec(
            select(Chart).where(
                Chart.entity_id == entity.id,
                Chart.system == system,
                Chart.kind == ChartKind.natal,
            )
        ).first() or Chart(
            owner_user_id=entity.owner_user_id,
            entity_id=entity.id,
            system=system,
            kind=ChartKind.natal,
            as_of=entity.birth_dt_utc,
        )
        dumped = data.model_dump(mode="json")
        row.as_of = entity.birth_dt_utc
        row.points = dumped["points"]
        row.houses = dumped["houses"] or {}
        row.aspects = dumped["aspects"]
        row.meta = dumped["meta"]
        session.add(row)
        rows.append(row)
    session.commit()
    return rows


def recompute_entity(
    session: Session,
    entity: Entity,
    start: datetime,
    end: datetime,
    *,
    transiting: Iterable[Point] | None = None,
    as_of: datetime | None = None,
) -> int:
    """Replace this entity's transit events overlapping [start, end]. Returns count."""
    user = session.get(User, entity.owner_user_id)
    gen = TransitGenerator(prefs=user.prefs if user else {}, as_of=as_of, transiting=transiting)
    window = Window(start, end)
    events: list[Event] = []
    for system in System:  # compute both; prefs decide what is shown
        events.extend(gen.generate(entity, system, window))

    stale = (
        delete(Event)
        .where(col(Event.entity_id) == entity.id)
        .where(col(Event.technique) == Technique.transit)
        .where(col(Event.end) >= start)
        .where(col(Event.start) <= end)
    )
    if transiting is not None:
        stale = stale.where(col(Event.transiting_point).in_([str(p) for p in transiting]))
    session.exec(stale)
    uids = [e.uid for e in events]
    for i in range(0, len(uids), 500):  # also clear same-uid rows outside the window
        session.exec(delete(Event).where(col(Event.uid).in_(uids[i : i + 500])))
    session.add_all(events)
    session.commit()
    return len(events)


def default_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    s = get_settings()
    now = now or datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=s.recompute_days_behind), today + timedelta(
        days=s.recompute_days_ahead
    )


def recompute_all(session: Session, now: datetime | None = None) -> dict[str, int]:
    """Nightly job body: refresh every entity's next ~90 days and re-render its feeds."""
    from skycal.adapters.ics import render_entity_feed

    start, end = default_window(now)
    counts: dict[str, int] = {}
    for entity in session.exec(select(Entity)).all():
        store_natal_charts(session, entity, session.get(User, entity.owner_user_id))
        counts[str(entity.id)] = recompute_entity(session, entity, start, end, as_of=now)
        render_entity_feed(session, entity)  # smoke-check the feed renders
        log.info("recomputed %s (%s): %d events", entity.name, entity.id, counts[str(entity.id)])
    return counts


def refresh_moon(session: Session, now: datetime | None = None) -> int:
    """Hourly job body: recompute Moon transits for the next 3 days (keeps the
    applying/separating flag of fast events current)."""
    now = now or datetime.now(UTC)
    total = 0
    for entity in session.exec(select(Entity)).all():
        total += recompute_entity(
            session,
            entity,
            now - timedelta(days=1),
            now + timedelta(days=3),
            transiting=[Point.MOON],
            as_of=now,
        )
    return total
