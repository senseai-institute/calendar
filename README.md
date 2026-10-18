# calendar

A personal astrological-weather engine. It computes every active transit to your
natal chart in both Western (tropical, Placidus) and Vedic (sidereal Lahiri,
whole-sign) astrology, stores each as a time-windowed event, and serves them as a
calendar feed you can subscribe to in Google Calendar.

Events are facts (what, when, how exact). There's no interpretation text.

## Run locally (5 commands)

```bash
uv sync                                    # Python 3.12 env + deps
uv run python scripts/fetch_ephemeris.py   # Swiss Ephemeris data (~2 MB) -> data/ephe
cp .env.example .env                       # then fill in the ME_* lines with your birth data
uv run python scripts/seed_me.py           # creates you, computes charts + 90 days of events, prints your feed URL
uv run uvicorn skycal.api.app:app          # API on http://localhost:8000 (docs at /docs)
```

Tests: `uv run pytest`. Lint: `uv run ruff check . && uv run ruff format --check .`

`ME_BIRTH_LAT`/`ME_BIRTH_LON` are decimal degrees, north and east positive
(New York is `40.7128`, `-74.0060`). If you don't know your birth time, set
`ME_TIME_KNOWN=unknown` and leave `ME_BIRTH_TIME` empty. The chart is then cast
at 12:00 local, and houses/ASC/MC are left out.

## Subscribe in Google Calendar

Google fetches the feed from its own servers, so a `localhost` URL won't work.
The feed has to be reachable from the internet. Either deploy it (below) or
expose your local server with a tunnel such as `cloudflared tunnel --url http://localhost:8000`.
Then set `PUBLIC_BASE_URL` to that address and re-run `seed_me.py` to print the
right URL.

1. Copy the feed URL that `seed_me.py` prints:
   `https://<host>/ics/<entity-id>/<secret-token>.ics`
2. Open Google Calendar on the web. In the left sidebar, next to **Other
   calendars**, click **+** and choose **From URL**.
3. Paste the URL and click **Add calendar**. It appears as "Sky weather · <name>".

On the feed:
- Tier 1–2 transits (outer planets to personal points, Jupiter/Saturn) show as
  multi-day all-day events spanning their whole active window. Tier 3
  (Sun/Mercury/Venus/Mars) shows as a single all-day event on the exact date.
  Moon transits (tier 4) are left out; add `?tier_max=4` to include them, or
  `?system=western` / `?system=vedic` to show one system.
- Titles look like `♄ Saturn □ natal Sun (exact Nov 4)`. The description has
  the system, dates, and applying/separating status.
- Google re-polls subscribed calendars on its own schedule, usually every
  8–24 hours, and you can't force it. Event UIDs are stable, so refreshed
  events update in place rather than duplicating.
- The token in the URL is the only credential. To rotate it, call
  `DELETE /entities/{id}/feed-tokens/{token}`, then `POST /entities/{id}/feed-tokens`.

## API

| Method | Path | |
|---|---|---|
| POST | `/entities` | create a person/pet; natal charts computed immediately, events in the background |
| GET | `/entities/{id}/chart?system=western\|vedic` | points (longitude, sign, degree, house, speed, retrograde; Vedic adds nakshatra/pada), houses, natal aspects |
| GET | `/entities/{id}/events?from&to&tier_max&technique&system` | stored events overlapping the range |
| POST | `/entities/{id}/recompute` | recompute now |
| POST | `/entities/{id}/feed-tokens` | mint an ICS URL |
| GET | `/ics/{entity_id}/{token}.ics` | the calendar feed |

If `API_KEY` is set, every route except `/health` and the ICS feed needs the
header `X-API-Key: <API_KEY>`. Set it on any public deployment.

A background scheduler recomputes the next 90 days for every entity at 02:00
`APP_TIMEZONE`, and refreshes Moon transits hourly. To run the nightly job by
hand: `uv run python scripts/recompute_now.py`.

## Deploy to Fly.io

```bash
fly launch --no-deploy --copy-config --name <your-app>    # keeps fly.toml; pick a region
fly volumes create calendar_data --size 1
fly secrets set API_KEY=$(openssl rand -hex 24) PUBLIC_BASE_URL=https://<your-app>.fly.dev
fly deploy
fly ssh console -C "python scripts/seed_me.py"   # after `fly secrets set ME_NAME=... ME_BIRTH_DATE=...` etc.
```

The app runs as one always-on machine with SQLite on the volume, because the
scheduler runs in-process.

## Licence note

The code here is Apache-2.0. The Swiss Ephemeris (via `pyswisseph`) is dual
AGPL/commercial, so check that before distributing.
