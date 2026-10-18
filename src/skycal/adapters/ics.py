"""Render events as an iCalendar (ICS) feed for Google/Apple Calendar subscriptions.

Layout rules:
- tier 1–2: multi-day all-day event spanning the whole active window
- tier 3:   all-day event on the exact date only
- tier 4:   excluded by default; if requested, a timed event over its window
UIDs come from `event.uid`, which is stable across recomputes, so a
subscribed calendar updates entries in place rather than duplicating them.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar
from icalendar import Event as VEvent
from sqlmodel import Session, col, select

from skycal.core.aspects import ASPECT_GLYPHS
from skycal.core.ephemeris import GLYPHS, VEDIC_NAMES, Point
from skycal.db.models import Entity, Event, System, User

PRODID = "-//senseai//calendar skycal//EN"
UID_DOMAIN = "skycal.calendar"


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _point_label(name: str | None, system: str) -> str:
    if name is None:
        return ""
    try:
        p = Point(name)
    except ValueError:
        return name
    if system == System.vedic and p in (Point.NORTH_NODE, Point.SOUTH_NODE):
        return VEDIC_NAMES[p]
    return str(p)


def _aspect_label(aspect: str | None) -> str:
    if aspect is None:
        return ""
    if aspect in ASPECT_GLYPHS:
        return ASPECT_GLYPHS[aspect]
    if aspect.startswith("drishti_"):
        return f"{_ordinal(int(aspect.removeprefix('drishti_')))}-house aspect →"
    return aspect


def _fmt_day(dt: datetime, today: date | None = None) -> str:
    """ "Nov 4"; with the year when it isn't the current one ("Jun 9 2025")."""
    today = today or datetime.now(dt.tzinfo).date()
    return f"{dt:%b} {dt.day}" + ("" if dt.year == today.year else f" {dt.year}")


def _aspect_words(aspect: str | None) -> str:
    if aspect and aspect.startswith("drishti_"):
        return f"{_ordinal(int(aspect.removeprefix('drishti_')))}-house aspect (graha drishti)"
    return aspect or ""


def event_title(ev: Event, tz: ZoneInfo, today: date | None = None) -> str:
    """e.g. "♄ Saturn □ natal Sun (exact Nov 4)"."""
    t = _point_label(ev.transiting_point, ev.system)
    glyph = GLYPHS.get(Point(ev.transiting_point), "") if ev.transiting_point else ""
    n = _point_label(ev.natal_point, ev.system)
    when = ev.exact or ev.start
    label = "exact" if ev.meta.get("perfected", True) else "closest"
    paren = [f"{label} {_fmt_day(when.astimezone(tz), today)}"]
    if ev.meta.get("passes", 1) > 1:
        paren.append(f"pass {ev.meta['pass']}/{ev.meta['passes']}")
    if ev.system == System.vedic:
        paren.insert(0, "Vedic")
    return f"{glyph} {t} {_aspect_label(ev.aspect)} natal {n} ({', '.join(paren)})".strip()


def event_description(ev: Event, tz: ZoneInfo) -> str:
    def full(dt: datetime) -> str:
        return dt.astimezone(tz).strftime("%a %b %-d %Y %H:%M %Z")

    system = (
        "Vedic (sidereal, Lahiri ayanamsa, whole-sign houses)"
        if ev.system == System.vedic
        else "Western (tropical, Placidus houses)"
    )
    lines = [
        f"Technique: {ev.technique}",
        f"System: {system}",
        f"Transiting {_point_label(ev.transiting_point, ev.system)} {_aspect_words(ev.aspect)} "
        f"natal {_point_label(ev.natal_point, ev.system)}",
        f"Tier: {ev.tier}",
        f"Starts: {full(ev.start)}",
    ]
    if ev.exact:
        word = "Exact" if ev.meta.get("perfected", True) else "Closest approach (never exact)"
        retro = " (transiting planet retrograde)" if ev.meta.get("retrograde_at_exact") else ""
        lines.append(f"{word}: {full(ev.exact)}{retro}")
    lines.append(f"Ends: {full(ev.end)}")
    if ev.applying is not None:
        as_of = ev.meta.get("as_of", "")[:10]
        lines.append(f"Status: {'applying' if ev.applying else 'separating'} (as of {as_of})")
    if ev.meta.get("orb") is not None:
        lines.append(f"Orb: {ev.meta['orb']:g}°")
    if ev.meta.get("passes", 1) > 1:
        lines.append(f"Pass {ev.meta['pass']} of {ev.meta['passes']} (retrograde loop)")
    if ev.meta.get("time_known") and ev.meta["time_known"] != "exact":
        lines.append(f"Birth time: {ev.meta['time_known']}")
    return "\n".join(lines)


def render_ics(
    events: Iterable[Event],
    tz_name: str,
    calendar_name: str,
    tier_max: int = 3,
) -> bytes:
    tz = ZoneInfo(tz_name)
    cal = Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", calendar_name)
    cal.add("x-wr-timezone", tz_name)
    # How often clients should re-poll (Google mostly ignores this and polls ~daily).
    cal.add("x-published-ttl", "PT6H")
    cal.add("refresh-interval", timedelta(hours=6), parameters={"VALUE": "DURATION"})

    for ev in sorted(events, key=lambda e: (e.start, e.uid)):
        if ev.tier > tier_max:
            continue
        v = VEvent()
        v.add("uid", f"{ev.uid}@{UID_DOMAIN}")
        v.add("summary", event_title(ev, tz))
        v.add("description", event_description(ev, tz))
        stamp = ev.created_at or datetime.now(UTC)
        v.add("dtstamp", stamp)
        v.add("last-modified", stamp)
        v.add("transp", "TRANSPARENT")  # never blocks free/busy
        v.add("categories", [f"tier {ev.tier}", ev.system, ev.technique])
        if ev.tier <= 2:
            v.add("dtstart", ev.start.astimezone(tz).date())
            v.add("dtend", ev.end.astimezone(tz).date() + timedelta(days=1))
        elif ev.tier == 3:
            d: date = (ev.exact or ev.start).astimezone(tz).date()
            v.add("dtstart", d)
            v.add("dtend", d + timedelta(days=1))
        else:
            v.add("dtstart", ev.start.astimezone(UTC))
            v.add("dtend", ev.end.astimezone(UTC))
        cal.add_component(v)
    return cal.to_ical()


def feed_events(
    session: Session,
    entity: Entity,
    tier_max: int,
    systems: Iterable[str],
    now: datetime | None = None,
) -> list[Event]:
    now = now or datetime.now(UTC)
    return list(
        session.exec(
            select(Event)
            .where(Event.entity_id == entity.id)
            .where(Event.tier <= tier_max)
            .where(col(Event.system).in_(list(systems)))
            .where(Event.end >= now - timedelta(days=30))
            .where(Event.start <= now + timedelta(days=400))
        ).all()
    )


def render_entity_feed(
    session: Session,
    entity: Entity,
    tier_max: int | None = None,
    systems: Iterable[str] | None = None,
) -> bytes:
    user = session.get(User, entity.owner_user_id)
    prefs = user.prefs if user else {}
    if tier_max is None:
        tier_max = int(prefs.get("tiers_per_surface", {}).get("ics", 3))
    if systems is None:
        systems = prefs.get("systems_on") or [s.value for s in System]
    tz = prefs.get("timezone") or entity.birth_tz
    events = feed_events(session, entity, tier_max, systems)
    return render_ics(events, tz, f"Sky weather · {entity.name}", tier_max=tier_max)
