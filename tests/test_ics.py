import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from icalendar import Calendar

from skycal.adapters.ics import event_title, render_ics
from skycal.db.models import Event

NY = ZoneInfo("America/New_York")


def utc(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


def ev(tier, start, exact, end, **kw) -> Event:
    base = dict(
        uid=uuid.uuid4().hex,
        owner_user_id=uuid.uuid4(),
        entity_id=uuid.uuid4(),
        system="western",
        technique="transit",
        transiting_point="Saturn",
        natal_point="Sun",
        aspect="square",
        start=start,
        exact=exact,
        end=end,
        tier=tier,
        applying=True,
        meta={"perfected": True, "pass": 1, "passes": 1, "orb": 2.0, "as_of": "2026-10-18"},
        created_at=utc(2026, 10, 18),
    )
    base.update(kw)
    return Event(**base)


def test_title_format():
    e = ev(2, utc(2026, 10, 1), utc(2026, 11, 4, 15), utc(2026, 12, 1))
    assert event_title(e, NY) == "♄ Saturn □ natal Sun (exact Nov 4)"
    e.meta = {**e.meta, "pass": 2, "passes": 3}
    assert event_title(e, NY) == "♄ Saturn □ natal Sun (exact Nov 4, pass 2/3)"
    v = ev(
        1, utc(2026, 10, 1), utc(2026, 11, 4, 15), utc(2026, 12, 1),
        system="vedic", transiting_point="North Node", aspect="drishti_5", natal_point="Moon",
    )  # fmt: skip
    assert event_title(v, NY) == "☊ Rahu 5th-house aspect → natal Moon (Vedic, exact Nov 4)"
    e.meta = {**e.meta, "perfected": False, "passes": 1}
    assert event_title(e, NY) == "♄ Saturn □ natal Sun (closest Nov 4)"


def test_exact_date_uses_feed_timezone():
    # 02:30 UTC on Nov 5 is still Nov 4 in New York
    e = ev(3, utc(2026, 11, 3), utc(2026, 11, 5, 2, 30), utc(2026, 11, 6), transiting_point="Mars")
    assert event_title(e, NY).endswith("(exact Nov 4)")


def test_layout_by_tier_and_roundtrip():
    events = [
        ev(1, utc(2026, 10, 1, 12), utc(2026, 11, 4, 15), utc(2026, 12, 1, 12)),
        ev(3, utc(2026, 10, 20), utc(2026, 10, 22, 15), utc(2026, 10, 25), transiting_point="Mars"),
        ev(
            4,
            utc(2026, 10, 20, 3),
            utc(2026, 10, 20, 15),
            utc(2026, 10, 21, 4),
            transiting_point="Moon",
        ),  # fmt: skip
    ]
    body = render_ics(events, "America/New_York", "Sky weather · Test")
    cal = Calendar.from_ical(body)
    assert str(cal["x-wr-calname"]) == "Sky weather · Test"
    vevents = cal.walk("VEVENT")
    assert len(vevents) == 2  # tier 4 excluded by default
    long_, short = vevents
    # tier 1: multi-day all-day, DTEND exclusive
    assert long_["dtstart"].dt == date(2026, 10, 1)
    assert long_["dtend"].dt == date(2026, 12, 2)
    # tier 3: all-day on the exact date only
    assert short["dtstart"].dt == date(2026, 10, 22)
    assert short["dtend"].dt == date(2026, 10, 23)
    desc = str(long_["description"])
    assert "System: Western" in desc and "applying" in desc and "Exact:" in desc
    assert str(long_["uid"]).endswith("@skycal.calendar")
    # re-serialising the parsed calendar gives the same bytes (valid, lossless)
    assert Calendar.from_ical(cal.to_ical()).to_ical() == cal.to_ical()

    with_moon = Calendar.from_ical(render_ics(events, "America/New_York", "x", tier_max=4))
    moon = [v for v in with_moon.walk("VEVENT") if "Moon" in str(v["summary"])][0]
    assert moon["dtstart"].dt == utc(2026, 10, 20, 3)  # timed


def test_uid_stable_across_renders():
    events = [ev(2, utc(2026, 10, 1), utc(2026, 11, 4), utc(2026, 12, 1))]
    a = Calendar.from_ical(render_ics(events, "UTC", "x")).walk("VEVENT")[0]["uid"]
    b = Calendar.from_ical(render_ics(events, "UTC", "x")).walk("VEVENT")[0]["uid"]
    assert a == b == f"{events[0].uid}@skycal.calendar"
