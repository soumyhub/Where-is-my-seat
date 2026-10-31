"""Rough road / metro estimates for feeder, station-change and onward legs.

These legs are never booked through the app. Times and costs are labelled estimates:
explicit overrides from ``road_transfers.json`` first, otherwise a distance formula on
approximate station coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .stations import StationDirectory

ESTIMATE_BASIS = "Rough estimate from straight-line distance; check a maps app before you go."


@dataclass(frozen=True, slots=True)
class RoadEstimate:
    from_code: str
    to_code: str
    minutes: int
    km: int
    cost_per_person: int
    mode: str
    basis: str = ESTIMATE_BASIS


class RoadEstimator:
    def __init__(self, directory: StationDirectory, overrides: list[dict[str, Any]] | None = None):
        self._directory = directory
        self._overrides: dict[frozenset[str], dict[str, Any]] = {}
        for row in overrides or []:
            self._overrides[frozenset((row["a"], row["b"]))] = row

    def estimate(self, a: str, b: str) -> RoadEstimate | None:
        if a == b:
            return None
        override = self._overrides.get(frozenset((a, b)))
        straight = self._directory.distance_km(a, b)
        if override:
            km = int(override.get("km") or round((straight or 0) * 1.3))
            return RoadEstimate(
                a,
                b,
                int(override["minutes"]),
                km,
                int(override["cost"]),
                override.get("mode", "Metro / auto / cab"),
                override.get("basis", "Estimate for typical traffic; not a timetable."),
            )
        if straight is None:
            return None
        sa, sb = self._directory.get(a), self._directory.get(b)
        same_city = bool(sa and sb and sa.city == sb.city)
        if same_city:
            road_km = max(2.0, straight * 1.35)
            minutes = round(road_km / 20 * 60 + 15)
            cost = round(20 + road_km * 5)
            mode = "Metro / auto / cab"
        else:
            road_km = straight * 1.3
            minutes = round(road_km / 45 * 60 + 20)
            cost = round(30 + road_km * 1.4)
            mode = "Bus or cab"
        return RoadEstimate(a, b, int(minutes), int(round(road_km)), int(cost), mode)
