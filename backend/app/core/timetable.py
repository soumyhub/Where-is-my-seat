"""Timetable access with a per-station departure index.

Departures are looked up from an index (station -> boardable halts) instead of scanning
every train, and only start dates that can produce a departure inside the requested
window are considered.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from .models import Train, TrainRun


@dataclass(frozen=True, slots=True)
class Departure:
    run: TrainRun
    index: int  # boarding stop index
    time: datetime


class Timetable:
    def __init__(self, trains: list[Train], meta: dict[str, Any] | None = None) -> None:
        self.meta = meta or {}
        self._trains = {t.number: t for t in trains}
        self._boardable: dict[str, list[tuple[str, int]]] = {}
        self._alightable: dict[str, list[tuple[str, int]]] = {}
        for train in trains:
            for stop in train.stops:
                if stop.boardable:
                    self._boardable.setdefault(stop.station, []).append((train.number, stop.index))
                if stop.alightable:
                    self._alightable.setdefault(stop.station, []).append((train.number, stop.index))

    def train(self, number: str) -> Train | None:
        return self._trains.get(number)

    def trains(self) -> list[Train]:
        return list(self._trains.values())

    def serves_departures(self, station: str) -> bool:
        return bool(self._boardable.get(station))

    def serves_arrivals(self, station: str) -> bool:
        return bool(self._alightable.get(station))

    def departures(self, station: str, earliest: datetime, latest: datetime) -> list[Departure]:
        out: list[Departure] = []
        for number, index in self._boardable.get(station, ()):
            train = self._trains[number]
            dep_minutes = train.stops[index].dep
            assert dep_minutes is not None
            offset = timedelta(minutes=dep_minutes)
            start = (earliest - offset).date()
            last = (latest - offset).date()
            day = start
            while day <= last:
                if train.runs_on_date(day):
                    when = datetime.combine(day, time()) + offset
                    if earliest <= when <= latest:
                        out.append(Departure(TrainRun(train, day), index, when))
                day += timedelta(days=1)
        out.sort(key=lambda d: (d.time, d.run.train.number))
        return out

    def run_for_journey_date(self, train: Train, index: int, journey_date: date) -> TrainRun | None:
        """The run that departs stop ``index`` on ``journey_date``, if the train runs that day."""
        dep_minutes = train.stops[index].dep
        if dep_minutes is None:
            return None
        start = journey_date - timedelta(days=dep_minutes // 1440)
        if not train.runs_on_date(start):
            return None
        return TrainRun(train, start)
