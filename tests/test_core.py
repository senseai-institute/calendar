from datetime import UTC, datetime

import pytest

from skycal.core import ephemeris as eph
from skycal.core.aspects import (
    Aspect,
    graha_aspects,
    natal_orb,
    transit_orb,
    transit_tier,
    western_natal_aspects,
    wrap180,
)
from skycal.core.ephemeris import Point
from skycal.core.houses import house_of, whole_sign_house
from skycal.core.zodiac import degree_in_sign, nakshatra_of, sign_of


def dms(d: int, m: int, s: float) -> float:
    return d + m / 60 + s / 3600


@pytest.mark.parametrize(
    ("when", "published"),
    [
        # Defining value of the Lahiri (Chitrapaksha) ayanamsa adopted by the Indian
        # Calendar Reform Committee: 23°15'00.658" at 1956-03-21 00:00 TT.
        (datetime(1956, 3, 21, 0, 0, tzinfo=UTC), dms(23, 15, 0.658)),
        # Widely tabulated value for 2000-01-01: 23°51'11".
        (datetime(2000, 1, 1, 12, 0, tzinfo=UTC), dms(23, 51, 11)),
    ],
)
def test_lahiri_ayanamsa_matches_published(when, published):
    assert eph.ayanamsa(eph.julian_day(when)) == pytest.approx(published, abs=0.01)


def test_sidereal_is_tropical_minus_ayanamsa():
    jd = eph.julian_day(datetime(2026, 10, 18, tzinfo=UTC))
    trop = eph.position(Point.MARS, jd).longitude
    sid = eph.position(Point.MARS, jd, sidereal=True).longitude
    assert wrap180(trop - sid - eph.ayanamsa(jd)) == pytest.approx(0, abs=1e-6)


def test_julian_day_roundtrip():
    dt = datetime(2026, 10, 18, 13, 37, 12, tzinfo=UTC)
    assert eph.julian_day(datetime(2000, 1, 1, 12, tzinfo=UTC)) == 2451545.0
    assert abs((eph.from_julian_day(eph.julian_day(dt)) - dt).total_seconds()) < 1e-3


def test_south_node_opposes_north_node():
    jd = 2461000.5
    nn = eph.position(Point.NORTH_NODE, jd).longitude
    sn = eph.position(Point.SOUTH_NODE, jd).longitude
    assert (sn - nn) % 360 == pytest.approx(180)


def test_chiron_available():
    assert 0 <= eph.position(Point.CHIRON, 2461000.5).longitude < 360


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        eph.julian_day(datetime(2026, 1, 1))


def test_zodiac_helpers():
    assert sign_of(245.5) == "Sagittarius"
    assert degree_in_sign(245.5) == pytest.approx(5.5)
    assert sign_of(359.999) == "Pisces"
    n = nakshatra_of(0.0)
    assert (n.name, n.pada, n.lord) == ("Ashwini", 1, "Ketu")
    n = nakshatra_of(359.9)
    assert (n.name, n.pada, n.lord) == ("Revati", 4, "Mercury")
    # Rohini spans 40°00'–53°20'; pada 2 starts at 43°20'.
    n = nakshatra_of(45.0)
    assert (n.name, n.pada, n.lord) == ("Rohini", 2, "Moon")


def test_house_of_wraps():
    cusps = [350, 20, 50, 80, 110, 140, 170, 200, 230, 260, 290, 320]
    assert house_of(355, cusps) == 1
    assert house_of(5, cusps) == 1
    assert house_of(21, cusps) == 2
    assert house_of(349, cusps) == 12
    assert whole_sign_house(95, asc=250) == 8  # Cancer is 8th sign from Sagittarius


def test_orbs():
    assert transit_orb(Aspect.CONJUNCTION, Point.PLUTO) == 3
    assert transit_orb(Aspect.SQUARE, Point.SUN) == 6
    assert transit_orb(Aspect.SEXTILE, Point.MARS) == 2
    assert natal_orb(Aspect.CONJUNCTION, Point.PLUTO, Point.SUN) == 8
    assert natal_orb(Aspect.TRINE, Point.SATURN, Point.VENUS) == 4
    assert natal_orb(Aspect.SEXTILE, Point.SATURN, Point.JUPITER) == 1


def test_tiers():
    assert transit_tier(Point.PLUTO, Point.SUN) == 1
    assert transit_tier(Point.PLUTO, Point.JUPITER) == 2
    assert transit_tier(Point.SATURN, Point.SUN) == 2
    assert transit_tier(Point.MARS, Point.MOON) == 3
    assert transit_tier(Point.MOON, Point.SUN) == 4


def test_western_natal_aspect_applying():
    # Mars at 88° moving faster than Sun at 0°: square forming (applying).
    asp = western_natal_aspects({Point.SUN: (0.0, 1.0), Point.MARS: (88.0, 0.7)})
    assert [(a.aspect, round(a.orb, 3), a.applying) for a in asp] == [("square", 2.0, False)]
    asp = western_natal_aspects({Point.SUN: (0.0, 0.5), Point.MARS: (88.0, 0.7)})
    assert asp[0].applying is True


def test_graha_drishti():
    # Saturn in Aries (5°) aspects Gemini (3rd), Libra (7th), Capricorn (10th).
    assert graha_aspects(5, Point.SATURN, 65) == [3]
    assert graha_aspects(5, Point.SATURN, 185) == [7]
    assert graha_aspects(5, Point.SATURN, 275) == [10]
    assert graha_aspects(5, Point.SATURN, 125) == []
    assert graha_aspects(5, Point.VENUS, 25) == [1]
