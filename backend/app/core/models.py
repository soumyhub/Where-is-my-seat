"""Core railway domain models. Pure data: no I/O, no web framework."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

RESERVED_CLASSES: tuple[str, ...] = ("1A", "2A", "3A", "3E", "EC", "CC", "FC", "SL", "2S")
UNRESERVED_CLASS = "UR"
CLASS_LABELS: dict[str, str] = {
    "1A": "AC First Class",
    "2A": "AC 2 Tier",
    "3A": "AC 3 Tier",
    "3E": "AC 3 Economy",
    "EC": "Executive Chair Car",
    "CC": "AC Chair Car",
    "FC": "First Class",
    "SL": "Sleeper",
    "2S": "Second Sitting",
    "UR": "Unreserved (General)",
}
WEEKDAY_NAMES: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True, slots=True)
class Station:
    code: str
    name: str
    city: str  # city key, e.g. "delhi"
    state: str
    lat: float | None
    lon: float | None
    junction: bool = False
    aliases: tuple[str, ...] = ()
    halts: int | None = None  # trains that stop here; 0 = searchable, but no train in the timetable

    @property
    def served(self) -> bool:
        return self.halts != 0


@dataclass(frozen=True, slots=True)
class City:
    key: str
    name: str
    anchor: str  # main station, used as the reference point for road estimates
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Stop:
    """A scheduled halt. Times are minutes after 00:00 on the train's start date."""

    index: int
    station: str
    arr: int | None
    dep: int | None
    km: int
    technical: bool = False  # technical halt: passengers may not board or alight

    @property
    def day(self) -> int:
        """1-based running day, as printed in Indian timetables."""
        minutes = self.arr if self.arr is not None else self.dep
        return (minutes or 0) // 1440 + 1

    @property
    def boardable(self) -> bool:
        return self.dep is not None and not self.technical

    @property
    def alightable(self) -> bool:
        return self.arr is not None and not self.technical


@dataclass(frozen=True, slots=True)
class Train:
    number: str
    name: str
    category: str
    runs_on: frozenset[int]  # weekdays (0 = Monday) on which the train leaves its origin
    classes: tuple[str, ...]  # reserved classes; empty for unreserved-only trains
    unreserved: bool  # carries General (UR) coaches
    superfast: bool
    stops: tuple[Stop, ...]
    simulated: bool
    source: str
    valid_from: str | None = None  # "MM-DD": seasonal timetable window (may wrap the year end)
    valid_to: str | None = None
    notes: tuple[str, ...] = ()

    def runs_on_date(self, start_date: date) -> bool:
        """Does a run leave the origin on ``start_date``? Checks weekday and seasonal window."""
        if start_date.weekday() not in self.runs_on:
            return False
        if self.valid_from and self.valid_to:
            md = start_date.strftime("%m-%d")
            if self.valid_from <= self.valid_to:
                return self.valid_from <= md <= self.valid_to
            return md >= self.valid_from or md <= self.valid_to
        return True

    def index_of(self, code: str) -> int | None:
        for stop in self.stops:
            if stop.station == code:
                return stop.index
        return None

    @property
    def origin(self) -> str:
        return self.stops[0].station

    @property
    def destination(self) -> str:
        return self.stops[-1].station

    def runs_on_label(self) -> str:
        if len(self.runs_on) == 7:
            return "Daily"
        return ", ".join(WEEKDAY_NAMES[d] for d in sorted(self.runs_on))


@dataclass(frozen=True, slots=True)
class TrainRun:
    """One train on one start date (the date it leaves its origin station)."""

    train: Train
    start_date: date

    @property
    def key(self) -> str:
        return f"{self.train.number}@{self.start_date.isoformat()}"

    def at(self, minutes: int) -> datetime:
        return datetime.combine(self.start_date, time()) + timedelta(minutes=minutes)

    def dep_at(self, index: int) -> datetime:
        minutes = self.train.stops[index].dep
        if minutes is None:
            raise ValueError(f"{self.train.number} does not depart from stop {index}")
        return self.at(minutes)

    def arr_at(self, index: int) -> datetime:
        minutes = self.train.stops[index].arr
        if minutes is None:
            raise ValueError(f"{self.train.number} does not arrive at stop {index}")
        return self.at(minutes)
