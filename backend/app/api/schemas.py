"""Validated request and response schemas for the HTTP API."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ClassChoice = Literal["SL", "3A", "2A", "1A", "CC", "2S", "ANY"]
ReservedClass = Literal["SL", "3A", "2A", "1A", "CC", "2S", "3E", "EC", "FC"]
SortChoice = Literal["best", "cheapest", "fastest", "fewest_transfers"]
Status = Literal["CONFIRMED", "RAC", "WAITLISTED", "UNAVAILABLE", "UNKNOWN"]
OverallStatus = Literal["CONFIRMED", "RAC", "WAITLISTED", "UNAVAILABLE", "UNKNOWN", "UNRESERVED"]


# ----- requests -----------------------------------------------------------
class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: str = Field(min_length=2, max_length=40, description="Station code, city:<key> or name")
    destination: str = Field(min_length=2, max_length=40)
    date: dt.date
    passengers: int = Field(1, ge=1, le=6)
    travel_class: ClassChoice = "3A"
    max_budget: int | None = Field(None, ge=50, le=100_000, description="Per person, INR")
    max_duration_hours: float | None = Field(None, ge=1, le=48)
    max_transfers: int = Field(2, ge=0, le=3)
    flexible_days: int = Field(0, ge=0, le=3)
    include_nearby: bool = True
    allow_unreserved: bool = True
    smart_tickets: bool = True
    sort: SortChoice = "best"


class AvailabilityCheckItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    train_number: str = Field(min_length=1, max_length=20)
    journey_date: dt.date = Field(description="Date the train leaves from_code")
    from_code: str = Field(min_length=1, max_length=8)
    to_code: str = Field(min_length=1, max_length=8)
    travel_class: ReservedClass


class AvailabilityCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passengers: int = Field(1, ge=1, le=6)
    checks: list[AvailabilityCheckItem] = Field(min_length=1, max_length=20)


# ----- shared pieces ------------------------------------------------------
class StationRef(BaseModel):
    code: str
    name: str
    city: str


class PlaceOut(BaseModel):
    kind: Literal["station", "city"]
    key: str
    code: str | None
    name: str
    subtitle: str
    city: str
    codes: list[str]
    served: bool = True  # False: no timetable train stops here; searches use the nearest stations


class AvailabilityOut(BaseModel):
    status: Status
    count: int | None
    label: str
    display: str
    source: str
    observed_at: str
    is_live: bool
    is_simulated: bool
    stale: bool
    note: str | None


class FareOut(BaseModel):
    per_person: int
    total: int
    is_estimate: bool
    basis: str


class BookingOut(BaseModel):
    channel: str
    url: str | None
    bookable: bool
    note: str


class TicketOut(BaseModel):
    kind: Literal["reserved", "unreserved"]
    train_number: str
    from_station: StationRef
    to_station: StationRef
    journey_date: str
    travel_class: str
    class_label: str
    quota: str
    strategy: Literal["standard", "book_beyond", "upstream_boarding", "split", "later_boarding"]
    class_mismatch: bool
    distance_km: int
    availability: AvailabilityOut | None
    fare: FareOut
    booking: BookingOut


class IdeaOut(BaseModel):
    strategy: Literal["book_beyond", "upstream_boarding", "split", "later_boarding"]
    title: str
    detail: str
    tickets: list[TicketOut]
    extra_road: dict[str, Any] | None


class StopOut(BaseModel):
    code: str
    name: str
    arr: str | None
    dep: str | None
    km: int
    day: int
    role: Literal["board", "alight", "halt"]


class TrainOut(BaseModel):
    number: str
    name: str
    category: str
    runs_on: str
    classes: list[str]
    unreserved: bool
    superfast: bool
    simulated: bool
    source: str
    notes: list[str]
    start_date: str | None = None  # the day this run leaves its first station (for live status)


class RoadOut(BaseModel):
    mode: str
    km: int
    cost_per_person: int
    basis: str


class LegOut(BaseModel):
    kind: Literal["train", "road"]
    purpose: Literal["ride", "feeder", "transfer", "onward"]
    from_station: StationRef
    to_station: StationRef
    depart_at: str
    arrive_at: str
    duration_minutes: int
    day_change: int
    distance_km: int
    train: TrainOut | None
    road: RoadOut | None
    tickets: list[TicketOut]
    stops: list[StopOut]
    buffer_before_minutes: int | None
    instructions: list[str]
    cost_per_person: int
    class_fares: dict[str, int]


class VsPreferredOut(BaseModel):
    extra_cost_per_person: int
    extra_minutes: int
    arrival_delta_minutes: int


class ItineraryOut(BaseModel):
    id: str
    categories: list[str]
    primary_category: str
    headline: str
    legs: list[LegOut]
    depart_at: str
    arrive_at: str
    total_minutes: int
    travel_date: str
    date_offset: int
    passengers: int
    cost_per_person: int
    cost_total: int
    transfers: int
    train_changes: int
    tickets_count: int
    reserved_tickets_count: int
    separate_tickets: bool
    single_train: bool
    overall_status: OverallStatus
    availability_score: float
    convenience_score: float
    score: float
    connection_quality: Literal["none", "comfortable", "tight", "long_wait"]
    why: list[str]
    fits: list[str]
    warnings: list[str]
    tips: list[str]
    booking_tip: str | None
    vs_preferred: VsPreferredOut | None
    ideas: list[IdeaOut]
    contains_simulated: bool
    contains_estimates: bool


class DataNoticeOut(BaseModel):
    mode: Literal["demo", "timetable", "live"]
    label: str
    details: list[str]
    timetable_source: str
    timetable_version: str
    timetable_updated: str
    timetable_simulated: bool
    availability_source: str
    availability_live: bool
    availability_simulated: bool
    fare_basis: str
    coverage: str
    provider_note: str | None
    live_checks: bool = False
    live_checks_source: str | None = None


class MapStopOut(BaseModel):
    code: str
    name: str
    lat: float
    lon: float
    role: Literal["board", "alight", "halt", "road"]


class MapSegmentOut(BaseModel):
    points: list[list[float]]  # [lat, lon]
    matched: bool  # True: drawn along the track; False: straight line


class MapLegOut(BaseModel):
    kind: Literal["train", "road"]
    train_number: str | None
    train_name: str | None
    segments: list[MapSegmentOut]
    stops: list[MapStopOut]


class JourneyMapOut(BaseModel):
    legs: list[MapLegOut]
    bounds: list[list[float]] | None
    track_share: float  # share of train distance drawn along real track
    attribution: str
    available: bool


class LiveUsageOut(BaseModel):
    available: bool
    source: str | None
    monthly_limit: int | None
    used_this_month: int | None
    remaining_this_month: int | None
    blocked_reason: str | None = None  # e.g. the plan does not include seat availability
    tools: bool = False  # live tools (running status, station board, fare, …) are set up
    requests_used: int | None = None  # RailRadar requests in the last 30 days (all features)
    requests_left: int | None = None


class LiveOut(BaseModel):
    data: dict[str, Any]
    source: str
    fetched_at: str
    cached: bool  # True: reused an earlier answer, no request spent
    requests_left: int


class SummaryOut(BaseModel):
    headline: str
    subline: str
    direct_count: int
    direct_confirmed: int
    alternatives_with_seats: int
    best_bookable_id: str | None
    preferred_id: str | None


class DateStripOut(BaseModel):
    date: str
    label: str
    best_status: OverallStatus | None
    options: int
    bookable_options: int
    cheapest_bookable: int | None


class RushOut(BaseModel):
    level: str
    festival: str
    festival_date: str
    message: str


class QueryOut(BaseModel):
    origin: PlaceOut
    destination: PlaceOut
    date: str
    passengers: int
    travel_class: str
    max_budget: int | None
    max_duration_hours: float | None
    max_transfers: int
    flexible_days: int
    include_nearby: bool
    allow_unreserved: bool
    smart_tickets: bool
    sort: str


# ----- responses ----------------------------------------------------------
class SearchResponse(BaseModel):
    query: QueryOut
    data_notice: DataNoticeOut
    summary: SummaryOut
    preferred: ItineraryOut | None
    itineraries: list[ItineraryOut]
    date_strip: list[DateStripOut] | None
    rush: RushOut | None
    hidden: dict[str, int]
    no_results_reason: str | None
    no_results_message: str | None
    search_stats: dict[str, Any]
    generated_at: str


class JourneyResponse(BaseModel):
    itinerary: ItineraryOut
    origin: PlaceOut
    destination: PlaceOut
    data_notice: DataNoticeOut
    checked_at: str


class AvailabilityCheckResult(BaseModel):
    request: AvailabilityCheckItem
    ok: bool
    error: str | None
    availability: AvailabilityOut | None


class AvailabilityCheckResponse(BaseModel):
    results: list[AvailabilityCheckResult]
    data_notice: DataNoticeOut
    checked_at: str
    live_usage: LiveUsageOut


class SampleSearchOut(BaseModel):
    id: str
    title: str
    description: str
    shows: list[str]
    from_name: str
    to_name: str
    request: dict[str, Any]


class MetaResponse(BaseModel):
    app: str
    version: str
    today: str
    demo_date: str
    max_advance_days: int
    classes: list[dict[str, str]]
    samples: list[SampleSearchOut]
    data_notice: DataNoticeOut
    rush_periods: list[dict[str, Any]]
    limits: dict[str, Any]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    mode: str
    stations: int
    trains: int
    availability_provider: str
    availability_live: bool
    timetable_version: str


class ErrorBody(BaseModel):
    code: str
    message: str
    hint: str | None = None
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
