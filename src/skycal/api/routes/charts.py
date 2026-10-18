from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import select

from skycal.api.deps import EntityDep, SessionDep
from skycal.charts.models import AspectData, HousesData, PointData
from skycal.db.models import Chart, ChartKind, System
from skycal.jobs.recompute import store_natal_charts

router = APIRouter(prefix="/entities", tags=["charts"])


class ChartOut(BaseModel):
    entity_id: str
    system: System
    kind: str
    as_of: datetime
    time_known: str
    points: dict[str, PointData]
    houses: HousesData | None
    aspects: list[AspectData]
    meta: dict


@router.get("/{entity_id}/chart", response_model=ChartOut)
def get_chart(entity: EntityDep, session: SessionDep, system: System = System.western):
    """Natal chart. Each point has longitude, sign, degree-in-sign, house, speed and
    retrograde flag; Vedic points add nakshatra, pada and nakshatra lord."""

    def load():
        return session.exec(
            select(Chart).where(
                Chart.entity_id == entity.id,
                Chart.system == system,
                Chart.kind == ChartKind.natal,
            )
        ).first()

    chart = load()
    if chart is None:
        store_natal_charts(session, entity)
        chart = load()
    return ChartOut(
        entity_id=str(entity.id),
        system=system,
        kind=chart.kind,
        as_of=chart.as_of,
        time_known=chart.meta.get("time_known", entity.time_known),
        points=chart.points,
        houses=chart.houses or None,
        aspects=chart.aspects,
        meta=chart.meta,
    )
