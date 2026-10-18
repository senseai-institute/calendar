"""Thin, cached wrapper around the Swiss Ephemeris (`pyswisseph`).

Everything astronomical goes through here. Callers deal in tz-aware UTC
`datetime`s or Julian days and in our `Point` names; nobody else imports `swisseph`.

Glossary
--------
ephemeris
    A table (here, a numerical model) giving where each body is at a given time.
    We use geocentric *apparent* positions: as seen from Earth's centre, corrected
    for light-time and aberration, which is what astrology has always used.
ecliptic longitude
    Angle in degrees [0, 360) along the ecliptic (the Sun's apparent yearly path),
    measured from the zodiac's 0° Aries. Every "position" in this codebase is one.
speed
    Rate of change of longitude, degrees/day. Negative = *retrograde*: the planet
    appears to move backwards against the stars because Earth is overtaking it
    (or it is overtaking Earth). The Sun and Moon never go retrograde; the lunar
    nodes almost always are.
Julian day (JD)
    A continuous day count used by astronomers (JD 2451545.0 = 2000-01-01 12:00 TT).
    We use the UT flavour (`*_ut` functions), which is tied to civil time.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import lru_cache

import swisseph as swe

from skycal.settings import get_settings


class EphemerisFilesMissing(RuntimeError):
    pass


class Point(StrEnum):
    """Every chart point we know about.

    Planets are physical bodies. The rest are calculated points:

    NORTH_NODE / SOUTH_NODE
        Where the Moon's orbit crosses the ecliptic going north / south. Eclipses
        happen near them. We use the *true* (osculating) node, which wobbles,
        rather than the smoothed *mean* node. In Vedic astrology these are
        Rahu (north) and Ketu (south).
    CHIRON
        A small body orbiting between Saturn and Uranus (period ≈ 50 years).
    LILITH
        "Black Moon Lilith": the lunar apogee, the point of the Moon's orbit
        farthest from Earth (mean version). Optional.
    ASC (ascendant)
        The zodiac degree rising on the eastern horizon at the birth place and
        moment. Changes by ~1° every 4 minutes, so it needs an exact birth time.
    MC (midheaven, medium coeli)
        The zodiac degree culminating on the local meridian (highest point).
    """

    SUN = "Sun"
    MOON = "Moon"
    MERCURY = "Mercury"
    VENUS = "Venus"
    MARS = "Mars"
    JUPITER = "Jupiter"
    SATURN = "Saturn"
    URANUS = "Uranus"
    NEPTUNE = "Neptune"
    PLUTO = "Pluto"
    NORTH_NODE = "North Node"
    SOUTH_NODE = "South Node"
    CHIRON = "Chiron"
    LILITH = "Lilith"
    ASC = "ASC"
    MC = "MC"


GLYPHS: dict[Point, str] = {
    Point.SUN: "☉",
    Point.MOON: "☽",
    Point.MERCURY: "☿",
    Point.VENUS: "♀",
    Point.MARS: "♂",
    Point.JUPITER: "♃",
    Point.SATURN: "♄",
    Point.URANUS: "♅",
    Point.NEPTUNE: "♆",
    Point.PLUTO: "♇",
    Point.NORTH_NODE: "☊",
    Point.SOUTH_NODE: "☋",
    Point.CHIRON: "⚷",
    Point.LILITH: "⚸",
    Point.ASC: "AC",
    Point.MC: "MC",
}

# Vedic names for the same bodies (grahas). Used only for display.
VEDIC_NAMES: dict[Point, str] = {
    Point.SUN: "Surya",
    Point.MOON: "Chandra",
    Point.MERCURY: "Budha",
    Point.VENUS: "Shukra",
    Point.MARS: "Mangala",
    Point.JUPITER: "Guru",
    Point.SATURN: "Shani",
    Point.NORTH_NODE: "Rahu",
    Point.SOUTH_NODE: "Ketu",
}

_SWE_IDS: dict[Point, int] = {
    Point.SUN: swe.SUN,
    Point.MOON: swe.MOON,
    Point.MERCURY: swe.MERCURY,
    Point.VENUS: swe.VENUS,
    Point.MARS: swe.MARS,
    Point.JUPITER: swe.JUPITER,
    Point.SATURN: swe.SATURN,
    Point.URANUS: swe.URANUS,
    Point.NEPTUNE: swe.NEPTUNE,
    Point.PLUTO: swe.PLUTO,
    Point.NORTH_NODE: swe.TRUE_NODE,
    Point.CHIRON: swe.CHIRON,
    Point.LILITH: swe.MEAN_APOG,
}

BODIES: tuple[Point, ...] = tuple(_SWE_IDS) + (Point.SOUTH_NODE,)


@dataclass(frozen=True, slots=True)
class Position:
    longitude: float  # degrees [0, 360)
    latitude: float  # ecliptic latitude, degrees
    speed: float  # degrees/day; negative = retrograde

    @property
    def retrograde(self) -> bool:
        return self.speed < 0


# ---------------------------------------------------------------- setup & time

# The Swiss Ephemeris C library keeps its configuration (ephemeris path,
# sidereal mode) in *thread-local* globals, so each thread must initialise it.
# FastAPI's threadpool, background tasks and APScheduler all call in from
# different threads. Calls are also serialised under a lock, because the
# library's file handles and caches were not designed for concurrent use.
_thread_state = threading.local()
_LOCK = threading.RLock()


def _ensure_init() -> None:
    path = os.path.abspath(get_settings().skycal_ephe_path)
    if getattr(_thread_state, "path", None) == path:
        return
    with _LOCK:
        swe.set_ephe_path(path)
        # Lahiri (a.k.a. Chitrapaksha) ayanamsa, the Indian government standard.
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        _thread_state.path = path


JD_UNIX_EPOCH = 2440587.5  # JD (UT) of 1970-01-01 00:00 UTC


def julian_day(dt: datetime) -> float:
    """UT Julian day of a tz-aware datetime."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime; pass a tz-aware UTC datetime")
    return JD_UNIX_EPOCH + dt.timestamp() / 86400.0


