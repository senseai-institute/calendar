"""Database schema for all five phases.

Every table exists now so later phases only add logic, not migrations of shape.
Phase 1 populates: user, entity, chart (natal), event (technique=transit), feed_token.

Conventions:
- Primary keys are UUIDs (native `uuid` on Postgres, CHAR(32) on SQLite).
- Every row carries `owner_user_id` so row-level tenancy is a single WHERE clause
  (and a Postgres RLS policy later).
- Datetimes are tz-aware UTC (`UTCDateTime`). Longitudes are floats in [0, 360), never rounded.
- Enumerations are stored as plain strings; the `StrEnum`s below are the allowed values.
"""

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from skycal.db.types import JSONType, UTCDateTime


def utcnow() -> datetime:
    return datetime.now(UTC)


def _json(**kw) -> Any:
    return Field(default_factory=dict, sa_column=Column(JSONType, nullable=False), **kw)


def _ts(nullable: bool = False, index: bool = False, **kw) -> Any:
    return Field(sa_column=Column(UTCDateTime(), nullable=nullable, index=index), **kw)


# --------------------------------------------------------------------------- enums


class EntityKind(StrEnum):
    person = "person"
    pet = "pet"


class TimeKnown(StrEnum):
    """How sure we are of the birth time.

    `unknown` charts are cast at 12:00 local (noon minimises the worst-case Moon
    error to about ±6.5°) and have houses/ASC/MC suppressed, because those rotate
    through the whole zodiac every 24 hours.
    """

    exact = "exact"
    approx = "approx"
    unknown = "unknown"


class Visibility(StrEnum):
    private = "private"
    shared = "shared"
    public = "public"


class System(StrEnum):
    """Which zodiac the numbers are measured in.

    western = tropical zodiac (0° Aries = March equinox point), Placidus houses.
    vedic   = sidereal zodiac (0° Aries tied to the fixed stars via the Lahiri
              ayanamsa), whole-sign houses.
    """

    western = "western"
    vedic = "vedic"


class ChartKind(StrEnum):
    natal = "natal"
    solar_return = "solar_return"
    lunar_return = "lunar_return"
    progressed = "progressed"
    solar_arc = "solar_arc"
    synastry = "synastry"
    composite = "composite"


class Technique(StrEnum):
    transit = "transit"
    progression = "progression"
    solar_arc = "solar_arc"
    solar_return = "solar_return"
    lunar_return = "lunar_return"
    dasha = "dasha"
    eclipse = "eclipse"
    moon_phase = "moon_phase"
    retrograde = "retrograde"
    ingress = "ingress"
    void_of_course = "void_of_course"


# --------------------------------------------------------------------------- tables


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(index=True, unique=True)
    created_at: datetime = _ts(default_factory=utcnow)
    # {systems_on: [..], tiers_per_surface: {ics: 3, ...}, orbs_override: {...},
    #  planet_filters: [...], timezone: "America/New_York"}
    prefs: dict = _json()


class Entity(SQLModel, table=True):
    """A person or pet with a birth moment. The thing charts and events hang off."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    kind: str = Field(default=EntityKind.person)
    name: str
    species: str | None = None
    birth_dt_utc: datetime = _ts()
    birth_tz: str
    birth_lat: float
    birth_lon: float
    birth_place: str | None = None
    time_known: str = Field(default=TimeKnown.exact)
    visibility: str = Field(default=Visibility.private)
    created_at: datetime = _ts(default_factory=utcnow)


class Chart(SQLModel, table=True):
    """A computed chart snapshot (positions, houses, aspects) as JSON.

    `as_of` is the moment the chart is cast for: the birth moment for natal, the
    return moment for returns, the progressed date for progressions.
    """

    __table_args__ = (Index("ix_chart_entity_system_kind", "entity_id", "system", "kind"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    entity_id: uuid.UUID | None = Field(default=None, foreign_key="entity.id")
    relationship_id: uuid.UUID | None = Field(default=None, foreign_key="relationship.id")
    system: str
    kind: str = Field(default=ChartKind.natal)
    as_of: datetime = _ts()
    points: dict = _json()
    houses: dict = _json()
    aspects: list = Field(default_factory=list, sa_column=Column(JSONType, nullable=False))
    meta: dict = _json()
    created_at: datetime = _ts(default_factory=utcnow)


class Relationship(SQLModel, table=True):
    """Two entities considered together (synastry / composite charts). Phase 4."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    entity_a_id: uuid.UUID = Field(foreign_key="entity.id")
    entity_b_id: uuid.UUID = Field(foreign_key="entity.id")
    kind: str  # partner | family | friend | pet_owner | ...
    composite_chart_id: uuid.UUID | None = None
    created_at: datetime = _ts(default_factory=utcnow)


