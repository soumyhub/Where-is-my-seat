"""Time helpers. Railway times are Indian Standard Time, handled as naive datetimes."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """Current wall-clock time in IST (naive)."""

    def now(self) -> datetime:
        return datetime.now(IST).replace(tzinfo=None, second=0, microsecond=0)


@dataclass
class FixedClock:
    """Deterministic clock for tests and reproducible demos."""

    current: datetime

    def now(self) -> datetime:
        return self.current


def parse_hhmm(value: str) -> int:
    hours, minutes = value.split(":")
    h, m = int(hours), int(minutes)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"invalid time {value!r}")
    return h * 60 + m


def minutes_between(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


def to_iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M")


def format_clock(value: datetime) -> str:
    return value.strftime("%H:%M")


def format_day(value: date) -> str:
    return f"{value.strftime('%a')} {value.day} {value.strftime('%b')}"


def format_duration(minutes: int) -> str:
    hours, mins = divmod(max(0, int(minutes)), 60)
    if hours and mins:
        return f"{hours}h {mins:02d}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def daterange(start: date, end: date) -> Iterator[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)
