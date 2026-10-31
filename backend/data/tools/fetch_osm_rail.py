#!/usr/bin/env python3
"""Download India's railway lines from OpenStreetMap through the public Overpass API.

One-time (or occasional) build step for ``build_rail_graph.py``. India is fetched in 2°×2°
tiles, one at a time, with retries and backoff, which keeps well inside Overpass's fair-use
policy. Yard and siding tracks (``service=*``) are left out. Data © OpenStreetMap
contributors, ODbL 1.0.

Usage:  .venv/bin/python data/tools/fetch_osm_rail.py <out_dir>   (from backend/)
        (writes tile_<lat>_<lon>.json files; tiles already downloaded are skipped)
"""

from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

SERVERS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
AGENT = "WhereIsMySeat-build/1.0 (one-time railway export for a route map)"
LAT = (6, 38)
LON = (68, 98)
STEP = 2
QUERY = '[out:json][timeout:300];way["railway"="rail"][!"service"]({s},{w},{n},{e});out body geom;'


def _tls() -> ssl.SSLContext:
    try:
        import certifi  # installed with the backend's dev requirements

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch(query: str) -> dict:
    wait = 20
    for attempt in range(12):
        server = SERVERS[attempt % len(SERVERS)]
        body = urllib.parse.urlencode({"data": query}).encode()
        request = urllib.request.Request(server, data=body, headers={"User-Agent": AGENT})
        try:
            with urllib.request.urlopen(request, timeout=400, context=_tls()) as response:  # noqa: S310 (fixed hosts)
                return json.loads(response.read())
        except Exception as exc:  # busy server, timeout, bad gateway: back off and retry
            print(f"  {server.split('/')[2]}: {exc} — retrying in {wait}s", flush=True)
            time.sleep(wait)
            wait = min(wait * 2, 300)
    raise RuntimeError("Overpass kept failing")


def tiles_with_stations() -> set[tuple[int, int]]:
    """Only tiles that hold at least one station (skips sea and empty desert/mountain tiles)."""
    doc = json.loads((Path(__file__).resolve().parents[1] / "tag2026" / "stations.json").read_text())
    out = set()
    for st in doc["stations"]:
        if st.get("lat") is not None:
            out.add((int((st["lat"] - LAT[0]) // STEP) * STEP + LAT[0], int((st["lon"] - LON[0]) // STEP) * STEP + LON[0]))
    return out


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    wanted = tiles_with_stations()
    print(f"{len(wanted)} tiles to fetch", flush=True)
    for s in range(LAT[0], LAT[1], STEP):
        for w in range(LON[0], LON[1], STEP):
            path = out / f"tile_{s}_{w}.json"
            if path.exists() or (s, w) not in wanted:
                continue
            doc = fetch(QUERY.format(s=s, w=w, n=s + STEP, e=w + STEP))
            ways = sum(1 for e in doc.get("elements", []) if e.get("type") == "way")
            path.write_text(json.dumps(doc, separators=(",", ":")))
            print(f"tile {s},{w}: {ways} ways", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
