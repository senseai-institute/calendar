import uuid
from datetime import UTC, datetime, timedelta

import pytest

from skycal.core import ephemeris as eph
from skycal.core.aspects import wrap180
from skycal.core.ephemeris import Point
from skycal.db.models import Entity
from skycal.techniques.base import EventGenerator, Window
from skycal.techniques.transits import TransitGenerator, scan_transits


def utc(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


def close(a: datetime, b: datetime, minutes: float) -> bool:
    return abs((a - b).total_seconds()) <= minutes * 60


def test_saturn_square_sun_retrograde_loop():
    """Hand-verified window: transiting Saturn square a natal Sun at 0° Cancer.

    A square to 0° Cancer (90°) is Saturn at 0° Aries, so the exact moments are
    Saturn's published Aries ingresses, and the split is its retrograde station:
      2025-05-25 03:35 UTC  Saturn enters Aries          (pass 1, direct)
      2025-07-13 04:07 UTC  Saturn stations retrograde at 1°56' Aries (still in 2° orb)
      2025-09-01 08:06 UTC  Saturn retrogrades back into Pisces (pass 2)
      2026-02-14 00:11 UTC  Saturn re-enters Aries       (pass 3, after leaving orb)
    """
    hits = scan_transits(
        {Point.SUN: 90.0}, "western", utc(2025, 1, 1), utc(2026, 12, 31), transiting=[Point.SATURN]
    )
    assert [(h.aspect, h.target) for h in hits] == [("square", -90.0)] * 3
    h1, h2, h3 = hits
    assert close(h1.exact, utc(2025, 5, 25, 3, 35), 5)
    assert close(h2.exact, utc(2025, 9, 1, 8, 6), 5)
    assert close(h3.exact, utc(2026, 2, 14, 0, 11), 5)
    # passes 1 and 2 share one continuous in-orb window, split at the station
    assert h1.end == h2.start and close(h1.end, utc(2025, 7, 13, 4, 7), 30)
    assert [(h.pass_no, h.passes) for h in hits] == [(1, 2), (2, 2), (1, 1)]
    assert [h.retrograde_at_exact for h in hits] == [False, True, False]
    assert all(h.perfected for h in hits)
    # window edges are where Saturn is exactly 2° (outer-planet square orb) from 0° Aries
    for edge in (h1.start, h2.end, h3.start, h3.end):
        lon = eph.position(Point.SATURN, eph.julian_day(edge)).longitude
        assert abs(wrap180(lon)) == pytest.approx(2.0, abs=0.01)


def test_vedic_whole_sign_window_is_sign_stay():
    """Sidereal (Lahiri) Saturn entered Pisces 2025-03-29 21:44 IST = 16:14 UTC (Drik Panchang)."""
    natal = {Point.MOON: 345.0}  # 15° Pisces sidereal
    hits = scan_transits(
        natal, "vedic", utc(2025, 3, 1), utc(2025, 6, 1), transiting=[Point.SATURN]
    )
    conj = [h for h in hits if h.aspect == "conjunction"]
    assert len(conj) == 1
    assert close(conj[0].start, utc(2025, 3, 29, 16, 14), 30)
    lon = eph.position(Point.SATURN, eph.julian_day(conj[0].exact), sidereal=True).longitude
    if conj[0].perfected:
        assert lon == pytest.approx(345.0, abs=0.01)
    # Saturn's 3rd/7th/10th aspects from Pisces fall on Taurus/Virgo/Sagittarius, not Pisces
    assert {h.aspect for h in hits} == {"conjunction"}


def test_moon_transits_are_hourly_precise():
    hits = scan_transits(
        {Point.SUN: 100.0}, "western", utc(2026, 10, 1), utc(2026, 10, 20), transiting=[Point.MOON]
    )
    conj = [h for h in hits if h.aspect == "conjunction"]
    assert len(conj) == 1
    h = conj[0]
    # 8° luminary orb each side at ~12-15°/day: window roughly 1-1.4 days
    assert timedelta(hours=24) < h.end - h.start < timedelta(hours=34)
    lon = eph.position(Point.MOON, eph.julian_day(h.exact)).longitude
    assert lon == pytest.approx(100.0, abs=0.02)  # Moon moves ~0.01°/minute


def _entity() -> Entity:
    return Entity(
        id=uuid.UUID(int=1),
        owner_user_id=uuid.UUID(int=2),
        name="test",
        birth_dt_utc=utc(1990, 7, 15, 18, 30),
        birth_tz="America/New_York",
        birth_lat=40.7128,
        birth_lon=-74.0060,
    )


@pytest.mark.parametrize("system", ["western", "vedic"])
def test_generator_is_deterministic_across_windows(system):
    gen = TransitGenerator(as_of=utc(2026, 10, 18))
    assert isinstance(gen, EventGenerator)
    a = gen.generate(_entity(), system, Window(utc(2026, 10, 18), utc(2027, 1, 16)))
    b = gen.generate(_entity(), system, Window(utc(2026, 11, 1), utc(2027, 2, 1)))
    by_uid_a = {e.uid: e for e in a}
    assert len(by_uid_a) == len(a)  # uids unique
    shared = [e for e in b if e.uid in by_uid_a]
    assert len(shared) > 20
    for e in shared:
        o = by_uid_a[e.uid]
        assert (o.start, o.exact, o.end) == (e.start, e.exact, e.end)


def test_generator_fields():
    as_of = utc(2026, 10, 18)
    events = TransitGenerator(as_of=as_of).generate(
        _entity(), "western", Window(as_of, as_of + timedelta(days=90))
    )
    assert {e.tier for e in events} == {1, 2, 3, 4}
    for e in events:
        assert e.start <= e.exact <= e.end
        assert e.applying == (as_of < e.exact)
        assert e.natal_point != "South Node"
        assert e.meta["time_known"] == "exact"
        assert e.end >= as_of and e.start <= as_of + timedelta(days=90)
    # every transiting Moon event is tier 4
    assert all(e.tier == 4 for e in events if e.transiting_point == "Moon")