class Event(SQLModel, table=True):
    """One astrological influence as a time window: a fact, never an interpretation.

    start/end   when the influence is active (e.g. inside orb).
    exact       the moment it perfects (or closest approach if it never does).
    applying    True if, at computation time, the influence has not yet perfected.
    uid         deterministic key; stable across recomputes so calendar clients
                update an event rather than duplicating it.
    """

    __table_args__ = (
        Index("ix_event_entity_start_end_tier", "entity_id", "start", "end", "tier"),
        UniqueConstraint("uid", name="uq_event_uid"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    uid: str
    owner_user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    entity_id: uuid.UUID | None = Field(default=None, foreign_key="entity.id")
    relationship_id: uuid.UUID | None = Field(default=None, foreign_key="relationship.id")
    system: str
    technique: str
    transiting_point: str | None = None
    natal_point: str | None = None
    aspect: str | None = None
    start: datetime = _ts()
    exact: datetime | None = _ts(nullable=True)
    end: datetime = _ts()
    tier: int
    applying: bool | None = None
    rule_id: uuid.UUID | None = Field(default=None, foreign_key="rule.id")
    meta: dict = _json()
    created_at: datetime = _ts(default_factory=utcnow)


class Rule(SQLModel, table=True):
    """Phase 2: a pattern over events plus what it means (interpretation lives here only).

    owner_user_id NULL = built-in/global rule.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID | None = Field(default=None, foreign_key="user.id", index=True)
    name: str
    system: str | None = None
    technique: str | None = None
    # e.g. {"transiting_point": "Saturn", "aspect": ["square", "opposition"], "natal_point": "Sun"}
    match: dict = _json()
    weight: float = 0.0
    text: str = ""
    source: str | None = None
    visibility: str = Field(default=Visibility.private)
    created_at: datetime = _ts(default_factory=utcnow)


class RuleOverride(SQLModel, table=True):
    """Phase 2: per-user tweak of a rule (disable it, reweight it, rewrite its text)."""

    __table_args__ = (UniqueConstraint("owner_user_id", "rule_id"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    rule_id: uuid.UUID = Field(foreign_key="rule.id")
    enabled: bool = True
    weight: float | None = None
    text: str | None = None
    created_at: datetime = _ts(default_factory=utcnow)


class Brief(SQLModel, table=True):
    """Phase 2: generated natural-language summary for a period."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    entity_id: uuid.UUID = Field(foreign_key="entity.id", index=True)
    kind: str = "weekly"
    period_start: datetime = _ts()
    period_end: datetime = _ts()
    content: str = ""
    model: str | None = None
    meta: dict = _json()
    created_at: datetime = _ts(default_factory=utcnow)


class DayScore(SQLModel, table=True):
    """Phase 2: one aggregate number per entity per local day, with its components."""

    __table_args__ = (UniqueConstraint("entity_id", "day", "system"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    entity_id: uuid.UUID = Field(foreign_key="entity.id", index=True)
    day: date
    system: str
    score: float
    components: dict = _json()
    created_at: datetime = _ts(default_factory=utcnow)


class FeedToken(SQLModel, table=True):
    """Secret that authorises an ICS feed URL (calendar apps can't send auth headers)."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    entity_id: uuid.UUID = Field(foreign_key="entity.id", index=True)
    token: str = Field(index=True, unique=True)
    created_at: datetime = _ts(default_factory=utcnow)
    revoked_at: datetime | None = _ts(nullable=True)
