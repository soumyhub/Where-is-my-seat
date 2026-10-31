"""Provider-independent seat-availability interface.

Availability is kept completely separate from the static timetable: a timetable only
says a train *runs*; it never implies a seat. Every observation records where it came
from, when it was observed, and whether it is live or simulated.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class AvailabilityStatus(str, Enum):
    CONFIRMED = "CONFIRMED"  # seats available to book as confirmed
    RAC = "RAC"  # reservation against cancellation (shared berth)
    WAITLISTED = "WAITLISTED"
    UNAVAILABLE = "UNAVAILABLE"  # regret / not available / booking closed
    UNKNOWN = "UNKNOWN"  # not checked, provider missing or provider error


# Higher is better. UNKNOWN ranks above waitlists because it may be anything.
STATUS_RANK = {
    AvailabilityStatus.UNAVAILABLE: 0,
    AvailabilityStatus.WAITLISTED: 1,
    AvailabilityStatus.UNKNOWN: 2,
    AvailabilityStatus.RAC: 3,
    AvailabilityStatus.CONFIRMED: 4,
}


@dataclass(frozen=True, slots=True)
class TicketQuery:
    train_number: str
    journey_date: date  # date the train departs the ticket's boarding station
    from_code: str
    to_code: str
    travel_class: str
    quota: str = "GN"
    passengers: int = 1


@dataclass(frozen=True, slots=True)
class AvailabilityObservation:
    status: AvailabilityStatus
    count: int | None
    source: str
    observed_at: datetime
    is_live: bool
    is_simulated: bool
    note: str | None = None

    @property
    def label(self) -> str:
        n = self.count
        if self.status is AvailabilityStatus.CONFIRMED:
            return f"AVL {n}" if n is not None else "AVAILABLE"
        if self.status is AvailabilityStatus.RAC:
            return f"RAC {n}" if n is not None else "RAC"
        if self.status is AvailabilityStatus.WAITLISTED:
            return f"WL {n}" if n is not None else "WL"
        if self.status is AvailabilityStatus.UNAVAILABLE:
            return "REGRET"
        return "NOT CHECKED"

    @property
    def display(self) -> str:
        base = {
            AvailabilityStatus.CONFIRMED: "Available",
            AvailabilityStatus.RAC: "RAC",
            AvailabilityStatus.WAITLISTED: "Waitlisted",
            AvailabilityStatus.UNAVAILABLE: "Not available",
            AvailabilityStatus.UNKNOWN: "Unknown — not checked",
        }[self.status]
        if self.count is not None and self.status is not AvailabilityStatus.UNKNOWN:
            base = f"{base} · {self.label}"
        if self.is_simulated:
            return f"{base} (simulated)"
        if not self.is_live:
            return f"{base} (not live)"
        return base


class AvailabilityProvider(ABC):
    """Implement this for any authorized availability source."""

    name: str = "provider"
    is_live: bool = False
    is_simulated: bool = False

    @abstractmethod
    def check(self, query: TicketQuery) -> AvailabilityObservation: ...

    def describe(self) -> dict[str, object]:
        return {"name": self.name, "is_live": self.is_live, "is_simulated": self.is_simulated}


class ProviderError(RuntimeError):
    """A provider failed; callers must degrade to UNKNOWN, never to CONFIRMED."""


class ProviderNotConfigured(ProviderError):
    pass
