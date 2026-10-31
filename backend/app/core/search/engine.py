"""Search orchestration: resolve ends -> explore routes -> ticket & price -> validate ->
explain -> rank -> filter. Pure Python; the web layer only translates in and out."""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from ..availability import STATUS_RANK, AvailabilityService, AvailabilityStatus
from ..fares import FareEstimator
from ..festivals import RushCalendar
from ..graph import TimeDependentGraph
from ..models import TrainRun
from ..road import RoadEstimator
from ..stations import Place, StationDirectory, UnknownPlaceError
from ..timetable import Timetable
from ..timeutil import Clock, format_day
from .explain import ExplainContext, classify, explain, main_ride, primary_category
from .explorer import Endpoints, ExploreStats, Leg, RideLeg, RoadLeg, RouteCandidate, RouteExplorer
from .itinerary import Itinerary, PricedLeg, decode_itinerary_id, encode_itinerary_id
from .params import SearchLimits, SearchOptions, SearchParams
from .ranking import assess, diversify, score_all, sort_itineraries
from .ticketing import TicketPlanner
from .validation import InvalidItinerary, validate_route, validate_tickets


class SearchRequestError(ValueError):
    """The request itself is not searchable (bad dates, same ends...)."""

    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


@dataclass
class SearchResult:
    params: SearchParams
    ends: Endpoints
    itineraries: list[Itinerary]
    preferred: Itinerary | None
    summary: dict[str, Any]
    hidden: dict[str, int]
    date_strip: list[dict[str, Any]] | None
    rush: dict[str, Any] | None
    no_results_reason: str | None
    no_results_message: str | None
    stats: dict[str, Any] = field(default_factory=dict)


