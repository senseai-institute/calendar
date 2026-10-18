"""Column types that behave the same on SQLite (Phase 1) and Postgres (later)."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator

# JSON on SQLite, JSONB on Postgres.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class UTCDateTime(TypeDecorator):
    """A timezone-aware UTC datetime.

    SQLite has no timezone support and hands back naive datetimes; this decorator
    rejects naive input on the way in and re-attaches UTC on the way out, so the
    rest of the code can rely on every datetime being tz-aware UTC.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(f"naive datetime not allowed in storage: {value!r}")
        value = value.astimezone(UTC)
        # SQLite stores the string; strip tz so comparisons stay lexicographic-correct.
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
