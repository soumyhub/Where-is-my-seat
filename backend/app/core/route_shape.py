"""The shape of a journey for a map: each train leg along the track, road legs as straight lines."""

from __future__ import annotations

import math
from typing import Any

from .railmap import Point, RailMap
from .search.explorer import RideLeg
from .search.itinerary import Itinerary
from .stations import StationDirectory

ATTRIBUTION = "Railway lines © OpenStreetMap contributors (ODbL)"
DISPLAY_TOLERANCE = 0.0008  # degrees (≈ 80 m) — plenty for a phone-sized map


def _simplify(points: list[Point], tol: float) -> list[Point]:
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
            d = abs(dy * (points[k][1] - ax) - dx * (points[k][0] - ay)) / norm
            if d > best:
                best, idx = d, k
        if best > tol and idx > 0:
            keep[idx] = True
            stack += [(i, idx), (idx, j)]
    return [p for p, k in zip(points, keep) if k]


def itinerary_shape(it: Itinerary, directory: StationDirectory, railmap: RailMap | None) -> dict[str, Any]:
    legs: list[dict[str, Any]] = []
    lats: list[float] = []
    lons: list[float] = []
    track_km = matched_km = 0.0

    def where(code: str) -> Point | None:
        s = directory.get(code)
        return (s.lat, s.lon) if s and s.lat is not None and s.lon is not None else None

    def stop(code: str, role: str) -> dict[str, Any] | None:
        p = where(code)
        if p is None:
            return None
        lats.append(p[0])
        lons.append(p[1])
        return {"code": code, "name": directory.name(code), "lat": p[0], "lon": p[1], "role": role}

    for pl in it.legs:
        leg = pl.leg
        if isinstance(leg, RideLeg):
            stops_all = leg.train.stops[leg.board : leg.alight + 1]
            codes = [s.station for s in stops_all]
            segments = []
            for a, b in zip(codes, codes[1:]):
                pa, pb = where(a), where(b)
                seg = railmap.segment(a, b, pa, pb) if railmap else None
                if seg is None:
                    if pa is None or pb is None:
                        continue
                    points, matched = [pa, pb], False
                else:
                    points, matched = list(seg.points), seg.matched
                km = (stops_all[codes.index(b)].km - stops_all[codes.index(a)].km) or 1
                track_km += km
                if matched:
                    matched_km += km
                segments.append(
                    {"points": [[round(y, 5), round(x, 5)] for y, x in _simplify(points, DISPLAY_TOLERANCE)], "matched": matched}
                )
            stops = [
                s
                for i, code in enumerate(codes)
                if (s := stop(code, "board" if i == 0 else "alight" if i == len(codes) - 1 else "halt"))
            ]
            legs.append({"kind": "train", "train_number": leg.train.number, "train_name": leg.train.name,
                         "segments": segments, "stops": stops})
        else:
            a, b = stop(leg.from_code, "road"), stop(leg.to_code, "road")
            segments = [{"points": [[a["lat"], a["lon"]], [b["lat"], b["lon"]]], "matched": False}] if a and b else []
            legs.append({"kind": "road", "train_number": None, "train_name": None, "segments": segments,
                         "stops": [s for s in (a, b) if s]})
    bounds = [[min(lats), min(lons)], [max(lats), max(lons)]] if lats else None
    return {
        "legs": legs,
        "bounds": bounds,
        "track_share": round(matched_km / track_km, 2) if track_km else 0.0,
        "attribution": ATTRIBUTION,
        "available": railmap is not None,
    }
