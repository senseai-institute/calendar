"""The single interface every technique implements.

technique
    A method of deriving time-bound influences from a chart: transits (today's
    sky vs. the natal chart), progressions, returns, dashas, etc. Each produces
    `Event` rows; downstream code (ICS, rules, briefs) never cares which.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from skycal.charts.models import BirthData
from skycal.db.models import Entity, Event, System, Technique


@dataclass(frozen=True, slots=True)
class Window:
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Window datetimes must be tz-aware")
        if self.end <= self.start:
            raise ValueError("Window end must be after start")


@runtime_checkable
class EventGenerator(Protocol):
    technique: Technique

    def generate(self, entity: Entity, system: System, window: Window) -> list[Event]:
        """Return every event of this technique overlapping `window` (not yet persisted)."""
        ...


def birth_from_entity(entity: Entity) -> BirthData:
    dt = entity.birth_dt_utc
    if dt.tzinfo is None:  # defensive: objects not round-tripped through the DB
        dt = dt.replace(tzinfo=UTC)
    return BirthData(
        dt_utc=dt, lat=entity.birth_lat, lon=entity.birth_lon, time_known=entity.time_known
    )


def stable_uid(*parts: object) -> str:
    """Deterministic event id: same inputs → same uid on every recompute."""
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


class NotYetImplemented(EventGenerator):
    """Base for Phase-3 stubs so they already satisfy the protocol."""

    technique: Technique

    def generate(self, entity: Entity, system: System, window: Window) -> list[Event]:
        raise NotImplementedError(f"{self.technique} arrives in Phase 3")
