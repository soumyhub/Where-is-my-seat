"""Priced itineraries: physical legs, the tickets that cover them, and stable IDs.

A *leg* is a physical movement (one train ride or one road transfer). A *ticket* is what
the traveller buys. They differ for smart-ticket strategies: a "book beyond" ticket
covers more than the leg, a "split" leg needs two tickets on the same train.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ..availability import STATUS_RANK, AvailabilityObservation, AvailabilityStatus
from ..models import TrainRun
from ..timeutil import minutes_between
from .explorer import Leg, RideLeg, RoadLeg

ID_VERSION = 1


@dataclass(slots=True)
class Ticket:
    kind: str  # "reserved" | "unreserved"
    run: TrainRun
    from_idx: int
    to_idx: int
    travel_class: str
    quota: str
    strategy: str  # "standard" | "book_beyond" | "upstream_boarding" | "split"
    class_mismatch: bool
    availability: AvailabilityObservation | None
    fare_per_person: int

    @property
    def from_code(self) -> str:
        return self.run.train.stops[self.from_idx].station

    @property
    def to_code(self) -> str:
        return self.run.train.stops[self.to_idx].station

    @property
    def km(self) -> int:
        stops = self.run.train.stops
        return stops[self.to_idx].km - stops[self.from_idx].km

    @property
    def journey_date(self) -> date:
        return self.run.dep_at(self.from_idx).date()

    @property
    def status(self) -> AvailabilityStatus | None:
        return self.availability.status if self.availability else None


@dataclass(slots=True)
class TicketIdea:
    """A backup ticket worth checking on IRCTC when the plain ticket is waitlisted.

    Used when seat availability is not live: the app cannot know which option has seats,
    so it tells the traveller exactly which tickets to try, in order.
    """

    strategy: str  # "book_beyond" | "upstream_boarding" | "split" | "later_boarding"
    title: str
    detail: str
    tickets: list[Ticket]
    extra_road: dict[str, object] | None = None  # for later boarding: how to reach that station


@dataclass(slots=True)
class PricedLeg:
    leg: Leg
    tickets: list[Ticket]
    buffer_before: int | None = None  # minutes of waiting before this leg starts

    @property
    def cost_per_person(self) -> int:
        if isinstance(self.leg, RoadLeg):
            return self.leg.estimate.cost_per_person
        return sum(t.fare_per_person for t in self.tickets)


@dataclass(slots=True)
class Itinerary:
    legs: list[PricedLeg]
    requested_date: date
    travel_date: date
    passengers: int
    preferred_class: str
    origin_key: str
    destination_key: str
    categories: list[str] = field(default_factory=list)
    primary_category: str = "direct"
    headline: str = ""
    why: list[str] = field(default_factory=list)
    fits: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)
    booking_tip: str | None = None
    score: float = 0.0
    availability_score: float = 0.0
    convenience_score: float = 1.0
    connection_quality: str = "none"
    vs_preferred: dict[str, int] | None = None
    ideas: list[TicketIdea] = field(default_factory=list)
    id: str = ""

    # ----- derived ------------------------------------------------------
    @property
    def rides(self) -> list[RideLeg]:
        return [pl.leg for pl in self.legs if isinstance(pl.leg, RideLeg)]

    @property
    def tickets(self) -> list[Ticket]:
        return [t for pl in self.legs for t in pl.tickets]

    @property
    def reserved_tickets(self) -> list[Ticket]:
        return [t for t in self.tickets if t.kind == "reserved"]

    @property
    def depart_at(self) -> datetime:
        return self.legs[0].leg.dep

    @property
    def arrive_at(self) -> datetime:
        return self.legs[-1].leg.arr

    @property
    def total_minutes(self) -> int:
        return minutes_between(self.depart_at, self.arrive_at)

    @property
    def cost_per_person(self) -> int:
        return sum(pl.cost_per_person for pl in self.legs)

    @property
    def cost_total(self) -> int:
        return self.cost_per_person * self.passengers

    @property
    def transfers(self) -> int:
        return len(self.legs) - 1

    @property
    def train_changes(self) -> int:
        return max(0, len(self.rides) - 1)

    @property
    def date_offset(self) -> int:
        return (self.travel_date - self.requested_date).days

    @property
    def has_road(self) -> bool:
        return any(isinstance(pl.leg, RoadLeg) for pl in self.legs)

    @property
    def separate_tickets(self) -> bool:
        return len(self.tickets) + (1 if self.has_road else 0) > 1

    @property
    def overall_status(self) -> str:
        reserved = self.reserved_tickets
        if not reserved:
            return "UNRESERVED"
        worst = min(
            (t.status or AvailabilityStatus.UNKNOWN for t in reserved), key=lambda s: STATUS_RANK[s]
        )
        return worst.value

    @property
    def contains_simulated(self) -> bool:
        return any(r.train.simulated for r in self.rides) or any(
            t.availability is not None and t.availability.is_simulated for t in self.tickets
        )

    def core_key(self) -> tuple[str, ...]:
        return tuple(sorted({t.run.key for t in self.reserved_tickets})) or tuple(
            r.run.key for r in self.rides
        )

    def route_signature(self) -> tuple[Any, ...]:
        return tuple(
            (pl.leg.signature(), tuple((t.from_code, t.to_code, t.travel_class, t.strategy) for t in pl.tickets))
            for pl in self.legs
        )


# ----- stable, stateless itinerary IDs ----------------------------------
def encode_itinerary_id(it: Itinerary) -> str:
    legs: list[list[Any]] = []
    for pl in it.legs:
        leg = pl.leg
        if isinstance(leg, RoadLeg):
            legs.append(["R", leg.from_code, leg.to_code, leg.dep.strftime("%Y-%m-%dT%H:%M"), leg.purpose])
        else:
            tickets = [[t.from_code, t.to_code, t.travel_class, t.strategy] for t in pl.tickets]
            legs.append(["T", leg.train.number, leg.run.start_date.isoformat(), leg.from_code, leg.to_code, tickets])
    payload = {
        "v": ID_VERSION,
        "o": it.origin_key,
        "t": it.destination_key,
        "d": it.requested_date.isoformat(),
        "p": it.passengers,
        "c": it.preferred_class,
        "l": legs,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_itinerary_id(journey_id: str) -> dict[str, Any]:
    if not journey_id or len(journey_id) > 4000:
        raise ValueError("journey id is empty or too long")
    padded = journey_id + "=" * (-len(journey_id) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except Exception as exc:  # malformed base64 or JSON
        raise ValueError("journey id is not readable") from exc
    if not isinstance(payload, dict) or payload.get("v") != ID_VERSION or not payload.get("l"):
        raise ValueError("journey id has an unsupported format")
    return payload
