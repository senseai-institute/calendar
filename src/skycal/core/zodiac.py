"""Signs and nakshatras: turning a longitude into named segments.

zodiac sign
    The ecliptic is cut into 12 equal 30° *signs* starting at 0° Aries. A planet
    at 245.5° is at 5.5° Sagittarius (sign index 8, degree-in-sign 5.5).
tropical vs sidereal
    Same 12 signs, different starting point. Tropical (Western) starts at the
    March equinox; sidereal (Vedic) starts ~24° later, tied to the stars. See
    `ephemeris.ayanamsa`.
nakshatra
    Vedic "lunar mansion": the sidereal ecliptic cut into 27 equal segments of
    13°20' (360/27), roughly the distance the Moon travels in one day. Each is
    split into 4 *padas* (quarters) of 3°20'. Each nakshatra has a ruling planet
    ("lord"), cycling Ketu, Venus, Sun, Moon, Mars, Rahu, Jupiter, Saturn,
    Mercury; this sequence also drives Vimshottari dashas (Phase 3).
"""

from dataclasses import dataclass

SIGNS: tuple[str, ...] = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)

SIGN_GLYPHS: tuple[str, ...] = (
    "♈",
    "♉",
    "♊",
    "♋",
    "♌",
    "♍",
    "♎",
    "♏",
    "♐",
    "♑",
    "♒",
    "♓",
)

NAKSHATRAS: tuple[str, ...] = (
    "Ashwini",
    "Bharani",
    "Krittika",
    "Rohini",
    "Mrigashira",
    "Ardra",
    "Punarvasu",
    "Pushya",
    "Ashlesha",
    "Magha",
    "Purva Phalguni",
    "Uttara Phalguni",
    "Hasta",
    "Chitra",
    "Swati",
    "Vishakha",
    "Anuradha",
    "Jyeshtha",
    "Mula",
    "Purva Ashadha",
    "Uttara Ashadha",
    "Shravana",
    "Dhanishta",
    "Shatabhisha",
    "Purva Bhadrapada",
    "Uttara Bhadrapada",
    "Revati",
)

NAKSHATRA_LORDS: tuple[str, ...] = (
    "Ketu",
    "Venus",
    "Sun",
    "Moon",
    "Mars",
    "Rahu",
    "Jupiter",
    "Saturn",
    "Mercury",
)

NAKSHATRA_SPAN = 360.0 / 27  # 13°20'
PADA_SPAN = NAKSHATRA_SPAN / 4  # 3°20'


def normalize(lon: float) -> float:
    return lon % 360.0


def sign_index(lon: float) -> int:
    return int(normalize(lon) // 30) % 12


def sign_of(lon: float) -> str:
    return SIGNS[sign_index(lon)]


def degree_in_sign(lon: float) -> float:
    return normalize(lon) % 30.0


@dataclass(frozen=True, slots=True)
class Nakshatra:
    index: int  # 0..26
    name: str
    pada: int  # 1..4
    lord: str


def nakshatra_of(sidereal_lon: float) -> Nakshatra:
    """Nakshatra + pada of a *sidereal* longitude."""
    lon = normalize(sidereal_lon)
    idx = int(lon // NAKSHATRA_SPAN) % 27
    pada = int((lon - idx * NAKSHATRA_SPAN) // PADA_SPAN) + 1
    return Nakshatra(idx, NAKSHATRAS[idx], min(pada, 4), NAKSHATRA_LORDS[idx % 9])


def format_dms(lon: float) -> str:
    """245.5 -> "5°30' Sagittarius" (display only)."""
    d = degree_in_sign(lon)
    deg = int(d)
    minutes = int(round((d - deg) * 60))
    if minutes == 60:
        deg, minutes = deg + 1, 0
    return f"{deg}°{minutes:02d}' {sign_of(lon)}"
