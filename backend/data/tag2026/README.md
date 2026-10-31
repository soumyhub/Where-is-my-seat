# Real network: Trains at a Glance 2026

The default timetable (`WIMS_TIMETABLE=tag2026`). Real Indian Railways trains, not simulated.

| File | What | Source & licence |
| --- | --- | --- |
| `trains.json` | 3,202 trains: number, name, type, running days, classes, main halts with times | Railway Board *Trains at a Glance 2026*, as parsed by [railways-mcp](https://github.com/shubhamyadav8901/railways-mcp) (Apache-2.0) |
| `stations.json` | 8,718 stations (804 with trains, 329 junctions), city groups, coordinates, `halts` = trains stopping | TAG 2026 / datameet station list via railways-mcp; the full directory (codes, names, coordinates only) from [prasenjit-27/Indian-Railway-Data](https://github.com/prasenjit-27/Indian-Railway-Data) (MIT); junctions from Wikipedia "List of railway junction stations in India" (CC BY-SA 4.0); missing coordinates from Wikidata (CC0) |

## What was left out, and why

Nothing is guessed. The build drops records it cannot trust and records the counts in
`trains.json → meta.skipped`:

- `origin_not_confirmed` (125): the timetable could not confirm the first stop is the origin, so
  running days could be off by a day. Another 159 such trains are kept because their own name
  starts with the first listed station (e.g. "Dadar Gorakhpur Special" listed from Dadar); their
  days follow TAG's rule and they carry a note asking to confirm the day.
- `no_running_days` (86) and `classes_not_published` (58).
- `konkan_monsoon_variant` (96): the monsoon timetable (10 Jun–31 Oct); the regular variant is
  kept and only runs inside its own window.
- A few trains that visit a station twice or have fewer than two usable stops.

Known limits of the source: only **main halts** are listed (smaller halts are missing), retimings
after publication are not reflected, and distances are **estimated** from coordinates (TAG's km
columns could not be reconciled). Always confirm timings on NTES/IRCTC before travelling.

Seat availability is **not** part of this data. With this timetable the backend uses no
availability provider by default, so every seat status is "not checked" and the app links to IRCTC.

Why the Indian-Railway-Data schedules are *not* used: compared on the 1,473 trains both sets
share, only 5% of halt times matched TAG 2026 exactly, 73% differed by more than 10 minutes,
running days matched for 37% of trains, and all distances are 0 — it is an older timetable.

## Rebuild

1. Download into a scratch folder:
   - `tag2026.json.gz` from `https://raw.githubusercontent.com/shubhamyadav8901/railways-mcp/main/data/tag2026.json.gz`
   - `wikidata_stations.json`: SPARQL `SELECT ?s ?code ?label ?coord WHERE { ?s wdt:P5696 ?code . OPTIONAL { ?s wdt:P625 ?coord } OPTIONAL { ?s rdfs:label ?label FILTER(LANG(?label)="en") } }` against `https://query.wikidata.org/sparql` (JSON results)
   - `junctions_wikitext.json`: `https://en.wikipedia.org/w/api.php?action=parse&page=List_of_railway_junction_stations_in_India&prop=wikitext&format=json&formatversion=2`
   - `ird_stations.json`: `https://raw.githubusercontent.com/prasenjit-27/Indian-Railway-Data/main/stations.json`
2. Run `python3 -I data/tools/build_real_dataset.py <that folder>` from `backend/`.
