"""Train paths on real track, for maps, from OpenStreetMap railway lines.

``data/osm/rail_graph.json`` (built by ``data/tools/build_rail_graph.py``; © OpenStreetMap
contributors, ODbL) is a graph of India's railway lines with each station snapped to its
nearest track. Between two halts the path is the shortest one along the track (A*). When the
track data has a gap, or the shortest path is an implausible detour, that stretch is drawn as
a straight line and marked ``matched=False`` — the map never pretends to know more.
"""

from __future__ import annotations

import heapq
import json
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

Point = tuple[float, float]  # (lat, lon)

MAX_DETOUR = 1.9  # track path longer than this × straight line → treat as a gap
MAX_SNAP_M = 3000  # station further than this from any track → not matched


def _hav_m(a: Point, b: Point) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


@dataclass(frozen=True, slots=True)
class Segment:
    from_code: str
    to_code: str
    points: tuple[Point, ...]
    matched: bool  # True: follows the track; False: straight line (no track path found)
    km: float | None  # length along the track, when matched


class RailMap:
    def __init__(self, doc: dict) -> None:
        self.meta = doc.get("meta", {})
        self._nodes: list[Point] = [(y / 1e5, x / 1e5) for y, x in doc["nodes"]]
        self._adj: list[list[tuple[int, int, int]]] = [[] for _ in self._nodes]  # (to, metres, edge)
        self._shapes: list[list[int]] = []
        self._ends: list[tuple[int, int]] = []
        self._lengths: list[int] = []
        for k, (u, v, length, flat) in enumerate(doc["edges"]):
            self._adj[u].append((v, length, k))
            self._adj[v].append((u, length, k))
            self._shapes.append(flat)
            self._ends.append((u, v))
            self._lengths.append(length)
        self._stations: dict[str, tuple[int, int]] = {c: (n, d) for c, (n, d) in doc["stations"].items()}
        self._cache: OrderedDict[tuple[str, str], Segment | None] = OrderedDict()
        self._lock = threading.Lock()

    @classmethod
    def load(cls, path: Path) -> RailMap | None:
        if not path.is_file():
            return None
        return cls(json.loads(path.read_text()))

    def knows(self, code: str) -> bool:
        snap = self._stations.get(code)
        return bool(snap and snap[1] <= MAX_SNAP_M)

    # ----- paths --------------------------------------------------------
    def segment(self, a: str, b: str, a_point: Point | None, b_point: Point | None) -> Segment | None:
        """Path between two stations; None when neither the track nor coordinates are known."""
        key = (a, b)
        with self._lock:
            known = key in self._cache
            if known:
                self._cache.move_to_end(key)
                seg = self._cache[key]
        if not known:
            seg = self._track_segment(a, b)
            with self._lock:
                self._cache[key] = seg
                if len(self._cache) > 5000:
                    self._cache.popitem(last=False)
        if seg is None and a_point and b_point:
            seg = Segment(a, b, (a_point, b_point), False, None)
        return seg

    def _track_segment(self, a: str, b: str) -> Segment | None:
        if not (self.knows(a) and self.knows(b)):
            return None
        start, goal = self._stations[a][0], self._stations[b][0]
        if start == goal:
            return None
        straight = _hav_m(self._nodes[start], self._nodes[goal])
        budget = straight * MAX_DETOUR + 2000
        edges = self._astar(start, goal, budget)
        if edges is None:
            return None
        points: list[Point] = [self._nodes[start]]
        metres = 0
        at = start
        for k in edges:
            u, v = self._ends[k]
            shape = self._edge_points(k)
            if at == v:
                shape = shape[::-1]
                at = u
            else:
                at = v
            points.extend(shape[1:])
            metres += self._lengths[k]
        return Segment(a, b, tuple(points), True, round(metres / 1000, 1))

    def _edge_points(self, k: int) -> list[Point]:
        u, v = self._ends[k]
        y, x = round(self._nodes[u][0] * 1e5), round(self._nodes[u][1] * 1e5)
        pts = [self._nodes[u]]
        flat = self._shapes[k]
        for i in range(0, len(flat), 2):
            y += flat[i]
            x += flat[i + 1]
            pts.append((y / 1e5, x / 1e5))
        pts.append(self._nodes[v])
        return pts

    def _astar(self, start: int, goal: int, budget: float) -> list[int] | None:
        target = self._nodes[goal]
        best = {start: 0.0}
        came: dict[int, tuple[int, int]] = {}
        heap = [(_hav_m(self._nodes[start], target), 0.0, start)]
        settled = 0
        while heap:
            f, g, n = heapq.heappop(heap)
            if n == goal:
                path = []
                while n != start:
                    prev, edge = came[n]
                    path.append(edge)
                    n = prev
                return path[::-1]
            if g > best.get(n, math.inf) or f > budget:
                continue
            settled += 1
            if settled > 200_000:
                return None
            for to, length, edge in self._adj[n]:
                ng = g + length
                if ng < best.get(to, math.inf):
                    best[to] = ng
                    came[to] = (n, edge)
                    heapq.heappush(heap, (ng + _hav_m(self._nodes[to], target), ng, to))
        return None
