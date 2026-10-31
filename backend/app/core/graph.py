"""Time-dependent railway graph.

Nodes are stations. Every scheduled train run between two of its halts is a
time-dependent edge (it exists only at the times the train actually runs). Same-city
station changes (e.g. New Delhi -> Delhi Sarai Rohilla) are road edges with estimated
durations. The graph is built once at startup from the timetable index.
"""

from __future__ import annotations

from datetime import datetime

from .road import RoadEstimate, RoadEstimator
from .stations import StationDirectory
from .timetable import Departure, Timetable


LARGE_NETWORK_TRAINS = 300  # above this, only major stations are used as change points
MIN_DEPARTURES_FOR_TRANSFER = 6


class TimeDependentGraph:
    def __init__(self, timetable: Timetable, directory: StationDirectory, road: RoadEstimator) -> None:
        self.timetable = timetable
        self.directory = directory
        self.road = road
        self._city_edges: dict[str, list[RoadEstimate]] = {}
        # On a national network, travellers change trains at junctions and big stations, not at
        # every halt. Restricting change points keeps the search focused and fast.
        departures: dict[str, set[str]] = {}
        for train in timetable.trains():
            for stop in train.stops:
                if stop.boardable:
                    departures.setdefault(stop.station, set()).add(train.number)
        large = len(timetable.trains()) >= LARGE_NETWORK_TRAINS
        self._transfer_points: set[str] | None = None
        if large:
            self._transfer_points = {
                s.code
                for s in directory.all()
                if s.junction
                or len(departures.get(s.code, ())) >= MIN_DEPARTURES_FOR_TRANSFER
                or len(directory.stations_in_city(s.city)) > 1
            }
        self.departure_counts = {code: len(trains) for code, trains in departures.items()}
        for station in directory.all():
            edges: list[RoadEstimate] = []
            for other in directory.stations_in_city(station.city):
                if other == station.code or not timetable.serves_departures(other):
                    continue
                estimate = road.estimate(station.code, other)
                if estimate is not None:
                    edges.append(estimate)
            self._city_edges[station.code] = sorted(edges, key=lambda e: e.minutes)

    def serves(self, station: str) -> bool:
        return self.timetable.serves_departures(station)

    def is_transfer_point(self, station: str) -> bool:
        return self._transfer_points is None or station in self._transfer_points

    def progress_ok(self, origin: str, destination: str, via: str, slack_km: float) -> bool:
        """A change point should not be meaningfully farther from the destination than the origin."""
        start = self.directory.distance_km(origin, destination)
        here = self.directory.distance_km(via, destination)
        if start is None or here is None:
            return True
        return here <= start + slack_km

    def departures(self, station: str, earliest: datetime, latest: datetime) -> list[Departure]:
        return self.timetable.departures(station, earliest, latest)

    def city_transfers(self, station: str) -> list[RoadEstimate]:
        return self._city_edges.get(station, [])

    def detour_ok(self, origin: str, destination: str, via: str, factor: float, slack_km: float) -> bool:
        """Prune transfer points far outside the origin-destination ellipse."""
        direct = self.directory.distance_km(origin, destination)
        a = self.directory.distance_km(origin, via)
        b = self.directory.distance_km(via, destination)
        if direct is None or a is None or b is None:
            return True  # without coordinates we cannot judge; keep it
        return a + b <= factor * direct + slack_km