class JourneySearchEngine:
    def __init__(
        self,
        *,
        directory: StationDirectory,
        timetable: Timetable,
        road: RoadEstimator,
        fares: FareEstimator,
        availability: AvailabilityService,
        rush: RushCalendar,
        clock: Clock,
        options: SearchOptions | None = None,
        limits: SearchLimits | None = None,
        max_advance_days: int = 60,
    ) -> None:
        self.directory = directory
        self.timetable = timetable
        self.road = road
        self.fares = fares
        self.availability = availability
        self.rush = rush
        self.clock = clock
        self.options = options or SearchOptions()
        self.limits = limits or SearchLimits()
        self.max_advance_days = max_advance_days
        self.graph = TimeDependentGraph(timetable, directory, road)
        self.explorer = RouteExplorer(self.graph, self.options, self.limits)

    @property
    def availability_informative(self) -> bool:
        """True when seat status comes from a live or simulated source (not just 'unknown')."""
        provider = self.availability.provider
        return bool(provider.is_live or provider.is_simulated)

    # ----- request checks -----------------------------------------------
    def resolve_place(self, text: str) -> Place:
        return self.directory.resolve(text)

    def check_request(self, params: SearchParams) -> None:
        o, t = params.origin, params.destination
        if o.key == t.key or set(o.codes) & set(t.codes):
            raise SearchRequestError(
                "SAME_ORIGIN_DESTINATION",
                "Origin and destination are the same place.",
                "Pick two different stations or cities.",
            )
        today = self.clock.now().date()
        if params.travel_date < today:
            raise SearchRequestError(
                "INVALID_DATE", "That travel date is in the past.", "Choose today or a later date."
            )
        if params.travel_date > today + timedelta(days=self.max_advance_days):
            raise SearchRequestError(
                "INVALID_DATE",
                f"Reservations open only {self.max_advance_days} days ahead.",
                f"Choose a date on or before {format_day(today + timedelta(days=self.max_advance_days))}.",
            )

    def _unserved_note(self, params: SearchParams, ends: Endpoints) -> tuple[str, str] | None:
        """Headline and subline when From or To has no train in the timetable."""
        d = self.directory
        parts = []
        if not any(self.graph.serves(c) for c in ends.origin_zero):
            near = sorted(ends.origin_feeders.values(), key=lambda e: e.km)[:3]
            listed = ", ".join(f"{d.name(e.to_code)} ({e.km} km)" for e in near)
            parts.append((params.origin.name, f"Start from the nearest stations with trains: {listed}." if near else ""))
        if not any(self.timetable.serves_arrivals(c) for c in ends.dest_zero):
            near = sorted(ends.dest_onward.values(), key=lambda e: e.km)[:3]
            listed = ", ".join(f"{d.name(e.from_code)} ({e.km} km)" for e in near)
            parts.append((params.destination.name, f"Get off at the nearest stations with trains: {listed}." if near else ""))
        if not parts:
            return None
        names = " or ".join(name for name, _ in parts)
        return (
            f"No train in our timetable stops at {names}",
            " ".join(text for _, text in parts if text) + " Road times are rough estimates.",
        )

    # ----- endpoints ----------------------------------------------------
    def endpoints(self, origin: Place, destination: Place, include_nearby: bool) -> Endpoints:
        d, opts = self.directory, self.options
        origin_zero = frozenset(origin.codes)
        feeders = {}
        if origin.kind == "station":
            for code in d.stations_in_city(origin.city):
                if code != origin.anchor and (est := self.road.estimate(origin.anchor, code)):
                    feeders[code] = est
        # A station with no timetable train always starts from the nearest stations that have one.
        origin_unserved = not any(self.graph.serves(c) for c in origin_zero)
        if include_nearby or origin_unserved:
            exclude = set(origin_zero) | set(d.stations_in_city(origin.city))
            radius = max(opts.nearby_origin_radius_km, UNSERVED_RADIUS_KM if origin_unserved else 0)
            served = [c for c, _ in d.nearby(origin.anchor, radius, exclude) if self.graph.serves(c)]
            for code in served[: opts.max_nearby_stations]:
                if est := self.road.estimate(origin.anchor, code):
                    feeders.setdefault(code, est)
        dest_zero = frozenset(destination.codes)
        onward = {}
        if destination.kind == "station":
            for code in d.stations_in_city(destination.city):
                if code != destination.anchor and (est := self.road.estimate(code, destination.anchor)):
                    onward[code] = est
        dest_unserved = not any(self.timetable.serves_arrivals(c) for c in dest_zero)
        if include_nearby or dest_unserved:
            exclude = set(dest_zero) | set(d.stations_in_city(destination.city))
            radius = max(opts.nearby_destination_radius_km, UNSERVED_RADIUS_KM if dest_unserved else 0)
            served = [
                c
                for c, _ in d.nearby(destination.anchor, radius, exclude)
                if self.timetable.serves_arrivals(c)
            ]
            for code in served[: opts.max_nearby_stations]:
                if est := self.road.estimate(code, destination.anchor):
                    onward.setdefault(code, est)
        feeders = {c: e for c, e in feeders.items() if c not in dest_zero and c not in onward}
        onward = {c: e for c, e in onward.items() if c not in origin_zero and c not in feeders}
        return Endpoints(
            origin_label=origin.name,
            destination_label=destination.name,
            origin_anchor=origin.anchor,
            dest_anchor=destination.anchor,
            origin_zero=origin_zero,
            origin_feeders=feeders,
            dest_zero=dest_zero,
            dest_onward=onward,
        )

    def _window(self, day: date) -> tuple[datetime, datetime]:
        start = datetime.combine(day, time())
        end = datetime.combine(day, time(23, 59))
        earliest_today = self.clock.now() + timedelta(minutes=30)
        return max(start, earliest_today), end

    def _dates(self, params: SearchParams) -> list[date]:
        today = self.clock.now().date()
        last = today + timedelta(days=self.max_advance_days)
        days = [params.travel_date]
        for k in range(1, params.flexible_days + 1):
            for d in (params.travel_date - timedelta(days=k), params.travel_date + timedelta(days=k)):
                if today <= d <= last:
                    days.append(d)
        return days

    # ----- search -------------------------------------------------------
    def search(self, params: SearchParams) -> SearchResult:
        self.check_request(params)
        started = _time.monotonic()
        deadline = started + self.limits.time_budget_seconds
        ends = self.endpoints(params.origin, params.destination, params.include_nearby)
        rush_info = self.rush.rush_for(params.travel_date)
        rush = (
            {
                "level": rush_info.level,
                "festival": rush_info.festival,
                "festival_date": rush_info.festival_date.isoformat(),
                "message": rush_info.message,
            }
            if rush_info
            else None
        )

        origin_codes = set(ends.origin_zero) | set(ends.origin_feeders)
        dest_codes = set(ends.dest_zero) | set(ends.dest_onward)
        if not any(self.graph.serves(c) for c in origin_codes):
            return self._empty(
                params, ends, rush, "NO_TIMETABLE_AT_ORIGIN",
                f"The timetable has no trains departing {params.origin.name} or stations near it.",
            )
        if not any(self.timetable.serves_arrivals(c) for c in dest_codes):
            return self._empty(
                params, ends, rush, "NO_TIMETABLE_AT_DESTINATION",
                f"The timetable has no trains arriving at {params.destination.name} or stations near it.",
            )

        stats = ExploreStats()
        max_duration = params.max_duration_minutes or self.options.default_max_duration_minutes
        candidates: list[RouteCandidate] = []
        searched_dates = self._dates(params)
        for day in searched_dates:
            window_start, window_end = self._window(day)
            if window_start > window_end:
                continue
            candidates += self.explorer.explore(
                ends,
                day,
                window_start,
                window_end,
                max_transfers=params.max_transfers,
                max_duration_minutes=max_duration,
                allow_unreserved=params.allow_unreserved,
                deadline=deadline,
                stats=stats,
            )
            if stats.truncated and stats.truncated_reason == "time budget reached":
                break

        session = self.availability.session(self.limits.max_availability_checks)
        informative = self.availability_informative
        planner = TicketPlanner(session, self.fares, self.directory, params, self.limits, informative)
        priced = planner.price(candidates)

        valid: list[Itinerary] = []
        invalid = 0
        for it in priced:
            try:
                self._validate(it)
            except InvalidItinerary:
                invalid += 1
                continue
            it.categories = classify(it, ends)
            it.primary_category = primary_category(it.categories)
            assess(it, self.options)
            valid.append(it)

        merged = len(valid)
        valid = _merge_near_duplicates(valid)
        merged -= len(valid)
        before_dominance = len(valid)
        valid = _drop_dominated(valid, ends)
        if not informative:
            valid = _drop_impractical(valid)
        dominated = before_dominance - len(valid)

        preferred = _pick_preferred(valid, params)
        ctx = ExplainContext(
            directory=self.directory,
            ends=ends,
            params=params,
            options=self.options,
            preferred=preferred,
            informative=informative,
            direct_by_run={it.rides[0].run.key: it for it in valid if it.primary_category == "direct"},
            standard_labels={
                (t.run.key, t.from_code, t.to_code, t.travel_class): t.availability.label
                for it in valid
                for t in it.reserved_tickets
                if t.strategy == "standard" and t.availability is not None
            },
        )
        for it in valid:
            explain(it, ctx)
            if not informative and it.primary_category == "direct" and len(it.rides) == 1:
                main = it.legs[0]
                it.ideas = planner.ideas(main.leg, main.tickets[0], ends.origin_feeders)

        visible, hidden = _apply_filters(valid, params)
        score_all(visible)
        ranked = diversify(sort_itineraries(visible, params.sort), self.limits.max_per_core)
        ranked = ranked[: self.limits.max_results]
        for it in ranked:
            it.id = encode_itinerary_id(it)
        if preferred is not None and not preferred.id:
            preferred.id = encode_itinerary_id(preferred)

        reason, message = None, None
        if not ranked:
            if valid:
                reason = "ALL_FILTERED"
                message = "Options exist, but none fit your budget or duration limits. Try relaxing them."
            elif stats.truncated:
                reason = "SEARCH_LIMIT_REACHED"
                message = "The search hit its limits before finding a route. Try fewer transfers or a specific station."
            else:
                reason = "NO_ROUTE_WITHIN_LIMITS"
                message = (
                    "No route fits these limits in the timetable. Allow more transfers, nearby stations "
                    "or flexible dates."
                )

        elapsed_ms = int((_time.monotonic() - started) * 1000)
        return SearchResult(
            params=params,
            ends=ends,
            itineraries=ranked,
            preferred=preferred,
            summary=_summary(ranked, valid, preferred, params, informative, self._unserved_note(params, ends)),
            hidden=hidden,
            date_strip=_date_strip(valid, searched_dates) if params.flexible_days else None,
            rush=rush,
            no_results_reason=reason,
            no_results_message=message,
            stats={
                "routes_found": len(candidates),
                "itineraries_priced": len(priced),
                "invalid_dropped": invalid,
                "near_duplicates_merged": merged,
                "dominated_dropped": dominated,
                "duplicates_removed": stats.duplicates_removed,
                "departures_scanned": stats.departures_scanned,
                "expansions": stats.expansions,
                "labels_created": stats.labels_created,
                "labels_pruned": stats.labels_pruned,
                "rejected_short_connections": stats.rejected_short_connections,
                "rejected_examples": stats.rejected_examples,
                "loops_prevented": stats.loops_prevented,
                "detour_pruned": stats.detour_pruned,
                "duration_pruned": stats.duration_pruned,
                "availability_checks": session.calls,
                "availability_errors": session.errors,
                "truncated": stats.truncated,
                "truncated_reason": stats.truncated_reason,
                "dates_searched": [d.isoformat() for d in searched_dates],
                "elapsed_ms": elapsed_ms,
                "limits": {
                    "max_transfers": params.max_transfers,
                    "max_rides": self.limits.max_rides,
                    "max_expansions": self.limits.max_expansions,
                    "max_candidates": self.limits.max_candidates,
                    "min_transfer_minutes": self.options.min_transfer_minutes,
                    "max_wait_minutes": self.options.max_wait_minutes,
                },
            },
        )

    def _validate(self, it: Itinerary) -> None:
        validate_route([pl.leg for pl in it.legs], self.timetable, self.options)
        for pl in it.legs:
            if isinstance(pl.leg, RideLeg):
                validate_tickets(pl.leg, pl.tickets)

    def _empty(self, params, ends, rush, reason: str, message: str) -> SearchResult:
        return SearchResult(
            params=params,
            ends=ends,
            itineraries=[],
            preferred=None,
            summary=_summary([], [], None, params, self.availability_informative, self._unserved_note(params, ends)),
            hidden={"over_budget": 0, "over_duration": 0},
            date_strip=None,
            rush=rush,
            no_results_reason=reason,
            no_results_message=message,
            stats={"routes_found": 0},
        )

    # ----- saved / shared itineraries -----------------------------------
    def resolve_itinerary(self, journey_id: str) -> tuple[Itinerary, Endpoints]:
        """Rebuild an itinerary from its stateless ID and re-check availability."""
        try:
            payload = decode_itinerary_id(journey_id)
            origin = self.directory.resolve(payload["o"])
            destination = self.directory.resolve(payload["t"])
            requested = date.fromisoformat(payload["d"])
            passengers = int(payload["p"])
            travel_class = str(payload["c"])
        except (ValueError, KeyError, TypeError, UnknownPlaceError) as exc:
            raise InvalidItinerary("This journey link is not valid.") from exc
        if not 1 <= passengers <= 6:
            raise InvalidItinerary("This journey link is not valid.")
        legs: list[Leg] = []
        ticket_specs: list[list[list[str]]] = []
        try:
            for row in payload["l"]:
                if row[0] == "R":
                    _, a, b, dep, purpose = row
                    estimate = self.road.estimate(a, b)
                    if estimate is None or purpose not in ("feeder", "transfer", "onward"):
                        raise InvalidItinerary(f"No road estimate between {a} and {b}")
                    legs.append(RoadLeg(estimate, datetime.fromisoformat(dep), purpose))
                    ticket_specs.append([])
                elif row[0] == "T":
                    _, number, start, a, b, tickets = row
                    train = self.timetable.train(number)
                    if train is None:
                        raise InvalidItinerary(f"Train {number} is no longer in the timetable")
                    board, alight = train.index_of(a), train.index_of(b)
                    if board is None or alight is None:
                        raise InvalidItinerary(f"{number} does not halt at {a if board is None else b}")
                    legs.append(RideLeg(TrainRun(train, date.fromisoformat(start)), board, alight))
                    ticket_specs.append(tickets)
                else:
                    raise InvalidItinerary("This journey link is not valid.")
        except (ValueError, TypeError) as exc:
            if isinstance(exc, InvalidItinerary):
                raise
            raise InvalidItinerary("This journey link is not valid.") from exc
        validate_route(legs, self.timetable, self.options)

        params = SearchParams(
            origin=origin,
            destination=destination,
            travel_date=requested,
            passengers=passengers,
            travel_class=travel_class,
        )
        ends = self.endpoints(origin, destination, include_nearby=True)
        session = self.availability.session(self.limits.max_availability_checks)
        planner = TicketPlanner(
            session, self.fares, self.directory, params, self.limits, self.availability_informative
        )
        priced_legs: list[PricedLeg] = []
        for leg, spec in zip(legs, ticket_specs):
            if isinstance(leg, RoadLeg):
                priced_legs.append(PricedLeg(leg, []))
                continue
            if not leg.train.classes:
                priced_legs.append(PricedLeg(leg, [planner.standard_ticket(leg)]))
                continue
            tickets = []
            for a, b, cls, strategy in spec:
                i, j = leg.train.index_of(a), leg.train.index_of(b)
                if i is None or j is None or cls not in leg.train.classes:
                    raise InvalidItinerary("A saved ticket no longer matches the timetable")
                tickets.append(planner.reserved(leg.run, i, j, cls, strategy))
            validate_tickets(leg, tickets)
            priced_legs.append(PricedLeg(leg, tickets))
        travel_day = legs[0].dep.date()
        if abs((travel_day - requested).days) > 3:
            travel_day = requested
        it = planner.build_itinerary(priced_legs, RouteCandidate(tuple(legs), travel_day))
        it.categories = classify(it, ends)
        it.primary_category = primary_category(it.categories)
        assess(it, self.options)
        informative = self.availability_informative
        explain(it, ExplainContext(self.directory, ends, params, self.options, informative=informative))
        if not informative and len(it.rides) == 1 and not it.has_road:
            it.ideas = planner.ideas(it.legs[0].leg, it.legs[0].tickets[0], ends.origin_feeders)
        score_all([it])
        it.id = encode_itinerary_id(it)
        return it, ends


