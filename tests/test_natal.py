from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from skycal.charts.models import BirthData
from skycal.charts.natal import compute_natal

# A known chart: 1990-07-15 14:30 EDT, New York City.
LOCAL = datetime(1990, 7, 15, 14, 30, tzinfo=ZoneInfo("America/New_York"))
LAT, LON = 40.7128, -74.0060
BIRTH = BirthData(dt_utc=LOCAL.astimezone(UTC), lat=LAT, lon=LON)

KERYKEION_ATTRS = {
    "Sun": "sun",
    "Moon": "moon",
    "Mercury": "mercury",
    "Venus": "venus",
    "Mars": "mars",
    "Jupiter": "jupiter",
    "Saturn": "saturn",
    "Uranus": "uranus",
    "Neptune": "neptune",
    "Pluto": "pluto",
    "North Node": "true_north_lunar_node",
    "Chiron": "chiron",
    "ASC": "ascendant",
    "MC": "medium_coeli",
}
KERYKEION_HOUSES = [
    "first", "second", "third", "fourth", "fifth", "sixth",
    "seventh", "eighth", "ninth", "tenth", "eleventh", "twelfth",
]  # fmt: skip


def _kerykeion(**kw):
    kerykeion = pytest.importorskip("kerykeion")
    return kerykeion.AstrologicalSubjectFactory.from_birth_data(
        "test", 1990, 7, 15, 14, 30, lng=LON, lat=LAT, tz_str="America/New_York",
        online=False, active_points=[
            "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus",
            "Neptune", "Pluto", "True_North_Lunar_Node", "Chiron", "Ascendant", "Medium_Coeli",
        ], **kw,
    )  # fmt: skip


def _diff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def test_western_positions_match_kerykeion():
    ours = compute_natal(BIRTH, "western")
    ref = _kerykeion()
    for name, attr in KERYKEION_ATTRS.items():
        theirs = getattr(ref, attr).abs_pos
        assert _diff(ours.points[name].longitude, theirs) < 0.01, name
    for i, attr in enumerate(KERYKEION_HOUSES):
        theirs = getattr(ref, f"{attr}_house").abs_pos
        assert _diff(ours.houses.cusps[i], theirs) < 0.01, f"cusp {i + 1}"


def test_vedic_positions_match_kerykeion_lahiri():
    ours = compute_natal(BIRTH, "vedic")
    ref = _kerykeion(zodiac_type="Sidereal", sidereal_mode="LAHIRI")
    for name in ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "North Node"]:
        theirs = getattr(ref, KERYKEION_ATTRS[name]).abs_pos
        assert _diff(ours.points[name].longitude, theirs) < 0.01, name


def test_western_chart_shape():
    c = compute_natal(BIRTH, "western")
    assert c.houses.system == "placidus"
    sun = c.points["Sun"]
    assert (sun.sign, sun.house) == ("Cancer", 9)
    assert sun.degree_in_sign == pytest.approx(23.0045, abs=1e-3)
    assert c.points["ASC"].sign == "Scorpio"
    assert sun.nakshatra is None
    assert any(a.aspect == "conjunction" and {a.a, a.b} == {"Sun", "Jupiter"} for a in c.aspects)


def test_vedic_chart_shape():
    c = compute_natal(BIRTH, "vedic")
    assert set(c.points) == {
        "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "North Node", "South Node",
    }  # fmt: skip
    assert c.houses.system == "whole_sign"
    assert c.houses.cusps[0] % 30 == 0
    moon = c.points["Moon"]
    assert (moon.sign, moon.nakshatra, moon.pada, moon.nakshatra_lord) == (
        "Aries", "Ashwini", 2, "Ketu",
    )  # fmt: skip
    assert c.points["North Node"].vedic_name == "Rahu"
    assert c.meta["ayanamsa"] == "lahiri"
    assert all(a.orb is None for a in c.aspects)


def test_unknown_time_suppresses_houses():
    noon = datetime(1990, 7, 15, 12, 0, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
    b = BirthData(dt_utc=noon, lat=LAT, lon=LON, time_known="unknown")
    for system in ("western", "vedic"):
        c = compute_natal(b, system)
        assert c.houses is None
        assert "ASC" not in c.points and "MC" not in c.points
        assert all(p.house is None for p in c.points.values())
        assert c.meta["time_known"] == "unknown"
