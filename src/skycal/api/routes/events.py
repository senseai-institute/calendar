import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlmodel import col, select

from skycal.api.deps import EntityDep, SessionDep
from skycal.db.models import Event, System, Technique

router = APIRouter(prefix="/entities", tags=["events"])


class EventOut(BaseModel):
    id: uuid.UUID
    uid: str
    system: str
    technique: str
    transiting_point: str | None
    natal_point: str | None
    aspect: str | None
    start: datetime
    exact: datetime | None
    end: datetime
    tier: int
    applying: bool | None
    meta: dict


@router.get("/{entity_id}/events", response_model=list[EventOut])
def list_events(
    entity: EntityDep,
    session: SessionDep,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    tier_max: Annotated[int, Query(ge=1, le=4)] = 4,
    technique: Technique | None = None,
    system: System | None = None,
):
    """Events whose active window overlaps [from, to] (default: today .. +90 days)."""
    now = datetime.now(UTC)
    start = _aware(from_) if from_ else now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = _aware(to) if to else start + timedelta(days=90)
    q = (
        select(Event)
        .where(Event.entity_id == entity.id)
        .where(Event.end >= start)
        .where(Event.start <= end)
        .where(Event.tier <= tier_max)
    )
    if technique:
        q = q.where(Event.technique == technique)
    if system:
        q = q.where(Event.system == system)
    return session.exec(q.order_by(col(Event.start), col(Event.tier))).all()


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
