import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response
from sqlmodel import select

from skycal.adapters.ics import render_entity_feed
from skycal.api.deps import SessionDep
from skycal.db.models import Entity, FeedToken, System

router = APIRouter(tags=["ics"])


@router.get("/ics/{entity_id}/{token}.ics")
def ics_feed(
    entity_id: uuid.UUID,
    token: str,
    session: SessionDep,
    tier_max: Annotated[int | None, Query(ge=1, le=4)] = None,
    system: System | None = None,
):
    """Subscribable calendar feed. The token in the URL is the only credential."""
    rows = session.exec(
        select(FeedToken).where(FeedToken.entity_id == entity_id, FeedToken.revoked_at == None)  # noqa: E711
    ).all()
    if not any(secrets.compare_digest(r.token, token) for r in rows):
        raise HTTPException(404, "not found")
    entity = session.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(404, "not found")
    body = render_entity_feed(
        session, entity, tier_max=tier_max, systems=[system.value] if system else None
    )
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{entity_id}.ics"'},
    )