def _merge_near_duplicates(items: list[Itinerary]) -> list[Itinerary]:
    """Same trains, same kind of alternative, same alighting: keep the best one.

    Ties go to the earlier boarding (usually the train's main station in the city).
    """

    def quality(it: Itinerary) -> tuple[float, int, float]:
        return (it.availability_score, -it.transfers, -it.depart_at.timestamp())

    best: dict[tuple[Any, ...], Itinerary] = {}
    order: list[tuple[Any, ...]] = []
    for it in items:
        key = (
            tuple(r.run.key for r in it.rides),
            it.rides[-1].to_code,
            tuple(sorted(it.categories)),
            tuple(t.strategy for t in it.tickets),
            tuple(isinstance(pl.leg, RoadLeg) for pl in it.legs),
        )
        current = best.get(key)
        if current is None:
            best[key] = it
            order.append(key)
        elif quality(it) > quality(current):
            best[key] = it
    return [best[k] for k in order]


_NOT_BOOKABLE = ("WAITLISTED", "UNAVAILABLE", "UNKNOWN")
UNSERVED_RADIUS_KM = 150.0  # how far to look for a station with trains from one without


def _drop_dominated(items: list[Itinerary], ends: Endpoints) -> list[Itinerary]:
    """Remove alternatives that are strictly less useful than a simpler option.

    * A detour (other boarding / destination) on a train that also runs direct is only
      worth showing if it improves the seat situation and is itself bookable.
    * The same trains reached with an extra feeder leg but no better seats are dropped.
    * "Book from an earlier station" makes no sense when that station is where the
      traveller starts, or somewhere the itinerary already passed.
    """
    direct_by_run: dict[str, Itinerary] = {}
    for it in items:
        if it.primary_category == "direct":
            key = it.rides[0].run.key
            if key not in direct_by_run or it.availability_score > direct_by_run[key].availability_score:
                direct_by_run[key] = it
    by_runs: dict[frozenset[str], list[Itinerary]] = {}
    for it in items:
        by_runs.setdefault(frozenset(r.run.key for r in it.rides), []).append(it)

    out: list[Itinerary] = []
    for it in items:
        upstream = [
            (pl, t) for pl in it.legs for t in pl.tickets if t.strategy == "upstream_boarding"
        ]
        if upstream:
            pl, ticket = upstream[0]
            earlier: set[str] = set()
            for other in it.legs:
                if other is pl:
                    break
                earlier.update(other.leg.stations())
            if ticket.from_code in ends.origin_zero or ticket.from_code in earlier:
                continue
        if it.primary_category in ("alternative_boarding", "alternative_destination"):
            direct = direct_by_run.get(main_ride(it).run.key)
            if direct is not None and (
                direct.availability_score >= it.availability_score or it.overall_status in _NOT_BOOKABLE
            ):
                continue
        simpler = [
            other
            for other in by_runs[frozenset(r.run.key for r in it.rides)]
            if other is not it
            and other.transfers < it.transfers
            and other.availability_score >= it.availability_score
            and other.total_minutes <= it.total_minutes + 60
        ]
        if simpler:
            continue
        out.append(it)
    return out


