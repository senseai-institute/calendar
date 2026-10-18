"""Transits: where the planets are *now*, measured against the natal chart.

transit
    A currently moving ("transiting") body forming an aspect to a fixed natal
    point, e.g. "transiting Saturn square natal Sun". Slow planets make long,
    rare transits (Pluto: years), fast ones short, frequent ones (Moon: hours).
retrograde loop
    Near a retrograde *station* (where speed passes through zero) a planet can
    cross the same degree three times: direct, back retrograde, direct again.
    Each crossing is a separate "pass" and becomes its own event.

Algorithm (one code path for both systems)
------------------------------------------
For each (transiting point T, natal point N, aspect target) we define:

* an *active* predicate. Western: |s(t)| <= orb. Vedic: T is in the sign that
  casts this drishti onto N's sign.
* a *signed offset* s(t) = wrap180(lon_T(t) - lon_N - target), which is 0 at
  exact. For Vedic, target = -(h-1)*30° for the h-th house aspect ("degree for
  degree" perfection).

1. Sample on a grid anchored to whole UTC days (hours for the Moon), so repeat
   scans are bit-identical, and find runs of consecutive active samples.
2. Runs touching the scan edge are extended outward until they end, so a
   multi-year Pluto window always gets its true start/end.
3. start/end: bisect the active predicate between the last inactive and first
   active sample, to one minute.
4. exact: bisect each sign change of s(t) inside the run. With k > 1 crossings
   (retrograde loop), split the run at the max-|s| turning points into k events.
   With 0 crossings (the planet turned around inside orb), exact is the moment
   of closest approach and `perfected=False`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from skycal.charts.natal import bodies_for, compute_natal
from skycal.core import ephemeris as eph
from skycal.core.aspects import (
    Aspect,
    aspect_targets,
    transit_orb,
    transit_tier,
    vedic_aspect_houses,
    vedic_aspect_name,
    wrap180,
)
from skycal.core.ephemeris import Point
from skycal.core.zodiac import sign_index
from skycal.db.models import Entity, Event, System, Technique
from skycal.techniques.base import Window, birth_from_entity, stable_uid

MINUTE = 1.0 / 1440.0  # in days
HOURLY = 1.0 / 24.0
MAX_EXTENSION_DAYS = 3650  # safety cap when chasing a long window outward

TRANSITING_WESTERN: tuple[Point, ...] = (
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
    Point.CHIRON,
)


def step_for(point: Point) -> float:
    """Grid step in days. Must be shorter than the briefest possible window.

    The shortest daily-stepped window is a Mercury sextile: 2*2° orb at
    ≤2.2°/day ≈ 1.8 days. The Moon (≈13°/day) needs hourly steps.
    """
    return HOURLY if point is Point.MOON else 1.0


@dataclass(slots=True)
class TransitHit:
    """One transit event before it becomes a DB row."""

    transiting: Point
    natal: Point
    aspect: str
    target: float  # signed angle (Western) or aspect house number (Vedic)
    start: datetime
    exact: datetime
    end: datetime
    perfected: bool
    pass_no: int = 1
    passes: int = 1
    orb: float | None = None  # configured orb (Western)
    offset_at_exact: float = 0.0  # |s| at exact, 0 if perfected
    transiting_lon_at_exact: float = 0.0
    retrograde_at_exact: bool = False
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _Series:
    """A condition to scan: is_active(jd) and signed offset s(jd)."""

    transiting: Point
    natal: Point
    aspect: str
    target: float
    active: Callable[[float], bool]
    offset: Callable[[float], float]
    step: float
    orb: float | None
    extra: dict


# --------------------------------------------------------------------- numerics


def _to_dt(jd: float) -> datetime:
    """JD -> UTC datetime rounded to the minute (our stated precision)."""
    dt = eph.from_julian_day(jd)
    return (dt + timedelta(seconds=30)).replace(second=0, microsecond=0)


def _bisect_predicate(f: Callable[[float], bool], lo: float, hi: float) -> float:
    """f(lo) != f(hi); find the switch point to within a minute."""
    flo = f(lo)
    while hi - lo > MINUTE / 4:
        mid = (lo + hi) / 2
        if f(mid) == flo:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _bisect_zero(s: Callable[[float], float], lo: float, hi: float) -> float:
    slo = s(lo)
    while hi - lo > MINUTE / 4:
        mid = (lo + hi) / 2
        if (s(mid) >= 0) == (slo >= 0):
            lo, slo = mid, s(mid)
        else:
            hi = mid
    return (lo + hi) / 2


def _golden(g: Callable[[float], float], lo: float, hi: float) -> float:
    """Minimise a unimodal g on [lo, hi] to within a minute."""
    invphi = (math.sqrt(5) - 1) / 2
    a, b = lo, hi
    c, d = b - invphi * (b - a), a + invphi * (b - a)
    gc, gd = g(c), g(d)
    while b - a > MINUTE / 4:
        if gc < gd:
            b, d, gd = d, c, gc
            c = b - invphi * (b - a)
            gc = g(c)
        else:
            a, c, gc = c, d, gd
            d = a + invphi * (b - a)
            gd = g(d)
    return (a + b) / 2


def _refine_extremum(g: Callable[[float], float], grid: list[float], i: int) -> float:
    lo = grid[max(i - 1, 0)]
    hi = grid[min(i + 1, len(grid) - 1)]
    return _golden(g, lo, hi) if hi > lo else grid[i]


# --------------------------------------------------------------------- scanning


def _runs(series: _Series, jd_start: float, jd_end: float) -> list[tuple[int, int]]:
    """Index runs [k_first, k_last] of active grid samples, extended past the range."""
    step = series.step
    k0 = math.floor((jd_start - eph.JD_UNIX_EPOCH) / step)
    k1 = math.ceil((jd_end - eph.JD_UNIX_EPOCH) / step)

    def jd(k: int) -> float:
        return eph.JD_UNIX_EPOCH + k * step

    cap = int(MAX_EXTENSION_DAYS / step)
    runs: list[tuple[int, int]] = []
    k = k0
    while k <= k1:
        if not series.active(jd(k)):
            k += 1
            continue
        first = k
        if k == k0:  # started before the range: walk back
            while first > k0 - cap and series.active(jd(first - 1)):
                first -= 1
        last = k
        while series.active(jd(last + 1)):
            last += 1
            if last > k1 + cap:
                break
        runs.append((first, last))
        k = last + 1
    return runs


def _hits_for_run(series: _Series, first: int, last: int) -> list[TransitHit]:
    step = series.step
    s, active = series.offset, series.active
    grid_jd = [eph.JD_UNIX_EPOCH + k * step for k in range(first, last + 1)]

    start = _bisect_predicate(active, grid_jd[0] - step, grid_jd[0])
    end = _bisect_predicate(active, grid_jd[-1], grid_jd[-1] + step)
    pts = [start, *grid_jd, end]
    vals = [s(t) for t in pts]

    # zero crossings of the signed offset = exact perfections
    exacts: list[float] = []
    for i in range(len(pts) - 1):
        a, b = vals[i], vals[i + 1]
        if a == 0:
            exacts.append(pts[i])
        elif (a > 0) != (b > 0) and b != 0 and abs(a - b) < 180:
            exacts.append(_bisect_zero(s, pts[i], pts[i + 1]))
    if vals[-1] == 0:
        exacts.append(pts[-1])

    def absval(t: float) -> float:
        return abs(s(t))

    if not exacts:
        i = min(range(len(pts)), key=lambda j: abs(vals[j]))
        exact = _refine_extremum(absval, pts, i)
        segments = [(start, exact, end, False)]
    else:
        # split between consecutive perfections at the turning point (max |s|)
        bounds = [start]
        for e1, e2 in zip(exacts, exacts[1:], strict=False):
            inner = [j for j, t in enumerate(pts) if e1 < t < e2]
            if inner:
                j = max(inner, key=lambda j: abs(vals[j]))
                split = _refine_extremum(lambda t: -absval(t), pts, j)
            else:
                split = (e1 + e2) / 2
            bounds.append(split)
        bounds.append(end)
        segments = [(bounds[i], e, bounds[i + 1], True) for i, e in enumerate(exacts)]

    hits = []
    for n, (a, e, b, perfected) in enumerate(segments, start=1):
        pos = eph.position(series.transiting, e, sidereal=series.extra.get("sidereal", False))
        hits.append(
            TransitHit(
                transiting=series.transiting,
                natal=series.natal,
                aspect=series.aspect,
                target=series.target,
                start=_to_dt(a),
                exact=_to_dt(e),
                end=_to_dt(b),
                perfected=perfected,
                pass_no=n,
                passes=len(segments),
                orb=series.orb,
                offset_at_exact=0.0 if perfected else abs(s(e)),
                transiting_lon_at_exact=pos.longitude,
                retrograde_at_exact=pos.retrograde,
                extra={k: v for k, v in series.extra.items() if k != "sidereal"},
            )
        )
    return hits


def _western_series(
    natal: dict[Point, float], transiting: Iterable[Point], orbs_override: dict | None
) -> Iterable[_Series]:
    for t in transiting:
        lon_t = _lon_fn(t, sidereal=False)
        for n, lon_n in natal.items():
            for aspect in Aspect:
                orb = transit_orb(aspect, t, orbs_override)
                for target in aspect_targets(aspect):

                    def offset(jd, lon_n=lon_n, target=target, lon_t=lon_t):
                        return wrap180(lon_t(jd) - lon_n - target)

                    def active(jd, offset=offset, orb=orb):
                        return abs(offset(jd)) <= orb

                    yield _Series(
                        t, n, aspect, target, active, offset, step_for(t), orb, {"sidereal": False}
                    )


def _vedic_series(natal: dict[Point, float], transiting: Iterable[Point]) -> Iterable[_Series]:
    for t in transiting:
        lon_t = _lon_fn(t, sidereal=True)
        for n, lon_n in natal.items():
            for h in vedic_aspect_houses(t):
                # T aspects the h-th sign from itself, so T must sit h-1 signs behind N.
                needed_sign = (sign_index(lon_n) - (h - 1)) % 12
                shift = (h - 1) * 30.0

                def offset(jd, lon_n=lon_n, shift=shift, lon_t=lon_t):
                    return wrap180(lon_t(jd) - lon_n + shift)

                def active(jd, needed_sign=needed_sign, lon_t=lon_t):
                    return sign_index(lon_t(jd)) == needed_sign

                yield _Series(
                    t,
                    n,
                    vedic_aspect_name(h),
                    float(h),
                    active,
                    offset,
                    step_for(t),
                    None,
                    {"sidereal": True, "transit_sign_index": needed_sign},
                )


def _lon_fn(point: Point, sidereal: bool) -> Callable[[float], float]:
    def lon(jd: float) -> float:
        return eph.position(point, jd, sidereal).longitude

    return lon


def scan_transits(
    natal: dict[Point, float],
    system: System | str,
    start: datetime,
    end: datetime,
    transiting: Iterable[Point] | None = None,
    orbs_override: dict | None = None,
) -> list[TransitHit]:
    """Every transit window overlapping [start, end] against fixed natal longitudes.

    `natal` longitudes must be in the system's zodiac (tropical for Western,
    sidereal for Vedic). Pure function: no DB, easy to test.
    """
    system = System(system)
    if transiting is None:
        transiting = TRANSITING_WESTERN if system is System.western else bodies_for(system)
    transiting = tuple(transiting)
    jd0, jd1 = eph.julian_day(start), eph.julian_day(end)
    if system is System.western:
        series_iter = _western_series(natal, transiting, orbs_override)
    else:
        series_iter = _vedic_series(natal, transiting)

    hits: list[TransitHit] = []
    for series in series_iter:
        for first, last in _runs(series, jd0, jd1):
            for hit in _hits_for_run(series, first, last):
                if hit.end >= start and hit.start <= end:
                    hits.append(hit)
    hits.sort(key=lambda h: (h.start, h.transiting, h.natal))
    return hits


# --------------------------------------------------------------------- generator


class TransitGenerator:
    """`EventGenerator` for transits."""

    technique = Technique.transit

    def __init__(
        self,
        prefs: dict | None = None,
        as_of: datetime | None = None,
        transiting: Iterable[Point] | None = None,
    ):
        self.prefs = prefs or {}
        self.as_of = as_of
        self.transiting = tuple(transiting) if transiting else None

    def natal_targets(self, entity: Entity, system: System) -> dict[Point, float]:
        chart = compute_natal(
            birth_from_entity(entity), system, include_lilith=bool(self.prefs.get("lilith"))
        )
        targets = {Point(k): p.longitude for k, p in chart.points.items()}
        if system is System.western:
            targets.pop(Point.SOUTH_NODE, None)  # same fact as an aspect to the North Node
        return targets

    def generate(self, entity: Entity, system: System, window: Window) -> list[Event]:
        system = System(system)
        as_of = self.as_of or datetime.now(UTC)
        transiting = self.transiting
        if transiting is None and system is System.western and self.prefs.get("lilith"):
            transiting = (*TRANSITING_WESTERN, Point.LILITH)
        natal = self.natal_targets(entity, system)
        hits = scan_transits(
            natal,
            system,
            window.start,
            window.end,
            transiting=transiting,
            orbs_override=self.prefs.get("orbs_override") or None,
        )
        return [self._to_event(entity, system, h, natal, as_of) for h in hits]

    @staticmethod
    def _to_event(
        entity: Entity, system: System, h: TransitHit, natal: dict[Point, float], as_of: datetime
    ) -> Event:
        meta = {
            "zodiac": "sidereal" if system is System.vedic else "tropical",
            "target": h.target,
            "perfected": h.perfected,
            "pass": h.pass_no,
            "passes": h.passes,
            "orb": h.orb,
            "offset_at_exact": h.offset_at_exact,
            "transiting_lon_at_exact": h.transiting_lon_at_exact,
            "natal_lon": natal[h.natal],
            "retrograde_at_exact": h.retrograde_at_exact,
            "time_known": entity.time_known,
            "as_of": as_of.isoformat(),
            **h.extra,
        }
        uid = stable_uid(
            entity.id,
            system,
            Technique.transit,
            h.transiting,
            h.natal,
            h.aspect,
            h.target,
            h.exact.date().isoformat(),
        )
        return Event(
            uid=uid,
            owner_user_id=entity.owner_user_id,
            entity_id=entity.id,
            system=system,
            technique=Technique.transit,
            transiting_point=h.transiting,
            natal_point=h.natal,
            aspect=h.aspect,
            start=h.start,
            exact=h.exact,
            end=h.end,
            tier=transit_tier(h.transiting, h.natal),
            applying=as_of < h.exact,
            meta=meta,
        )
