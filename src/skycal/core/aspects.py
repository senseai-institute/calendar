"""Aspects (angular relationships between points), orbs, and event tiers.

aspect
    Two points are "in aspect" when the angle between their longitudes is close
    to one of a few special angles: conjunction 0°, sextile 60°, square 90°,
    trine 120°, opposition 180°.
orb
    How far from the exact angle still counts. Saturn at 92.5° from the natal Sun
    is a square "with a 2.5° orb". Bigger, brighter, or more personal points
    traditionally get wider orbs.
exact / perfection
    The moment the angle is exactly the aspect angle (orb 0).
applying vs separating
    Applying: the orb is shrinking, so the aspect is heading toward exact.
    Separating: exact has passed and the orb is growing.
graha drishti (Vedic "planetary sight")
    Vedic astrology doesn't use degree-based angles. A graha (planet) "aspects"
    whole signs counted from its own sign (its own sign = 1st). Everyone aspects
    the 7th sign; Mars, Jupiter and Saturn (and, by common practice, Rahu/Ketu)
    have extra special aspects. There are no orbs: a planet anywhere in the
    aspected sign is aspected.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from skycal.core.ephemeris import Point
from skycal.core.zodiac import sign_index


class Aspect(StrEnum):
    CONJUNCTION = "conjunction"
    SEXTILE = "sextile"
    SQUARE = "square"
    TRINE = "trine"
    OPPOSITION = "opposition"


ASPECT_ANGLES: dict[Aspect, float] = {
    Aspect.CONJUNCTION: 0.0,
    Aspect.SEXTILE: 60.0,
    Aspect.SQUARE: 90.0,
    Aspect.TRINE: 120.0,
    Aspect.OPPOSITION: 180.0,
}

ASPECT_GLYPHS: dict[str, str] = {
    Aspect.CONJUNCTION: "☌",
    Aspect.SEXTILE: "⚹",
    Aspect.SQUARE: "□",
    Aspect.TRINE: "△",
    Aspect.OPPOSITION: "☍",
}


class OrbClass(StrEnum):
    LUMINARY = "luminary"  # Sun, Moon
    INNER = "inner"  # Mercury, Venus, Mars (+ ASC/MC as natal targets)
    OUTER = "outer"  # Jupiter outward, nodes, Chiron, Lilith


# degrees, by aspect then orb class
ORBS: dict[Aspect, dict[OrbClass, float]] = {
    Aspect.CONJUNCTION: {OrbClass.LUMINARY: 8, OrbClass.INNER: 6, OrbClass.OUTER: 3},
    Aspect.OPPOSITION: {OrbClass.LUMINARY: 8, OrbClass.INNER: 6, OrbClass.OUTER: 3},
    Aspect.SQUARE: {OrbClass.LUMINARY: 6, OrbClass.INNER: 4, OrbClass.OUTER: 2},
    Aspect.TRINE: {OrbClass.LUMINARY: 6, OrbClass.INNER: 4, OrbClass.OUTER: 2},
    Aspect.SEXTILE: {OrbClass.LUMINARY: 3, OrbClass.INNER: 2, OrbClass.OUTER: 1},
}

LUMINARIES = frozenset({Point.SUN, Point.MOON})
INNER = frozenset({Point.MERCURY, Point.VENUS, Point.MARS, Point.ASC, Point.MC})
# "Personal points" in the tier table: the fast, individual parts of a chart.
PERSONAL_POINTS = frozenset(
    {Point.SUN, Point.MOON, Point.ASC, Point.MC, Point.MERCURY, Point.VENUS, Point.MARS}
)
TIER1_TRANSITERS = frozenset(
    {
        Point.URANUS,
        Point.NEPTUNE,
        Point.PLUTO,
        Point.NORTH_NODE,
        Point.SOUTH_NODE,
        Point.CHIRON,
    }
)


def orb_class(point: Point) -> OrbClass:
    if point in LUMINARIES:
        return OrbClass.LUMINARY
    if point in INNER:
        return OrbClass.INNER
    return OrbClass.OUTER


def transit_orb(aspect: Aspect, transiting: Point, overrides: dict | None = None) -> float:
    """Orb for a transit: keyed on the transiting body (see CLAUDE.md for why)."""
    cls = orb_class(transiting)
    if overrides and (v := overrides.get(aspect, {}).get(cls)) is not None:
        return float(v)
    return float(ORBS[aspect][cls])


def natal_orb(aspect: Aspect, a: Point, b: Point) -> float:
    """Orb between two natal points: the more generous class of the pair."""
    classes = {orb_class(a), orb_class(b)}
    for cls in (OrbClass.LUMINARY, OrbClass.INNER, OrbClass.OUTER):
        if cls in classes:
            return float(ORBS[aspect][cls])
    raise AssertionError


def wrap180(x: float) -> float:
    """Map an angle to (-180, 180]."""
    x = (x + 180.0) % 360.0 - 180.0
    return 180.0 if x == -180.0 else x


def aspect_targets(aspect: Aspect) -> tuple[float, ...]:
    """Signed angles (transiting − natal) at which an aspect is exact.

    Sextile/square/trine occur on both sides (e.g. +90° "waxing" and −90°
    "waning" squares); these are separate events that happen at different times.
    """
    a = ASPECT_ANGLES[aspect]
    return (a,) if a in (0.0, 180.0) else (a, -a)


# ----------------------------------------------------------------- Vedic drishti

# Which signs (counted from the graha's own sign, own = 1) each graha aspects.
DRISHTI: dict[Point, tuple[int, ...]] = {
    Point.SUN: (7,),
    Point.MOON: (7,),
    Point.MERCURY: (7,),
    Point.VENUS: (7,),
    Point.MARS: (4, 7, 8),
    Point.JUPITER: (5, 7, 9),
    Point.SATURN: (3, 7, 10),
    Point.NORTH_NODE: (5, 7, 9),
    Point.SOUTH_NODE: (5, 7, 9),
}

VEDIC_CONJUNCTION = 1  # "same sign": we treat it as the 1st-house relationship


def vedic_aspect_name(house: int) -> str:
    return "conjunction" if house == VEDIC_CONJUNCTION else f"drishti_{house}"


def vedic_aspect_houses(graha: Point) -> tuple[int, ...]:
    return (VEDIC_CONJUNCTION, *DRISHTI[graha])


def graha_aspects(from_lon: float, graha: Point, to_lon: float) -> list[int]:
    """Houses (1 = conjunction, 7 = 7th aspect, ...) by which `graha` at `from_lon`
    aspects a point at `to_lon` (sidereal longitudes)."""
    h = (sign_index(to_lon) - sign_index(from_lon)) % 12 + 1
    return [h] if h in vedic_aspect_houses(graha) else []


# ----------------------------------------------------------------- natal aspects


@dataclass(frozen=True, slots=True)
class NatalAspect:
    a: str
    b: str
    aspect: str
    angle: float  # exact angle of the aspect (0..180) or house count for Vedic
    orb: float | None  # actual deviation from exact (Western); None for Vedic
    applying: bool | None


def western_natal_aspects(points: dict[Point, tuple[float, float]]) -> list[NatalAspect]:
    """All Western aspects between natal points. `points`: {point: (lon, speed)}.

    Applying is judged from the instantaneous speeds: would the separation
    from exact shrink in the next moment?
    """
    out: list[NatalAspect] = []
    names = list(points)
    for i, pa in enumerate(names):
        for pb in names[i + 1 :]:
            if {pa, pb} == {Point.NORTH_NODE, Point.SOUTH_NODE}:
                continue  # always exactly opposite by definition
            (la, sa), (lb, sb) = points[pa], points[pb]
            sep = wrap180(la - lb)
            for aspect in Aspect:
                ang = ASPECT_ANGLES[aspect]
                for target in aspect_targets(aspect):
                    dev = wrap180(sep - target)
                    if abs(dev) <= natal_orb(aspect, pa, pb):
                        # d|dev|/dt = sign(dev) * (sa - sb)
                        rate = (sa - sb) * (1 if dev >= 0 else -1)
                        out.append(NatalAspect(pa, pb, aspect, ang, abs(dev), rate < 0))
    return out


def vedic_natal_aspects(points: dict[Point, float]) -> list[NatalAspect]:
    """All graha drishti between natal grahas. `points`: {graha: sidereal lon}.

    Drishti is directional (Mars aspecting Venus ≠ Venus aspecting Mars), so
    each ordered pair is checked. Conjunctions are reported once.
    """
    out: list[NatalAspect] = []
    names = list(points)
    for pa in names:
        for pb in names:
            if pa == pb or {pa, pb} == {Point.NORTH_NODE, Point.SOUTH_NODE}:
                continue
            for h in graha_aspects(points[pa], pa, points[pb]):
                if h == VEDIC_CONJUNCTION and names.index(pa) > names.index(pb):
                    continue
                out.append(NatalAspect(pa, pb, vedic_aspect_name(h), h, None, None))
    return out


# ----------------------------------------------------------------- tiers


def transit_tier(transiting: Point, natal: Point) -> int:
    """Importance tier of a transit (1 = rare and big, 4 = daily noise).

    1  Uranus/Neptune/Pluto/Nodes/Chiron to personal points (years-long, rare)
    2  Jupiter/Saturn transits; outer bodies to non-personal points
    3  Sun/Mercury/Venus/Mars transits (days to weeks)
    4  Moon transits (hours)
    """
    if transiting is Point.MOON:
        return 4
    if transiting in TIER1_TRANSITERS:
        return 1 if natal in PERSONAL_POINTS else 2
    if transiting in (Point.JUPITER, Point.SATURN, Point.LILITH):
        return 2
    return 3
