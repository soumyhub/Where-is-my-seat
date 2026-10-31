"""Station lookup: codes, names, city groups, autocomplete and nearby stations."""

from __future__ import annotations

import difflib
import math
from dataclasses import dataclass
from typing import Literal

from .models import City, Station


class UnknownPlaceError(LookupError):
    def __init__(self, query: str, suggestions: list[str]) -> None:
        super().__init__(query)
        self.query = query
        self.suggestions = suggestions


@dataclass(frozen=True, slots=True)
class Place:
    """Something a traveller can search from or to: one station, or every station in a city."""

    kind: Literal["station", "city"]
    key: str  # station code, or "city:<key>"
    name: str
    city: str
    codes: tuple[str, ...]
    anchor: str  # station used for distance and road-time estimates


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class StationDirectory:
    def __init__(self, stations: list[Station], cities: list[City]) -> None:
        self._stations = {s.code: s for s in stations}
        self._cities = {c.key: c for c in cities}
        self._by_city: dict[str, list[str]] = {}
        for s in stations:
            self._by_city.setdefault(s.city, []).append(s.code)

    # ----- basic lookup -------------------------------------------------
    def get(self, code: str) -> Station | None:
        return self._stations.get(code.upper())

    def name(self, code: str) -> str:
        station = self._stations.get(code)
        return station.name if station else code

    def all(self) -> list[Station]:
        return list(self._stations.values())

    def city(self, key: str) -> City | None:
        return self._cities.get(key)

    def stations_in_city(self, key: str) -> list[str]:
        return list(self._by_city.get(key, []))

    def place_for_station(self, code: str) -> Place:
        s = self._stations[code]
        return Place("station", s.code, s.name, s.city, (s.code,), s.code)

    def place_for_city(self, key: str) -> Place:
        c = self._cities[key]
        codes = tuple(self._by_city.get(key, []))
        return Place("city", f"city:{key}", c.name, key, codes, c.anchor)

    # ----- resolution ---------------------------------------------------
    def resolve(self, text: str) -> Place:
        """Resolve a station code, ``city:<key>``, exact station name or city name/alias."""
        raw = (text or "").strip()
        if not raw:
            raise UnknownPlaceError(raw, [])
        lowered = raw.lower()
        if lowered.startswith("city:"):
            key = lowered[5:]
            if key in self._cities and self._by_city.get(key):
                return self.place_for_city(key)
            raise UnknownPlaceError(raw, self.suggestions(key))
        if raw.upper() in self._stations:
            return self.place_for_station(raw.upper())
        for s in self._stations.values():
            if s.name.lower() == lowered or lowered in s.aliases:
                return self.place_for_station(s.code)
        for c in self._cities.values():
            if c.name.lower() == lowered or lowered in c.aliases:
                if len(self._by_city.get(c.key, [])) == 1:
                    return self.place_for_station(self._by_city[c.key][0])
                return self.place_for_city(c.key)
        raise UnknownPlaceError(raw, self.suggestions(raw))

    def suggestions(self, text: str, limit: int = 3) -> list[str]:
        names = [f"{s.name} ({s.code})" for s in self._stations.values()]
        names += [c.name for c in self._cities.values()]
        pool = {n.lower(): n for n in names}
        matches = difflib.get_close_matches(text.lower(), list(pool), n=limit, cutoff=0.5)
        if not matches:
            matches = [k for k in pool if text.lower()[:3] and text.lower()[:3] in k][:limit]
        return [pool[m] for m in matches]

    # ----- autocomplete -------------------------------------------------
    def search(self, query: str, limit: int = 10) -> list[Place]:
        q = (query or "").strip().lower()
        if not q:
            return []
        scored: list[tuple[int, str, Place]] = []
        for c in self._cities.values():
            codes = self._by_city.get(c.key, [])
            if len(codes) < 2:
                continue
            score = _text_score(q, c.name.lower(), c.aliases)
            if score:
                scored.append((score + 5, c.name, self.place_for_city(c.key)))
        for s in self._stations.values():
            score = 0
            code = s.code.lower()
            if q == code:
                score = 100
            elif code.startswith(q):
                score = 80
            score = max(score, _text_score(q, s.name.lower(), s.aliases))
            city = self._cities.get(s.city)
            if city and not score:
                city_score = _text_score(q, city.name.lower(), city.aliases)
                score = city_score - 15 if city_score else 0
            if score:
                if not s.served:
                    score -= 25  # stations with trains first
                scored.append((score, s.name, self.place_for_station(s.code)))
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [place for _, _, place in scored[:limit]]

    # ----- geography ----------------------------------------------------
    def distance_km(self, a: str, b: str) -> float | None:
        sa, sb = self._stations.get(a), self._stations.get(b)
        if not sa or not sb or None in (sa.lat, sa.lon, sb.lat, sb.lon):
            return None
        return haversine_km(sa.lat, sa.lon, sb.lat, sb.lon)  # type: ignore[arg-type]

    def nearby(self, anchor: str, radius_km: float, exclude: set[str]) -> list[tuple[str, float]]:
        out: list[tuple[str, float]] = []
        for code in self._stations:
            if code == anchor or code in exclude:
                continue
            km = self.distance_km(anchor, code)
            if km is not None and km <= radius_km:
                out.append((code, km))
        out.sort(key=lambda row: row[1])
        return out


def _text_score(q: str, name: str, aliases: tuple[str, ...]) -> int:
    if q == name or q in aliases:
        return 90
    if name.startswith(q):
        return 70
    if any(word.startswith(q) for word in name.replace("(", " ").replace(")", " ").split()):
        return 60
    if any(alias.startswith(q) for alias in aliases):
        return 55
    if len(q) >= 3 and q in name:
        return 30
    return 0
