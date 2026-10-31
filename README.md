# Where is my Seat

**Your train is full. Your journey isn't over.**

Search a route and see every direct train from Indian Railways' official timetable — and when your
train is waitlisted, the backup tickets and other routes worth checking on IRCTC.

- **Real trains:** 3,202 trains with real numbers, names, running days, classes and published
  times from the Railway Board's *Trains at a Glance 2026*.
- **Real network:** 8,718 searchable stations; 804 have timetable trains, including 329
  junctions (Wikipedia's list). From any other station the search starts at the nearest
  station with trains (road leg, estimated). Cities are grouped (e.g. "Delhi" covers NDLS,
  DLI, NZM, DEE, DEC, ANVT, DSA).
- **Route map:** each journey drawn along the real railway line (OpenStreetMap, ODbL) on an
  OpenStreetMap base map; gaps in the track data are shown dashed.
- **Seat Watch:** follow tickets, record every status (yours or live), see whether the
  waitlist moves, get daily calendar reminders.
- **Not live:** seat availability, running status and exact fares. Every option shows exactly
  what to enter on IRCTC (train, from, to, date, class) with a link and a copy button.

The look follows the Where is my Train app (blue bar, green actions, train-number badges,
running-day letters, vertical stop timeline). The logo and name treatment are original.

## Run it (₹0 — local only, no paid services, no API keys)

Needs Python 3.11+ and Node.js 20+.

```bash
./dev.sh
```

Opens on http://localhost:3000 (API on :8000, docs at http://localhost:8000/docs). First run
installs dependencies. Or run the two halves separately:

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev
```

### Tests and checks

```bash
cd backend && .venv/bin/python -m pytest
cd frontend && npm run typecheck && npm run lint && npm run build
```

## What you get

**Search** — From/To (any station, code, old name like "Mughalsarai", or a whole city), date,
class, travellers; more options for changes allowed, nearby dates, budget, journey time, nearby
stations and backup tickets.

**Results** (full-width on desktop: filters · list · details)
- *Direct trains*: Where-is-my-Train-style cards — number, name, running days, times, duration,
  every class with an estimated fare, and **Check seats** (IRCTC).
- *If it's full*: per train, the backup tickets to try — book further and get off early, book
  from the starting station and change boarding point, split into two tickets, or board at a
  nearby station.
- *Other ways*: one change at a junction, starting from a nearby station, or ending near the
  destination — similar options grouped.
- Day-before / day-after buttons, departure-time and train-type filters, four sort orders.
- Details panel: exact IRCTC lookup for each ticket, stop-by-stop timeline, things to know.

**Saved journeys** (browser only), share links (Web Share / copy / WhatsApp), print view.

## Live seats at ₹0 — what is possible

There is no free, official way to get live seat availability:

1. Indian Railways publishes **no free public API** for availability, fares or running status.
2. **IRCTC and NTES terms forbid scraping** or building a database from their sites, and they
   use bot protection. This app never scrapes, bypasses CAPTCHAs, books or takes payments.

What this build does:

- **Check on IRCTC** for every ticket, with the exact train, stations, date and class (copied
  for you) and the backup tickets worth trying.
- **Optional live checks** with your own [RailRadar](https://railradar.in/pricing) key
  (an independent third party, not IRCTC). Their free Sandbox key does **not** include seat
  availability (tested 30 Oct 2026: `PLAN_UPGRADE_REQUIRED`); seats need the paid Developer
  plan (from ₹499/month). With a free key the app says so, gives back the failed request,
  stops offering live checks for 24 h and keeps the IRCTC links.
  RailRadar calls its seat data an availability forecast, so the app always says to confirm
  on IRCTC. Sign up yourself, then put `WIMS_RAILRADAR_KEY=…` in `backend/.env` and restart.
  The backend caps use at 90 per rolling 30 days (stored in `backend/.state/`), caches each
  answer for 30 minutes (one request answers several dates), and never spends checks inside
  a search.
- **Live info with a free RailRadar key** (journey details → *Live info*, and `/station`):
  running status and delay, exact fare breakdown, coach position, usual delay
  (punctuality), cancellations/diversions/reschedules, and live station boards. All of it
  shares the same 90-requests-per-30-days budget, and every answer is cached (2 min for
  running status and boards, 1 day for fares and coaches, 1 week for punctuality, 3 h for the
  exceptions list) in memory and in `backend/.state/`. RailRadar's lookup dumps, journey
  planner and trains-between-stations are not used: the app has its own timetable and router,
  and bulk-copying their dictionaries would go beyond personal use.
- **Seat Watch** (`/watch`): follow tickets, note what IRCTC shows or check live, see how the
  waitlist moves, auto-check every 6 h while the page is open, and add daily calendar reminders.

For a large public service, the proper route is an IRCTC authorised partnership or a licensed
data provider: implement `AuthorizedLiveProvider` in `backend/app/core/availability/providers.py`
and run with `WIMS_AVAILABILITY_PROVIDER=live`.

## Data

| Folder | Contents |
| --- | --- |
| `backend/data/tag2026/` | **Default.** Real trains and stations — see its README for sources, licences, what was excluded and how to rebuild. |
| `backend/data/simulated/` | The original simulated demo network (SIM- trains + scripted seat statuses), kept for tests and demos: `WIMS_TIMETABLE=simulated`. |
| `backend/data/osm/` | Railway track graph for the route map, from OpenStreetMap (ODbL) — see its README. |
| `backend/data/tools/` | `build_real_dataset.py` (real network), `fetch_osm_rail.py` + `build_rail_graph.py` (route-map track) and the simulated-data generator. |

Limits of the source: only main halts, retimings after publication not reflected, distances
estimated from coordinates, a few hundred trains excluded where running days or origin could not
be confirmed. Always confirm on NTES/IRCTC before travelling.

## Environment variables (all optional)

| Variable | Default | Meaning |
| --- | --- | --- |
| `WIMS_TIMETABLE` | `tag2026` | `tag2026` (real) or `simulated` (demo) |
| `WIMS_AVAILABILITY_PROVIDER` | `auto` | `auto` = none for real data (railradar if a key is set), simulated for the demo; or `none`, `simulated`, `railradar`, `live` |
| `WIMS_RAILRADAR_KEY` | — | Your own RailRadar key: turns on live checks of single tickets |
| `WIMS_LIVE_MONTHLY_LIMIT` | `90` | Hard cap on live requests per rolling 30 days |
| `WIMS_LIVE_CACHE_MINUTES` | `30` | How long a live answer is reused |
| `WIMS_LIVE_PROVIDER_URL` / `_KEY` | — | For an authorised live provider you implement |
| `WIMS_MAX_ADVANCE_DAYS` | `60` | Booking window |
| `WIMS_API_URL` (frontend) | `http://127.0.0.1:8000` | Backend address for the `/api` proxy |

## Architecture

```
backend/app/core/        pure Python domain: stations, timetable index, time-dependent graph,
                         bounded round-based search, ticketing & backup tickets, ranking,
                         explanations, availability providers, fare estimates
backend/app/main.py      FastAPI: /health /meta /stations /journeys/search /journeys/{id} /journeys/{id}/map /availability/check /availability/usage /live/trains/{n} (+ /punctuality /alerts /coaches/{stn}) /live/stations/{code} /live/fare
frontend/src/            Next.js 16 + Tailwind 4: search, results, journey, saved, about
```

The search engine: stations are nodes, each scheduled train run between two halts is a
time-dependent edge; a breadth-first search adds one train per round (≤ 3), only changes trains
at junctions/major stations with ≥ 30 min to spare, never doubles back, prunes detours, and is
capped by expansion, candidate and time budgets (typical search: 50–500 ms).

The product name sits close to the Where is my Train trademark (a Google product); check that
before any public launch.
