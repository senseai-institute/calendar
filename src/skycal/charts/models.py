"""Pydantic shapes of a computed chart (also what lands in `chart.points/houses/aspects`)."""

from datetime import datetime

from pydantic import BaseModel


class BirthData(BaseModel):
    """The minimum needed to cast a chart. `dt_utc` is already resolved from local time."""

    dt_utc: datetime
    lat: float
    lon: float
    time_known: str = "exact"


class PointData(BaseModel):
    name: str
    longitude: float  # [0, 360) in the chart's zodiac (tropical or sidereal)
    latitude: float
    speed: float  # degrees/day
    retrograde: bool
    sign: str
    sign_index: int  # 0 = Aries
    degree_in_sign: float
    house: int | None = None  # None when birth time is unknown
    # Vedic only
    vedic_name: str | None = None
    nakshatra: str | None = None
    nakshatra_index: int | None = None
    pada: int | None = None
    nakshatra_lord: str | None = None


class HousesData(BaseModel):
    system: str  # placidus | whole_sign | porphyry
    cusps: list[float]  # 12 longitudes, house 1..12
    ascendant: float
    midheaven: float
    ascendant_sign: str
    fallback: bool = False  # True if Placidus was impossible (polar latitude)


class AspectData(BaseModel):
    a: str
    b: str
    aspect: str  # conjunction|sextile|square|trine|opposition, or Vedic conjunction|drishti_N
    angle: float
    orb: float | None = None  # deviation from exact (Western)
    applying: bool | None = None


class ChartData(BaseModel):
    system: str
    kind: str = "natal"
    as_of: datetime
    time_known: str
    points: dict[str, PointData]
    houses: HousesData | None
    aspects: list[AspectData]
    meta: dict = {}
