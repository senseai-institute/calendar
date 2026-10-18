from datetime import UTC, datetime, timedelta

from icalendar import Calendar

ME = {
    "name": "Test Person",
    "birth_date": "1990-07-15",
    "birth_time": "14:30",
    "birth_tz": "America/New_York",
    "birth_lat": 40.7128,
    "birth_lon": -74.0060,
    "birth_place": "New York, USA",
}


def _create(client, **over):
    r = client.post("/entities", json={**ME, **over})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_entity_computes_both_charts_and_events(client):
    e = _create(client)
    assert e["birth_dt_utc"].startswith("1990-07-15T18:30:00")  # EDT = UTC-4

    w = client.get(f"/entities/{e['id']}/chart", params={"system": "western"}).json()
    sun = w["points"]["Sun"]
    assert (sun["sign"], sun["house"], sun["retrograde"]) == ("Cancer", 9, False)
    assert {"longitude", "degree_in_sign", "speed"} <= sun.keys()
    assert w["houses"]["system"] == "placidus"
    assert w["aspects"]

    v = client.get(f"/entities/{e['id']}/chart", params={"system": "vedic"}).json()
    moon = v["points"]["Moon"]
    assert (moon["nakshatra"], moon["pada"]) == ("Ashwini", 2)
    assert v["houses"]["system"] == "whole_sign"

    # background task computed events for the default window
    evs = client.get(f"/entities/{e['id']}/events").json()
    assert {x["system"] for x in evs} == {"western", "vedic"}
    tier3 = client.get(
        f"/entities/{e['id']}/events", params={"tier_max": 3, "system": "western"}
    ).json()
    assert tier3 and all(x["tier"] <= 3 and x["system"] == "western" for x in tier3)


def test_unknown_time_entity(client):
    e = _create(client, birth_time=None, time_known="unknown")
    assert e["time_known"] == "unknown"
    assert e["birth_dt_utc"].startswith("1990-07-15T16:00:00")  # cast at 12:00 local
    c = client.get(f"/entities/{e['id']}/chart").json()
    assert c["houses"] is None and "ASC" not in c["points"]
    evs = client.get(f"/entities/{e['id']}/events").json()
    assert evs and all(x["meta"]["time_known"] == "unknown" for x in evs)


def test_bad_timezone_rejected(client):
    assert client.post("/entities", json={**ME, "birth_tz": "Mars/Olympus"}).status_code == 422


def test_ics_feed(client):
    e = _create(client)
    tok = client.post(f"/entities/{e['id']}/feed-tokens").json()
    assert tok["url"] == f"https://example.test/ics/{e['id']}/{tok['token']}.ics"
    path = tok["url"].removeprefix("https://example.test")

    r = client.get(path)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    cal = Calendar.from_ical(r.content)  # round-trip validates the structure
    vevents = cal.walk("VEVENT")
    assert vevents
    tiers = {str(v["categories"].cats[0]) for v in vevents}
    assert "tier 4" not in tiers

    # stable UIDs across a recompute
    uids_before = {str(v["uid"]) for v in vevents}
    assert client.post(f"/entities/{e['id']}/recompute").status_code == 200
    uids_after = {
        str(v["uid"]) for v in Calendar.from_ical(client.get(path).content).walk("VEVENT")
    }
    assert uids_before == uids_after

    # wrong / revoked tokens
    assert client.get(f"/ics/{e['id']}/nope.ics").status_code == 404
    client.delete(f"/entities/{e['id']}/feed-tokens/{tok['token']}")
    assert client.get(path).status_code == 404


def test_stub_routes(client):
    assert client.get("/sky/events").status_code == 501
    assert client.get("/rules").status_code == 501


def test_events_window_filter(client):
    e = _create(client)
    now = datetime.now(UTC)
    evs = client.get(
        f"/entities/{e['id']}/events",
        params={"from": now.isoformat(), "to": (now + timedelta(days=7)).isoformat()},
    ).json()
    for x in evs:
        assert datetime.fromisoformat(x["end"]) >= now
        assert datetime.fromisoformat(x["start"]) <= now + timedelta(days=7)


def test_api_key_guard(client, monkeypatch):
    from skycal.settings import get_settings

    monkeypatch.setenv("API_KEY", "s3cret")
    get_settings.cache_clear()
    assert client.get("/entities").status_code == 401
    assert client.get("/entities", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/entities", headers={"X-API-Key": "s3cret"}).status_code == 200
    assert client.get("/health").status_code == 200
