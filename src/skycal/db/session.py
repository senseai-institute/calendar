"""Engine/session helpers and schema bootstrap via Alembic."""

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, select

from skycal.db.models import User
from skycal.settings import REPO_ROOT, get_settings


@lru_cache
def get_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        db_path = url.removeprefix("sqlite:///")
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def migrate(url: str | None = None) -> None:
    """Bring the database to the latest Alembic revision."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url or get_settings().database_url)
    command.upgrade(cfg, "head")


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def get_or_create_default_user(session: Session) -> User:
    """Phase 1 has no auth: everything belongs to one configured user."""
    s = get_settings()
    user = session.exec(select(User).where(User.email == s.default_user_email)).first()
    if user is None:
        user = User(
            email=s.default_user_email,
            prefs={
                "systems_on": ["western", "vedic"],
                "tiers_per_surface": {"ics": 3},
                "orbs_override": {},
                "planet_filters": [],
                "timezone": s.app_timezone,
            },
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
