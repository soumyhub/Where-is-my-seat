"""Search parameters, tunable options and hard limits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..stations import Place

SORT_MODES = ("best", "cheapest", "fastest", "fewest_transfers")
CLASS_CHOICES = ("SL", "3A", "2A", "1A", "CC", "2S", "ANY")


@dataclass(frozen=True)
class SearchLimits:
    """Hard bounds that keep every search finite, whatever the network size."""

    max_rides: int = 3  # train rides per itinerary
    max_expansions: int = 60_000  # (train run, alighting stop) pairs examined
    max_frontier: int = 600  # partial journeys carried into the next round
    max_labels_per_station: int = 24  # partial journeys kept per station per round
    max_labels_per_run: int = 3  # ...of which at most this many arrived on the same train run
    max_candidates: int = 300  # complete routes collected before pricing
    max_results: int = 30  # itineraries returned
    max_per_core: int = 2  # itineraries sharing the same reserved trains
    strategy_candidates: int = 40  # routes on which smart-ticket strategies are tried
    max_split_points: int = 6  # intermediate halts tried for a split ticket
    max_availability_checks: int = 800
    time_budget_seconds: float = 4.0


@dataclass(frozen=True)
class SearchOptions:
    min_transfer_minutes: int = 30  # same-station train-to-train change
    max_wait_minutes: int = 360
    feeder_buffer_minutes: int = 30  # be at the boarding station this early after a road feeder
    exit_buffer_minutes: int = 10  # leave the station before a road leg starts
    nearby_origin_radius_km: float = 100.0
    nearby_destination_radius_km: float = 60.0
    max_nearby_stations: int = 6  # closest served stations used as feeders / onward points
    detour_factor: float = 1.8
    detour_slack_km: float = 60.0
    progress_slack_km: float = 50.0
    max_unreserved_km: int = 200
    default_max_duration_minutes: int = 72 * 60  # Kanyakumari to Jammu takes ~3 days
    comfortable_buffer_minutes: int = 45


@dataclass(frozen=True)
class SearchParams:
    origin: Place
    destination: Place
    travel_date: date
    passengers: int = 1
    travel_class: str = "3A"
    max_budget: int | None = None  # per person, INR
    max_duration_minutes: int | None = None
    max_transfers: int = 2
    flexible_days: int = 0
    include_nearby: bool = True
    allow_unreserved: bool = True
    smart_tickets: bool = True
    sort: str = "best"
