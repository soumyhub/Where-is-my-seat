"""Multi-criteria ranking: seat availability, duration, cost, transfers and how
comfortable the connections are."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from ..availability import AvailabilityStatus
from ..timeutil import minutes_between
from .explorer import RideLeg, RoadLeg
from .itinerary import Itinerary, Ticket
from .params import SearchOptions

WEIGHTS = {"availability": 0.42, "duration": 0.22, "cost": 0.14, "transfers": 0.10, "convenience": 0.12}


def ticket_weight(ticket: Ticket) -> float:
    """How likely this ticket gets the traveller on board, in [0, 1]."""
    if ticket.kind == "unreserved":
        return 0.8 if ticket.km <= 100 else 0.6
    obs = ticket.availability
    if obs is None:
        return 0.25
    if obs.status is AvailabilityStatus.CONFIRMED:
        return 1.0
    if obs.status is AvailabilityStatus.RAC:
        return 0.6
    if obs.status is AvailabilityStatus.UNKNOWN:
        return 0.25
    if obs.status is AvailabilityStatus.UNAVAILABLE:
        return 0.0
    position = obs.count if obs.count is not None else 99
    if position <= 5:
        return 0.4
    if position <= 15:
        return 0.25
    if position <= 40:
        return 0.12
    return 0.05


def connections(it: Itinerary) -> list[dict[str, Any]]:
    """Every train-to-train change, with the slack left after any road transfer."""
    out: list[dict[str, Any]] = []
    legs = [pl.leg for pl in it.legs]
    for i, leg in enumerate(legs):
        if not isinstance(leg, RideLeg):
            continue
        j = i + 1
        road_minutes = 0
        while j < len(legs) and isinstance(legs[j], RoadLeg):
            road_minutes += legs[j].minutes
            j += 1
        if j >= len(legs):
            continue
        nxt = legs[j]
        assert isinstance(nxt, RideLeg)
        gap = minutes_between(leg.arr, nxt.dep)
        out.append(
            {
                "arrive": leg,
                "depart": nxt,
                "gap": gap,
                "slack": gap - road_minutes,
                "station_change": road_minutes > 0,
            }
        )
    return out


def _overlaps_night(start: datetime, end: datetime) -> bool:
    cursor = start
    while cursor < end:
        if cursor.hour < 5:
            return True
        cursor += timedelta(minutes=30)
    return False


def assess(it: Itinerary, options: SearchOptions) -> None:
    """Set availability score, convenience score and connection quality."""
    tickets = it.tickets
    it.availability_score = min((ticket_weight(t) for t in tickets), default=0.0)
    score = 1.0
    quality = "none"
    for c in connections(it):
        slack = c["slack"]
        if slack < options.comfortable_buffer_minutes:
            score -= 0.35
            quality = "tight"
        elif slack < 60:
            score -= 0.10
        elif slack > 300:
            score -= 0.30
        elif slack > 180:
            score -= 0.15
        if quality != "tight":
            if slack > 240:
                quality = "long_wait"
            elif quality == "none":
                quality = "comfortable"
        if _overlaps_night(c["arrive"].arr, c["depart"].dep):
            score -= 0.15
    road_legs = [pl.leg for pl in it.legs if isinstance(pl.leg, RoadLeg)]
    score -= 0.12 * len(road_legs)  # every road leg is extra effort and only an estimate
    if sum(leg.minutes for leg in road_legs) > 120:
        score -= 0.10
    if it.depart_at.hour < 4 or (it.depart_at.hour == 4 and it.depart_at.minute < 30):
        score -= 0.10
    if 1 <= it.arrive_at.hour < 5 and it.total_minutes < 12 * 60:
        score -= 0.08  # a short trip that drops you at a station in the small hours
    it.convenience_score = round(max(0.0, min(1.0, score)), 3)
    it.connection_quality = quality


def score_all(items: list[Itinerary]) -> None:
    if not items:
        return
    min_minutes = min(it.total_minutes for it in items)
    min_cost = min(it.cost_per_person for it in items)
    for it in items:
        s = (
            WEIGHTS["availability"] * it.availability_score
            + WEIGHTS["duration"] * (min_minutes / max(it.total_minutes, 1))
            + WEIGHTS["cost"] * (min_cost / max(it.cost_per_person, 1))
            + WEIGHTS["transfers"] * (1 / (1 + it.transfers))
            + WEIGHTS["convenience"] * it.convenience_score
        )
        s -= 0.12 * abs(it.date_offset)  # changing the travel day is a big ask
        s -= 0.03 * max(0, len(it.reserved_tickets) - 1)
        if any(t.class_mismatch for t in it.reserved_tickets):
            s -= 0.04
        it.score = round(max(0.0, s), 4)


SORT_KEYS: dict[str, Callable[[Itinerary], tuple[float, ...]]] = {
    "best": lambda it: (-it.score, it.total_minutes, it.cost_per_person),
    "cheapest": lambda it: (it.cost_per_person, -it.score, it.total_minutes),
    "fastest": lambda it: (it.total_minutes, -it.score, it.cost_per_person),
    "fewest_transfers": lambda it: (it.transfers, -it.score, it.total_minutes),
}


def sort_itineraries(items: list[Itinerary], mode: str) -> list[Itinerary]:
    return sorted(items, key=SORT_KEYS.get(mode, SORT_KEYS["best"]))


def diversify(items: list[Itinerary], max_per_core: int) -> list[Itinerary]:
    """Keep at most ``max_per_core`` itineraries that rely on the same reserved trains
    in the same way (same kind of alternative, same ticket strategy)."""
    counts: dict[tuple[str, ...], int] = {}
    out: list[Itinerary] = []
    for it in items:
        strategies = tuple(sorted({t.strategy for t in it.tickets}))
        key = it.core_key() + (it.primary_category,) + strategies
        if counts.get(key, 0) >= max_per_core:
            continue
        counts[key] = counts.get(key, 0) + 1
        out.append(it)
    return out