def _drop_impractical(items: list[Itinerary]) -> list[Itinerary]:
    """Without seat data, a slow detour is not a useful 'alternative' to a direct train."""
    directs = [it for it in items if it.primary_category == "direct"]
    if not directs:
        return items
    fastest = min(it.total_minutes for it in directs)
    limit = max(int(fastest * 1.8), fastest + 360)
    out = []
    for it in items:
        roads = sum(isinstance(pl.leg, RoadLeg) for pl in it.legs)
        if it.primary_category == "direct" or (it.total_minutes <= limit and roads <= 1):
            out.append(it)
    return out


def _pick_preferred(items: list[Itinerary], params: SearchParams) -> Itinerary | None:
    direct = [it for it in items if it.primary_category == "direct" and it.date_offset == 0]
    if not direct:
        return None
    matching = [it for it in direct if not any(t.class_mismatch for t in it.reserved_tickets)]
    pool = matching or direct
    return min(pool, key=lambda it: (it.total_minutes, it.depart_at))


def _apply_filters(items: list[Itinerary], params: SearchParams) -> tuple[list[Itinerary], dict[str, int]]:
    hidden = {"over_budget": 0, "over_duration": 0}
    visible: list[Itinerary] = []
    for it in items:
        if params.max_budget is not None and it.cost_per_person > params.max_budget:
            hidden["over_budget"] += 1
            continue
        if params.max_duration_minutes is not None and it.total_minutes > params.max_duration_minutes:
            hidden["over_duration"] += 1
            continue
        visible.append(it)
    return visible, hidden


