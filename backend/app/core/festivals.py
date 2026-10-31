"""Festival and holiday rush calendar (approximate dates, used only for hints)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .timeutil import format_day

_LEVEL_FACTOR = {"high": 0.32, "medium": 0.16}


@dataclass(frozen=True, slots=True)
class Festival:
    name: str
    date: date
    before: int  # rush days before the festival
    after: int  # rush days after (return rush)
    level: str  # "high" | "medium"

    def covers(self, day: date) -> bool:
        return self.date - timedelta(days=self.before) <= day <= self.date + timedelta(days=self.after)


@dataclass(frozen=True, slots=True)
class RushInfo:
    level: str
    festival: str
    festival_date: date
    message: str


class RushCalendar:
    def __init__(self, festivals: list[Festival]) -> None:
        self._festivals = sorted(festivals, key=lambda f: f.date)

    def rush_for(self, day: date) -> RushInfo | None:
        matches = [f for f in self._festivals if f.covers(day)]
        if not matches:
            return None
        festival = min(matches, key=lambda f: (f.level != "high", abs((f.date - day).days)))
        delta = (festival.date - day).days
        if delta > 0:
            when = f"{delta} day{'s' if delta != 1 else ''} before {festival.name}"
        elif delta < 0:
            when = f"{-delta} day{'s' if delta != -1 else ''} after {festival.name}"
        else:
            when = f"on {festival.name}"
        return RushInfo(
            level=festival.level,
            festival=festival.name,
            festival_date=festival.date,
            message=(
                f"Peak travel: {format_day(day)} is {when} ({format_day(festival.date)}). "
                "Expect long waitlists — alternatives matter most now."
            ),
        )

    def factor(self, day: date) -> float:
        """Demand pressure in [0, 0.32] used by the availability simulator."""
        rush = self.rush_for(day)
        return _LEVEL_FACTOR.get(rush.level, 0.0) if rush else 0.0

    def upcoming(self, today: date, days: int) -> list[Festival]:
        horizon = today + timedelta(days=days)
        return [f for f in self._festivals if today - timedelta(days=f.after) <= f.date <= horizon]
