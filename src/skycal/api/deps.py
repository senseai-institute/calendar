"""Shared FastAPI dependencies."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlmodel import Session

from skycal.db.models import Entity, User
from skycal.db.session import get_or_create_default_user, get_session

SessionDep = Annotated[Session, Depends(get_session)]


def current_user(session: SessionDep) -> User:
    """Phase 1: the single configured user. Phase 4 replaces this with real auth."""
    return get_or_create_default_user(session)


UserDep = Annotated[User, Depends(current_user)]


def owned_entity(entity_id: uuid.UUID, session: SessionDep, user: UserDep) -> Entity:
    entity = session.get(Entity, entity_id)
    if entity is None or entity.owner_user_id != user.id:
        raise HTTPException(404, "entity not found")
    return entity


EntityDep = Annotated[Entity, Depends(owned_entity)]