def from_julian_day(jd: float) -> datetime:
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(days=jd - JD_UNIX_EPOCH)


# ---------------------------------------------------------------- positions


def _flags(sidereal: bool) -> int:
    f = swe.FLG_SWIEPH | swe.FLG_SPEED
    return f | swe.FLG_SIDEREAL if sidereal else f


@lru_cache(maxsize=500_000)
def position(point: Point, jd: float, sidereal: bool = False) -> Position:
    """Geocentric apparent ecliptic position of a body at UT Julian day `jd`.

    `sidereal=True` returns Lahiri-sidereal longitude (tropical − ayanamsa).
    Cached: the transit scanner asks for the same (body, jd) many times.
    """
    _ensure_init()
    if point is Point.SOUTH_NODE:
        nn = position(Point.NORTH_NODE, jd, sidereal)
        return Position((nn.longitude + 180.0) % 360.0, -nn.latitude, nn.speed)
    try:
        swe_id = _SWE_IDS[point]
    except KeyError:
        raise ValueError(f"{point} is not a body; use houses() for ASC/MC") from None
    try:
        with _LOCK:
            values, retflag = swe.calc_ut(jd, swe_id, _flags(sidereal))
    except swe.Error as exc:  # e.g. seas_18.se1 missing for Chiron
        raise EphemerisFilesMissing(
            f"{exc}. Run `uv run python scripts/fetch_ephemeris.py`."
        ) from exc
    if swe_id not in (swe.TRUE_NODE, swe.MEAN_APOG) and not retflag & swe.FLG_SWIEPH:
        raise EphemerisFilesMissing(
            f"{point} @ {jd}: retflag={retflag}. "
            f"Swiss Ephemeris files not found in {get_settings().skycal_ephe_path!r} "
            "(fell back to Moshier). Run `uv run python scripts/fetch_ephemeris.py`."
        )
    lon, lat, _dist, speed = values[0], values[1], values[2], values[3]
    return Position(lon % 360.0, lat, speed)


def ayanamsa(jd: float) -> float:
    """Lahiri ayanamsa in degrees at `jd`.

    The *ayanamsa* is the angle between the tropical zodiac's 0° Aries (the March
    equinox, which drifts westward ~1° per 72 years because Earth's axis
    precesses) and the sidereal zodiac's 0° Aries (anchored to the stars; for
    Lahiri, so that the star Spica sits at 180°). sidereal = tropical − ayanamsa.
    About 24.2° in 2026.

    This is the *true* ayanamsa (includes nutation, the small ±0.005° wobble of
    Earth's axis), i.e. exactly the offset between our apparent tropical and
    sidereal longitudes. It is also the convention of the published Lahiri
    tables (23°15'00.658" on 1956-03-21, 23°51'11" on 2000-01-01).
    """
    with _LOCK:
        _ensure_init()
        _flag, value = swe.get_ayanamsa_ex_ut(jd, swe.FLG_SWIEPH)
    return value


@dataclass(frozen=True, slots=True)
class HouseResult:
    system: str  # one-letter Swiss Ephemeris code actually used
    cusps: tuple[float, ...]  # 12 longitudes, cusp of house 1..12
    asc: float
    mc: float
    asc_speed: float
    mc_speed: float


@lru_cache(maxsize=4096)
def houses(jd: float, lat: float, lon: float, hsys: str, sidereal: bool) -> HouseResult:
    """House cusps plus ASC/MC.

    `hsys`: 'P' Placidus (Western), 'W' whole-sign (Vedic), 'O' Porphyry (fallback).
    """
    flags = swe.FLG_SIDEREAL if sidereal else 0
    with _LOCK:
        _ensure_init()
        cusps, ascmc, _cusp_speeds, ascmc_speeds = swe.houses_ex2(
            jd, lat, lon, hsys.encode(), flags
        )
    return HouseResult(
        system=hsys,
        cusps=tuple(c % 360.0 for c in cusps[:12]),
        asc=ascmc[0] % 360.0,
        mc=ascmc[1] % 360.0,
        asc_speed=ascmc_speeds[0],
        mc_speed=ascmc_speeds[1],
    )
