# calendar — personal astrological-weather engine

Computes every active astrological influence for people (and later pets), stores
them as `event` rows, and serves them to Google Calendar (ICS), and later Claude
(MCP) and push channels. Backend-first: the API is the product.

The Python import package is **`skycal`**, not `calendar`: a top-level package
named `calendar` would shadow the standard-library `calendar` module, which
`icalendar`, `email` and `http.cookiejar` import.

## Stack
- Python 3.12, `uv`, `ruff`, `pytest`
- `pyswisseph` for every position; our own chart/aspect/transit logic on top, so
  Western and Vedic share one code path. `kerykeion` is a **test-only** dependency.
  It uses its own JPL-based backend, which makes it an independent cross-check.
- FastAPI + Pydantic v2 + SQLModel; SQLite now, Postgres-compatible types
  (`Uuid`, JSON→JSONB variant, tz-aware `UTCDateTime`), Alembic migrations
- APScheduler (nightly recompute 02:00 `APP_TIMEZONE`, hourly Moon refresh)
- `icalendar` for ICS; Dockerfile + `fly.toml`

## Layout
```
src/skycal/
  core/        ephemeris.py (swisseph wrapper + cache), zodiac.py, houses.py, aspects.py
  charts/      natal.py (cast a chart), models.py (pydantic chart shapes)
  techniques/  base.py (EventGenerator protocol), transits.py, + Phase-3 stubs
  db/          models.py (all tables, all phases), session.py, types.py, migrations/
  api/         app.py, routes/{entities,charts,events,ics,sky,rules}.py
  jobs/        scheduler.py, recompute.py
  adapters/    ics.py
scripts/       fetch_ephemeris.py, seed_me.py, recompute_now.py
```

## Commands
```
uv sync                                   # install (Python 3.12)
uv run python scripts/fetch_ephemeris.py  # Swiss Ephemeris data files -> data/ephe (needed for Chiron)
uv run pytest                             # tests
uv run ruff check . && uv run ruff format --check .
uv run alembic upgrade head               # migrate DATABASE_URL
uv run alembic revision --autogenerate -m "..."   # new migration after model change
uv run uvicorn skycal.api.app:app --reload
```

## Conventions
- Every datetime is tz-aware UTC in storage (`UTCDateTime` rejects naive ones).
  Local time appears only at the edges: API input and ICS rendering.
- Longitudes are floats in [0, 360). Never round in storage.
- Every row has `owner_user_id`.
- One `EventGenerator` protocol: `generate(entity, system, window) -> list[Event]`.
- Docstrings explain each astrological term the first time it appears. The reader
  is a data scientist, not an astrologer.
- No interpretation text in Phase 1. Events are facts.
- Conventional commits; commit after each acceptance criterion passes.

## Phase status
- [x] Phase 1: ephemeris wrapper, natal charts (Western + Vedic), transit scanner,
      event table, ICS feed, seed script, nightly recompute
- [ ] Phase 2: rules + matcher, day scores, weekly brief (Claude API), MCP server
- [ ] Phase 3: progressions, solar arc, returns, Vimshottari dashas, sky events, push
- [ ] Phase 4: multi-entity, relationships, pets, auth
- [ ] Phase 5: community rules, sharing, minimal web view

## Decisions made where the spec left room
- **Package name** `skycal` (see top).
- **Ephemeris files are not committed.** `scripts/fetch_ephemeris.py` downloads
  `sepl_18/semo_18/seas_18.se1` (1800–2399 CE) into `SKYCAL_EPHE_PATH`. Chiron
  needs them. The wrapper raises an error rather than silently falling back to
  the lower-precision Moshier model.
- **Licence:** pyswisseph / Swiss Ephemeris is AGPL (or a commercial licence),
  but this repo is Apache-2.0. That's fine for personal use. Anything distributed
  needs a decision.
- **Orbs for transits are set by the *transiting* body's class.** The table's
  "8° if Sun or Moon involved" rule, applied to the natal side, would give
  Pluto conj natal Sun an 8° orb. That's about 8 years of a single event. So:
  transiting Sun/Moon get luminary orbs, transiting Mercury/Venus/Mars get inner
  orbs, everything else gets outer orbs. For **natal** aspects (both points are
  fixed) the pair rule from the spec applies as written: luminary if either is
  Sun/Moon, else inner if either is personal (incl. ASC/MC), else outer.
  `prefs.orbs_override` will let users change this (wired in Phase 2).
- **Tiers for cases the table didn't cover:** Sun transits = tier 3. Outer
  bodies (Uranus/Neptune/Pluto/Nodes/Chiron) to non-personal natal points =
  tier 2.
- **South Node is not scanned in Western.** Its position is always exactly
  opposite the North Node, so "X conj natal SN" is the same fact as "X opp
  natal NN". It's still stored in chart points. Vedic scans Ketu, because graha
  drishti isn't symmetric.
- **Vedic nodes:** true node (same as Western) for Rahu; Ketu = Rahu + 180°.
- **Vedic aspects (graha drishti):** every graha aspects the 7th sign from
  itself. Mars also aspects the 4th and 8th, Jupiter the 5th and 9th, Saturn the
  3rd and 10th, and Rahu/Ketu the 5th and 9th (common modern practice; BPHS is
  ambiguous on this). Conjunction = same sign. A Vedic transit event spans the
  whole time the transiting graha sits in the aspecting sign. `exact` is the
  moment of degree-for-degree perfection, or closest approach with
  `meta.perfected=false` if perfection never happens.
- **Vedic points:** Sun–Saturn + Rahu/Ketu only (per spec). The Lagna
  (ascendant) is reported in `houses` but isn't a transit target.
- **Retrograde passes:** if a transiting planet perfects the same aspect several
  times inside one continuous in-orb window (direct → retrograde → direct), the
  window is split at the turning points into one event per perfection, with
  `meta.pass` / `meta.passes`.
- **`applying`** is evaluated at computation time (`as_of`): before `exact` →
  applying, after → separating. The nightly recompute keeps it current.
- **Event `uid`** = hash(entity, system, technique, transiting, natal, aspect
  target, UTC date of exact). The scan grid is anchored to whole UTC
  days/hours, so recomputes are bit-identical and Google updates events
  instead of duplicating them.
- **`time_known`** is carried in `chart.meta` / `event.meta` rather than a column.
- **Auth (Phase 4):** Phase 1 runs as a single implicit user
  (`DEFAULT_USER_EMAIL`), created on boot. The ICS feed is protected by a 32-byte
  `feed_token`.
- **ICS rendering is on demand** from the `event` table. "Regenerate ICS" in the
  nightly job means refreshing those rows. The job also renders each feed once
  as a smoke check.
- **Placidus above the polar circles** is undefined. In that case we fall back to
  Porphyry and record `houses.fallback`.
