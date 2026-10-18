"""Sky-wide events (moon phases, ingresses, stations, eclipses, void-of-course). Phase 3."""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/sky", tags=["sky"])


@router.get("/events")
def sky_events():
    raise HTTPException(501, "sky events arrive in Phase 3")
