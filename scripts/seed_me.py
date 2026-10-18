"""Create (or refresh) your own entity from ME_* variables in .env, compute it,
and print your private ICS subscription URL.

    uv run python scripts/seed_me.py            # idempotent
    uv run python scripts/seed_me.py --replace  # delete and recreate (new feed URL)
"""

import argparse
import os
import sys
from datetime import date, time

from dotenv import load_dotenv
from sqlmodel import Session, delete, select

from skycal.api.routes.entities import EntityCreate, create_entity_row, feed_url, new_feed_token
from skycal.db.models import Chart, Entity, Event, FeedToken
from skycal.db.session import get_engine, get_or_create_default_user, migrate
from skycal.jobs.recompute import default_window, recompute_entity, store_natal_charts


def env(name: str, required: bool = True) -> str | None:
    v = (os.environ.get(name) or "").strip().strip('"')
    if required and (not v or v.startswith(("YYYY", "HH", "Region/"))):
        sys.exit(f"{name} is not set in .env (see .env.example)")
    return v or None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replace", action="store_true", help="delete and recreate the entity")
    args = ap.parse_args()
    load_dotenv()
    time_known = env("ME_TIME_KNOWN", required=False) or "exact"
    t = env("ME_BIRTH_TIME", required=time_known != "unknown")
    body = EntityCreate(
        name=env("ME_NAME"),
        birth_date=date.fromisoformat(env("ME_BIRTH_DATE")),
        birth_time=time.fromisoformat(t) if t else None,
        birth_tz=env("ME_BIRTH_TZ"),
        birth_place=env("ME_BIRTH_PLACE", required=False),
        birth_lat=float(env("ME_BIRTH_LAT")),
        birth_lon=float(env("ME_BIRTH_LON")),
        time_known=time_known,
    )

    migrate()
    with Session(get_engine()) as session:
        user = get_or_create_default_user(session)
        if tz := env("ME_TIMEZONE", required=False):
            user.prefs = {**user.prefs, "timezone": tz}
            session.add(user)
            session.commit()

        entity = session.exec(
            select(Entity).where(Entity.owner_user_id == user.id, Entity.name == body.name)
        ).first()
        if entity and args.replace:
            for model in (Event, Chart, FeedToken):
                session.exec(delete(model).where(model.entity_id == entity.id))
            session.delete(entity)
            session.commit()
            entity = None
        if entity is None:
            entity = create_entity_row(session, user.id, body)
            print(f"created entity {entity.name} ({entity.id})")
        else:
            print(f"entity {entity.name} exists ({entity.id}); use --replace to recreate")

        store_natal_charts(session, entity, user)
        n = recompute_entity(session, entity, *default_window())
        print(f"computed {n} transit events (both systems, all tiers)")

        tok = session.exec(
            select(FeedToken).where(
                FeedToken.entity_id == entity.id,
                FeedToken.revoked_at == None,  # noqa: E711
            )
        ).first() or new_feed_token(session, entity)
        print("\nSubscribe in Google Calendar (Other calendars → + → From URL):")
        print(f"  {feed_url(tok)}")


if __name__ == "__main__":
    main()
