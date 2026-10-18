"""Houses: dividing the sky around the birth place into 12 sectors.

house
    Where signs are a division of the *ecliptic*, houses divide the local sky as
    seen from the birth place at the birth moment. House 1 starts at the
    ascendant (eastern horizon); houses count counter-clockwise. Since the
    horizon spins once a day, houses need an accurate birth time.
cusp
    The longitude where a house begins.
Placidus (Western default)
    Divides each quadrant by time: the cusps are where a degree has covered
    1/3 or 2/3 of its trip between horizon and meridian. Houses come out
    unequal in size, and it's undefined above the polar circles.
whole-sign (Vedic default)
    House 1 is the entire sign containing the ascendant, house 2 the next sign,
    and so on. Every house is exactly one sign.
"""

from dataclasses import dataclass

from skycal.core import ephemeris as eph
from skycal.core.zodiac import sign_index

POLAR_LATITUDE = 66.0  # Placidus breaks down beyond roughly ±66°


@dataclass(frozen=True, slots=True)
class HouseSystem:
    code: str  # Swiss Ephemeris one-letter code
    name: str


PLACIDUS = HouseSystem("P", "placidus")
WHOLE_SIGN = HouseSystem("W", "whole_sign")
PORPHYRY = HouseSystem("O", "porphyry")


def compute_houses(
    jd: float, lat: float, lon: float, system: HouseSystem, sidereal: bool
) -> tuple[eph.HouseResult, HouseSystem, bool]:
    """Return (result, system actually used, fell_back)."""
    if system is PLACIDUS and abs(lat) >= POLAR_LATITUDE:
        return eph.houses(jd, lat, lon, PORPHYRY.code, sidereal), PORPHYRY, True
    return eph.houses(jd, lat, lon, system.code, sidereal), system, False


def house_of(lon: float, cusps: tuple[float, ...] | list[float]) -> int:
    """Which house (1..12) a longitude falls in, given 12 cusp longitudes.

    House n runs from cusp n up to (not including) cusp n+1, going forward
    through the zodiac and wrapping at 360°.
    """
    lon %= 360.0
    for i in range(12):
        start, end = cusps[i], cusps[(i + 1) % 12]
        span = (end - start) % 360.0
        if (lon - start) % 360.0 < span:
            return i + 1
    return 12  # unreachable unless cusps are degenerate


def whole_sign_house(lon: float, asc: float) -> int:
    """Whole-sign house: count signs from the ascendant's sign (1-based)."""
    return (sign_index(lon) - sign_index(asc)) % 12 + 1
