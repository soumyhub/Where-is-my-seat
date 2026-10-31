#!/usr/bin/env python3
"""Build ``data/osm/rail_graph.json``: India's railway lines as a routable graph.

Input: OpenStreetMap railway lines for India (© OpenStreetMap contributors, ODbL 1.0), either

* a folder of Overpass tiles from ``fetch_osm_rail.py`` (preferred: exact OSM node links), or
* a GeoJSON export such as HOTOSM's ``railways.geojson`` from HDX (its lines are split at
  district borders and some stretches are missing, so routes match less often).

The output is a derived database and is ODbL too.

What it does:

* every ``railway=rail`` line becomes graph edges; lines that share an OSM node connect;
* each station with trains in ``data/tag2026/stations.json`` is snapped to the nearest track
  point within 5 km (its distance is recorded);
* loose ends of track are joined to other track within 40 m, or within 300 m straight ahead
  (the export splits lines at district borders, bridges and tunnels without a shared node);
* chains of track between junctions are merged into one edge, and their shape is simplified
  to about 30 m so the file stays small.

The app uses it only to draw a train's path on a map (and to know how long that path is).

Usage:  python3 -I data/tools/build_rail_graph.py <tiles_dir | railways.geojson>
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parents[1]
OUT = DATA / "osm" / "rail_graph.json"
SNAP_KM = 5.0
CELL = 0.05  # degrees, for the nearest-point grid
SIMPLIFY_DEG = 0.0003  # ≈ 30 m
HEAL_M = 40.0  # loose track ends closer than this to other track are joined
HEAL_CELL = 0.0005  # degrees (≈ 55 m)
GAP_M = 300.0  # …and up to this far when the other track lies straight ahead
GAP_COS = math.cos(math.radians(30))


def hav_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def simplify(points: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Douglas–Peucker (iterative); keeps both ends."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        (ay, ax), (by, bx) = points[i], points[j]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1e-12
        best, idx = 0.0, -1
        for k in range(i + 1, j):
            py, px = points[k]
            d = abs(dy * (px - ax) - dx * (py - ay)) / norm
            if d > best:
                best, idx = d, k
        if best > tol and idx > 0:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [p for p, k in zip(points, keep) if k]


def main(source: Path) -> None:
    ids: dict[object, int] = {}
    coords: list[tuple[float, float]] = []
    adj: list[set[int]] = []

    def vid(key: object, lat: float, lon: float) -> int:
        i = ids.get(key)
        if i is None:
            i = ids[key] = len(coords)
            coords.append((round(lat, 5), round(lon, 5)))
            adj.append(set())
        return i

    def link(pts: list[int]) -> None:
        for a, b in zip(pts, pts[1:]):
            if a != b:
                adj[a].add(b)
                adj[b].add(a)

    lines = 0
    if source.is_dir():
        # Overpass tiles (fetch_osm_rail.py): OSM node ids give exact connections.
        seen_ways: set[int] = set()
        for tile in sorted(source.glob("tile_*.json")):
            for e in json.load(open(tile)).get("elements", []):
                if e.get("type") != "way" or e["id"] in seen_ways or not e.get("geometry"):
                    continue
                seen_ways.add(e["id"])
                link([vid(n, g["lat"], g["lon"]) for n, g in zip(e["nodes"], e["geometry"]) if g])
                lines += 1
    else:
        # A GeoJSON export (e.g. HOTOSM): points shared by coordinates.
        for f in json.load(open(source))["features"]:
            g = f.get("geometry") or {}
            if f.get("properties", {}).get("railway") != "rail" or g.get("type") != "LineString":
                continue
            link([vid((round(lat, 5), round(lon, 5)), lat, lon) for lon, lat, *_ in g["coordinates"]])
            lines += 1
    print(f"lines {lines}, track points {len(coords)}")

    # The export splits lines at district borders and elsewhere without a shared node, which
    # leaves small gaps. Join every loose end to the nearest other track point within HEAL_M,
    # or within GAP_M when that point lies straight ahead of the loose end (the line goes on).
    fine: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, (lat, lon) in enumerate(coords):
        fine[(int(lat // HEAL_CELL), int(lon // HEAL_CELL))].append(i)
    reach = math.ceil(GAP_M / 1000 / 111 / HEAL_CELL) + 1  # grid cells to look around

    def heading(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
        k = math.cos(math.radians(a[0]))
        return ((b[1] - a[1]) * k, b[0] - a[0])

    healed = 0
    for i in [i for i, n in enumerate(adj) if len(n) == 1]:
        own = {i}
        ring = {i}
        for _ in range(6):
            ring = {n for r in ring for n in adj[r]} - own
            own |= ring
        here = coords[i]
        back = coords[next(iter(adj[i]))]
        ahead = heading(back, here)
        ahead_len = math.hypot(*ahead) or 1e-12
        cy, cx = int(here[0] // HEAL_CELL), int(here[1] // HEAL_CELL)
        best, best_d = -1, math.inf
        for dy in range(-reach, reach + 1):
            for dx in range(-reach, reach + 1):
                for j in fine.get((cy + dy, cx + dx), ()):
                    if j in own:
                        continue
                    d = hav_m(here, coords[j])
                    if d >= best_d or d > GAP_M:
                        continue
                    if d > HEAL_M:
                        to = heading(here, coords[j])
                        cos = (ahead[0] * to[0] + ahead[1] * to[1]) / (ahead_len * (math.hypot(*to) or 1e-12))
                        if cos < GAP_COS:
                            continue
                    best, best_d = j, d
        if best >= 0:
            adj[i].add(best)
            adj[best].add(i)
            healed += 1
    print(f"loose ends joined: {healed}")

    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, (lat, lon) in enumerate(coords):
        grid[(int(lat // CELL), int(lon // CELL))].append(i)

    stations = json.load(open(DATA / "tag2026" / "stations.json"))["stations"]
    snapped: dict[str, tuple[int, int]] = {}
    for s in stations:
        if not s.get("halts") or s.get("lat") is None:
            continue
        here = (s["lat"], s["lon"])
        cy, cx = int(here[0] // CELL), int(here[1] // CELL)
        best, best_d = -1, SNAP_KM * 1000
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for i in grid.get((cy + dy, cx + dx), ()):
                    d = hav_m(here, coords[i])
                    if d < best_d:
                        best, best_d = i, d
        if best >= 0:
            snapped[s["code"]] = (best, round(best_d))
    print(f"stations snapped {len(snapped)} / {sum(1 for s in stations if s.get('halts'))}")

    # Junctions, ends and station points become graph nodes; plain track in between is merged.
    is_node = [len(n) != 2 for n in adj]
    for i, _ in snapped.values():
        is_node[i] = True
    node_index: dict[int, int] = {}
    for i, flag in enumerate(is_node):
        if flag and adj[i]:
            node_index[i] = len(node_index)

    edges = []
    seen: set[tuple[int, int]] = set()
    for start in node_index:
        for nxt in adj[start]:
            if (start, nxt) in seen:
                continue
            path = [start, nxt]
            prev, cur = start, nxt
            while not is_node[cur]:
                step = next((n for n in adj[cur] if n != prev), None)
                if step is None:
                    break
                prev, cur = cur, step
                path.append(cur)
                if cur == start:  # a closed loop of plain track
                    break
            seen.add((path[0], path[1]))
            seen.add((path[-1], path[-2]))
            if cur not in node_index or path[0] == path[-1]:
                continue
            pts = [coords[i] for i in path]
            length = sum(hav_m(a, b) for a, b in zip(pts, pts[1:]))
            inner = simplify(pts, SIMPLIFY_DEG)[1:-1]
            flat: list[int] = []
            last = (round(pts[0][0] * 1e5), round(pts[0][1] * 1e5))
            for lat, lon in inner:  # delta-encoded 1e-5 degrees from the start node
                y, x = round(lat * 1e5), round(lon * 1e5)
                flat += [y - last[0], x - last[1]]
                last = (y, x)
            edges.append([node_index[path[0]], node_index[cur], round(length), flat])

    nodes = [0] * len(node_index)
    for raw, k in node_index.items():
        nodes[k] = [round(coords[raw][0] * 1e5), round(coords[raw][1] * 1e5)]
    out = {
        "meta": {
            "source": "OpenStreetMap railway lines for India"
            + (" via the Overpass API" if source.is_dir() else f" ({source.name})"),
            "source_url": "https://www.openstreetmap.org/copyright",
            "licence": "© OpenStreetMap contributors — Open Database License (ODbL) 1.0; this file is a derived database under the same licence",
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "coordinates": "integers in 1e-5 degrees; edge shapes are deltas from the edge's first node",
            "snap_limit_km": SNAP_KM,
        },
        "nodes": nodes,
        "edges": edges,
        "stations": {code: [node_index[i], d] for code, (i, d) in sorted(snapped.items())},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"nodes {len(nodes)}, edges {len(edges)}, file {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