def _is_bookable(it: Itinerary) -> bool:
    return it.overall_status in (AvailabilityStatus.CONFIRMED.value, "UNRESERVED")


def _summary(
    ranked: list[Itinerary],
    valid: list[Itinerary],
    preferred: Itinerary | None,
    params: SearchParams,
    informative: bool = True,
    unserved: tuple[str, str] | None = None,
) -> dict[str, Any]:
    direct = [it for it in valid if it.primary_category == "direct"]
    if unserved and ranked:
        return {
            "headline": unserved[0],
            "subline": f"{unserved[1]} {len(ranked)} way{'s' if len(ranked) != 1 else ''} to go below.",
            "direct_count": len(direct),
            "direct_confirmed": 0,
            "alternatives_with_seats": 0,
            "best_bookable_id": None,
            "preferred_id": preferred.id if preferred else None,
        }
    if not informative:
        others = [it for it in ranked if it.primary_category != "direct"]
        day = format_day(params.travel_date)
        if direct:
            headline = f"{len(direct)} direct train{'s' if len(direct) != 1 else ''} on {day}"
            subline = (
                "Seat availability isn't live here — tap Check seats to see it on IRCTC. If your train is "
                f"full, each train lists backup tickets, and there are {len(others)} other ways to go."
            )
        elif ranked:
            headline = f"No direct train on {day}"
            subline = f"{len(ranked)} way{'s' if len(ranked) != 1 else ''} to get there with a change. Check seats on IRCTC."
        else:
            headline = "No journeys found"
            subline = "Try nearby stations, more changes or flexible dates."
        return {
            "headline": headline,
            "subline": subline,
            "direct_count": len(direct),
            "direct_confirmed": 0,
            "alternatives_with_seats": 0,
            "best_bookable_id": None,
            "preferred_id": preferred.id if preferred else None,
        }
    direct_ok = [it for it in direct if it.overall_status == AvailabilityStatus.CONFIRMED.value]
    alternatives_ok = [it for it in ranked if it.primary_category != "direct" and _is_bookable(it)]
    if direct_ok:
        headline = "Direct seats are showing"
        subline = (
            f"{len(direct_ok)} direct option{'s' if len(direct_ok) != 1 else ''} show seats. "
            f"{len(alternatives_ok)} more alternatives below."
        )
    elif direct:
        headline = "Your direct trains are full"
        if alternatives_ok:
            found = f"We found {len(alternatives_ok)} alternative{'s' if len(alternatives_ok) != 1 else ''} with seats."
        else:
            found = "No alternative shows confirmed seats either — the best RAC and waitlist options are below."
        if len(direct) == 1:
            subline = f"The only direct train has no confirmed seat. {found}"
        else:
            subline = f"None of the {len(direct)} direct trains has a confirmed seat. {found}"
    elif ranked:
        headline = "No direct train for this route"
        subline = f"We found {len(alternatives_ok)} alternative{'s' if len(alternatives_ok) != 1 else ''} with seats."
    else:
        headline = "No journeys found"
        subline = "Try nearby stations, more transfers or flexible dates."
    best_ok = next((it for it in ranked if _is_bookable(it)), None)
    return {
        "headline": headline,
        "subline": subline,
        "direct_count": len(direct),
        "direct_confirmed": len(direct_ok),
        "alternatives_with_seats": len(alternatives_ok),
        "best_bookable_id": best_ok.id if best_ok else None,
        "preferred_id": preferred.id if preferred else None,
    }


def _status_rank(status: str) -> float:
    if status == "UNRESERVED":
        return 3.5  # always purchasable, but no seat guarantee
    return STATUS_RANK[AvailabilityStatus(status)]


def _date_strip(items: list[Itinerary], days: list[date]) -> list[dict[str, Any]]:
    out = []
    for day in sorted(days):
        options = [it for it in items if it.travel_date == day]
        statuses = [it.overall_status for it in options]
        best_status = max(statuses, key=_status_rank) if statuses else None
        bookable = [it for it in options if _is_bookable(it)]
        out.append(
            {
                "date": day.isoformat(),
                "label": format_day(day),
                "best_status": best_status,
                "options": len(options),
                "bookable_options": len(bookable),
                "cheapest_bookable": min((it.cost_per_person for it in bookable), default=None),
            }
        )
    return out
