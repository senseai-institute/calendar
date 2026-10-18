import secrets
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from skycal.api.deps import EntityDep, SessionDep, UserDep
from skycal.db.models import Entity, EntityKind, FeedToken, TimeKnown, Visibility
from skycal.db.session import get_engine
from skycal.jobs.recompute import default_window, recompute_entity, store_natal_charts
from skycal.settings import get_settings

router = APIRouter(prefix="/entities", tags=["entities"])


class EntityCreate(BaseModel):
    kind: EntityKind = EntityKind.person
    name: str
    species: str | None = None
    birth_date: date
    birth_time: time | None = Field(None, description="Local wall-clock time; omit if unknown")
    birth_tz: str = Field(..., examples=["Asia/Kolkata"])
    birth_lat: float = Field(..., ge=-90, le=90)
    birth_lon: float = Field(..., ge=-180, le=180, description="East positive")
    birth_place: str | None = None
    time_known: TimeKnown = TimeKnown.exact
    visibility: Visibility = Visibility.private

    @field_validator("birth_tz")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown IANA timezone {v!r}") from exc
        return v


class EntityOut(BaseModel):
    id: uuid.UUID
    kind: str
    name: str
    species: str | None
    birth_dt_utc: datetime
    birth_tz: str
    birth_lat: float
    birth_lon: float
    birth_place: str | None
    time_known: str
    visibility: str


class FeedTokenOut(BaseModel):
    token: str
    url: str


def birth_to_utc(d: date, t: time | None, tz: str, time_known: TimeKnown) -> tuple[datetime, str]:
    """Local birth date/time -> UTC. Unknown time is cast at 12:00 local.

    Wall-clock times in a DST "fall back" overlap resolve to the first
    occurrence (fold=0); times in a "spring forward" gap shift forward an hour.
    """
    if t is None or time_known == TimeKnown.unknown:
        t, time_known = time(12, 0), TimeKnown.unknown
    local = datetime.combine(d, t).replace(tzinfo=ZoneInfo(tz))
    return local.astimezone(UTC), time_known


def create_entity_row(session: Session, owner_id: uuid.UUID, body: EntityCreate) -> Entity:
    dt_utc, tk = birth_to_utc(body.birth_date, body.birth_time, body.birth_tz, body.time_known)
    entity = Entity(
        owner_user_id=owner_id,
        kind=body.kind,
        name=body.name,
        species=body.species,
        birth_dt_utc=dt_utc,
        birth_tz=body.birth_tz,
        birth_lat=body.birth_lat,
        birth_lon=body.birth_lon,
        birth_place=body.birth_place,
        time_known=tk,
        visibility=body.visibility,
    )
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity


def _compute_events(entity_id: uuid.UUID) -> None:
    with Session(get_engine()) as session:
        entity = session.get(Entity, entity_id)
        if entity is not None:
            recompute_entity(session, entity, *default_window())


@router.post("", response_model=EntityOut, status_code=201)
def create_entity(
    body: EntityCreate,
    session: SessionDep,
    user: UserDep,
    background: BackgroundTasks,
    compute_events: bool = True,
):
    """Create an entity; natal charts (both systems) are computed and stored
    immediately, transit events for the default window in the background."""
    entity = create_entity_row(session, user.id, body)
    store_natal_charts(session, entity, user)
    if compute_events:
        background.add_task(_compute_events, entity.id)
    return entity


@router.get("", response_model=list[EntityOut])
def list_entities(session: SessionDep, user: UserDep):
    return session.exec(select(Entity).where(Entity.owner_user_id == user.id)).all()


@router.get("/{entity_id}", response_model=EntityOut)
def get_entity(entity: EntityDep):
    return entity


@router.post("/{entity_id}/recompute")
def recompute(entity: EntityDep, session: SessionDep, days_ahead: int | None = None):
    start, end = default_window()
    if days_ahead is not None:
        if not 1 <= days_ahead <= 3660:
            raise HTTPException(422, "days_ahead must be 1..3660")
        end = start + timedelta(days=get_settings().recompute_days_behind + days_ahead)
    store_natal_charts(session, entity, None)
    n = recompute_entity(session, entity, start, end)
    return {"events": n, "from": start, "to": end}


def new_feed_token(session: Session, entity: Entity) -> FeedToken:
    tok = FeedToken(
        owner_user_id=entity.owner_user_id,
        entity_id=entity.id,
        token=secrets.token_urlsafe(32),
    )
    session.add(tok)
    session.commit()
    session.refresh(tok)
    return tok


def feed_url(tok: FeedToken) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/ics/{tok.entity_id}/{tok.token}.ics"


@router.post("/{entity_id}/feed-tokens", response_model=FeedTokenOut, status_code=201)
def create_feed_token(entity: EntityDep, session: SessionDep):
    """Mint a secret ICS URL. Anyone with the URL can read the feed; revoke to rotate."""
    tok = new_feed_token(session, entity)
    return FeedTokenOut(token=tok.token, url=feed_url(tok))


@router.delete("/{entity_id}/feed-tokens/{token}", status_code=204)
def revoke_feed_token(entity: EntityDep, token: str, session: SessionDep):
    tok = session.exec(
        select(FeedToken).where(FeedToken.entity_id == entity.id, FeedToken.token == token)
    ).first()
    if tok is None:
        raise HTTPException(404, "token not found")
    tok.revoked_at = datetime.now(UTC)
    session.add(tok)
    session.commit()
