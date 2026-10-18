"""FastAPI application. Run: uv run uvicorn skycal.api.app:app"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlmodel import Session

from skycal.api.deps import require_api_key
from skycal.api.routes import charts, entities, events, ics, rules, sky
from skycal.db.session import get_engine, get_or_create_default_user, migrate
from skycal.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate()
    with Session(get_engine()) as session:
        get_or_create_default_user(session)
    scheduler = None
    if get_settings().scheduler_enabled:
        from skycal.jobs.scheduler import build_scheduler

        scheduler = build_scheduler()
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="calendar",
    summary="Personal astrological-weather engine. Events are facts; no interpretation.",
    version="0.1.0",
    lifespan=lifespan,
)
for r in (entities, charts, events, sky, rules):
    app.include_router(r.router, dependencies=[Depends(require_api_key)])
app.include_router(ics.router)  # authorised by the secret token in its URL


@app.get("/health")
def health():
    return {"ok": True}
