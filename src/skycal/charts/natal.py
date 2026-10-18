"""Cast a natal chart: where everything was at the birth moment, from the birth place.

natal chart
    A snapshot of the sky at birth: planet longitudes, the houses (local sky
    sectors), and the aspects between natal points. Transits are measured
    against it.

The same function produces both systems; only the zodiac (tropical/sidereal),
house system (Placidus/whole-sign), point set, and aspect model differ.
"""

from __future__ import annotations

from functools import lru_cache

from skycal.charts.models import (
    AspectData,
    BirthData,
    ChartData,
    HousesData,
    PointData,
)
from skycal.core import ephemeris as eph
from skycal.core.aspects import vedic_natal_aspects, western_natal_aspects
from skycal.core.ephemeris import Point
from skycal.core.houses import PLACIDUS, WHOLE_SIGN, compute_houses, house_of, whole_sign_house
from skycal.core.zodiac import degree_in_sign, nakshatra_of, sign_index, sign_of
from skycal.db.models import System, TimeKnown

WESTERN_BODIES: tuple[Point, ...] = (
    Point.SUN,
    Point.MOON,
    Point.MERCURY,
    Point.VENUS,
    Point.MARS,
    Point.JUPITER,
    Point.SATURN,
    Point.URANUS,
    Point.NEPTUNE,
    Point.PLUTO,
    Point.NORTH_NODE,
    Point.SOUTH_NODE,
    Point.CHIRON,
)
# The nine Vedic grahas: seven visible planets plus the two lunar nodes.
VEDIC_BODIES: tuple[Point, ...] = (
    Point.SUN,
    Point.MOON,
    Point.MERCURY,
    Point.VENUS,
    Point.MARS,
    Point.JUPITER,
    Point.SATURN,
    Point.NORTH_NODE,
    Point.SOUTH_NODE,
)


def bodies_for(system: System | str, include_lilith: bool = False) -> tuple[Point, ...]:
    if System(system) is System.vedic:
        return VEDIC_BODIES
    return WESTERN_BODIES + ((Point.LILITH,) if include_lilith else ())


def _point(
    name: Point, lon: float, lat: float, speed: float, house: int | None, vedic: bool
) -> PointData:
    data = PointData(
        name=name,
        longitude=lon,
        latitude=lat,
        speed=speed,
        retrograde=speed < 0,
        sign=sign_of(lon),
        sign_index=sign_index(lon),
        degree_in_sign=degree_in_sign(lon),
        house=house,
    )
    if vedic:
        n = nakshatra_of(lon)
        data.vedic_name = eph.VEDIC_NAMES.get(name)
        data.nakshatra = n.name
        data.nakshatra_index = n.index
        data.pada = n.pada
        data.nakshatra_lord = n.lord
    return data


def compute_natal(
    birth: BirthData, system: System | str, include_lilith: bool = False
) -> ChartData:
    return _compute_natal_cached(
        birth.dt_utc, birth.lat, birth.lon, birth.time_known, System(system), include_lilith
    ).model_copy(deep=True)


@lru_cache(maxsize=256)
def _compute_natal_cached(dt_utc, lat, lon, time_known, system: System, include_lilith: bool):
    vedic = system is System.vedic
    jd = eph.julian_day(dt_utc)
    houses_known = TimeKnown(time_known) is not TimeKnown.unknown

    hres, hsys, fell_back = compute_houses(
        jd, lat, lon, WHOLE_SIGN if vedic else PLACIDUS, sidereal=vedic
    )
    houses = None
    if houses_known:
        houses = HousesData(
            system=hsys.name,
            cusps=list(hres.cusps),
            ascendant=hres.asc,
            midheaven=hres.mc,
            ascendant_sign=sign_of(hres.asc),
            fallback=fell_back,
        )

    def house(lon_: float) -> int | None:
        if not houses_known:
            return None
        return whole_sign_house(lon_, hres.asc) if vedic else house_of(lon_, hres.cusps)

    points: dict[str, PointData] = {}
    for p in bodies_for(system, include_lilith):
        pos = eph.position(p, jd, sidereal=vedic)
        points[p] = _point(p, pos.longitude, pos.latitude, pos.speed, house(pos.longitude), vedic)

    if houses_known and not vedic:
        points[Point.ASC] = _point(Point.ASC, hres.asc, 0.0, hres.asc_speed, 1, False)
        points[Point.MC] = _point(Point.MC, hres.mc, 0.0, hres.mc_speed, 10, False)

    if vedic:
        raw = vedic_natal_aspects({Point(k): v.longitude for k, v in points.items()})
    else:
        raw = western_natal_aspects({Point(k): (v.longitude, v.speed) for k, v in points.items()})
    aspects = [
        AspectData(a=x.a, b=x.b, aspect=x.aspect, angle=x.angle, orb=x.orb, applying=x.applying)
        for x in raw
    ]

    meta: dict = {"time_known": time_known, "julian_day": jd, "zodiac": "tropical"}
    if vedic:
        meta |= {"zodiac": "sidereal", "ayanamsa": "lahiri", "ayanamsa_deg": eph.ayanamsa(jd)}
        if houses_known:
            meta["lagna"] = {"longitude": hres.asc, "sign": sign_of(hres.asc)}
    return ChartData(
        system=system,
        as_of=dt_utc,
        time_known=time_known,
        points=points,
        houses=houses,
        aspects=aspects,
        meta=meta,
    )
