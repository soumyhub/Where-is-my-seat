"""Bounded, round-based breadth-first exploration of the time-dependent railway graph.

Round k extends every partial journey ("label") by exactly one more train ride, so the
number of rounds is bounded by the transfer limit. A ride is only followed when:

* the train actually halts at the boarding and alighting stations (passing through, or
  a technical halt, is never enough),
* it leaves inside a feasible time window (minimum transfer time after the previous
  arrival, at most ``max_wait_minutes`` later, overnight and multi-day runs included),
* it never revisits a station already on the journey (no circular routes), and
* the transfer point stays inside a detour ellipse around origin and destination.

Per-station label caps, a frontier cap, an expansion budget, a candidate cap and a
wall-clock deadline keep the search bounded on any network.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ..graph import TimeDependentGraph
from ..models import Train, TrainRun
from ..road import RoadEstimate
from ..timetable import Departure
from ..timeutil import minutes_between, to_iso
from .params import SearchLimits, SearchOptions


@dataclass(frozen=True, slots=True)
class RideLeg:
    """Riding one train run from stop ``board`` to stop ``alight``."""

    run: TrainRun
    board: int
    alight: int

    @property
    def kind(self) -> str:
        return "train"

    @property
    def train(self) -> Train:
        return self.run.train

    @property
    def from_code(self) -> str:
        return self.run.train.stops[self.board].station

    @property
    def to_code(self) -> str:
        return self.run.train.stops[self.alight].station

    @property
    def dep(self) -> datetime:
        return self.run.dep_at(self.board)

    @property
    def arr(self) -> datetime:
        return self.run.arr_at(self.alight)

    @property
    def km(self) -> int:
        stops = self.run.train.stops
        return stops[self.alight].km - stops[self.board].km

    @property
    def minutes(self) -> int:
        return minutes_between(self.dep, self.arr)

    def stations(self) -> list[str]:
        return [s.station for s in self.run.train.stops[self.board : self.alight + 1]]

    def signature(self) -> tuple[str, ...]:
        return ("T", self.run.key, self.from_code, self.to_code)


@dataclass(frozen=True, slots=True)
class RoadLeg:
    """A road / metro leg the traveller arranges separately (never booked here)."""

    estimate: RoadEstimate
    dep: datetime
    purpose: str  # "feeder" | "transfer" | "onward"

    @property
    def kind(self) -> str:
        return "road"

    @property
    def from_code(self) -> str:
        return self.estimate.from_code

    @property
    def to_code(self) -> str:
        return self.estimate.to_code

    @property
    def arr(self) -> datetime:
        return self.dep + timedelta(minutes=self.estimate.minutes)

    @property
    def km(self) -> int:
        return self.estimate.km

    @property
    def minutes(self) -> int:
        return self.estimate.minutes

    def stations(self) -> list[str]:
        return [self.from_code, self.to_code]

    def signature(self) -> tuple[str, ...]:
        return ("R", self.from_code, self.to_code, self.purpose)


Leg = RideLeg | RoadLeg


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    legs: tuple[Leg, ...]
    travel_date: date

    @property
    def rides(self) -> list[RideLeg]:
        return [leg for leg in self.legs if isinstance(leg, RideLeg)]

    def signature(self) -> tuple[tuple[str, ...], ...]:
        return tuple(leg.signature() for leg in self.legs)


@dataclass(frozen=True)
class Endpoints:
    """Resolved search ends: which stations count as 'here' and 'there'."""

    origin_label: str
    destination_label: str
    origin_anchor: str
    dest_anchor: str
    origin_zero: frozenset[str]  # board here with no feeder
    origin_feeders: dict[str, RoadEstimate]  # board here after a road feeder
    dest_zero: frozenset[str]  # arriving here completes the trip
    dest_onward: dict[str, RoadEstimate]  # arriving here needs a road leg onward


@dataclass
class ExploreStats:
    departures_scanned: int = 0
    expansions: int = 0
    labels_created: int = 0
    labels_pruned: int = 0
    rejected_short_connections: int = 0
    loops_prevented: int = 0
    detour_pruned: int = 0
    duration_pruned: int = 0
    duplicates_removed: int = 0
    truncated: bool = False
    truncated_reason: str | None = None
    rejected_examples: list[dict[str, object]] = field(default_factory=list)

    def truncate(self, reason: str) -> None:
        if not self.truncated:
            self.truncated = True
            self.truncated_reason = reason


@dataclass(slots=True)
class _Label:
    station: str
    earliest: datetime  # earliest feasible departure from ``station``
    latest: datetime  # latest departure worth considering
    legs: tuple[Leg, ...]
    touched: frozenset[str]  # every station the journey has passed
    last_run: str | None
    journey_start: datetime | None
    pending_feeder: RoadEstimate | None = None
    arrived_at: datetime | None = None  # set when the label ends a train ride here
    arrived_by: str | None = None


class RouteExplorer:
    def __init__(self, graph: TimeDependentGraph, options: SearchOptions, limits: SearchLimits):
        self.graph = graph
        self.options = options
        self.limits = limits

    def explore(
        self,
        ends: Endpoints,
        travel_date: date,
        window_start: datetime,
        window_end: datetime,
        *,
        max_transfers: int,
        max_duration_minutes: int,
        allow_unreserved: bool,
        deadline: float,
        stats: ExploreStats,
    ) -> list[RouteCandidate]:
        return _Exploration(
            self,
            ends,
            travel_date,
            window_start,
            window_end,
            max_transfers,
            max_duration_minutes,
            allow_unreserved,
            deadline,
            stats,
        ).run()


class _Exploration:
    def __init__(
        self,
        explorer: RouteExplorer,
        ends: Endpoints,
        travel_date: date,
        window_start: datetime,
        window_end: datetime,
        max_transfers: int,
        max_duration: int,
        allow_unreserved: bool,
        deadline: float,
        stats: ExploreStats,
    ) -> None:
        self.graph = explorer.graph
        self.options = explorer.options
        self.limits = explorer.limits
        self.ends = ends
        self.travel_date = travel_date
        self.window_start = window_start
        self.window_end = window_end
        self.max_legs = max_transfers + 1
        self.max_rides = min(self.limits.max_rides, self.max_legs)
        self.max_duration = max_duration
        self.allow_unreserved = allow_unreserved
        self.deadline = deadline
        self.stats = stats
        self.found: list[RouteCandidate] = []
        self.seen: set[tuple[tuple[str, ...], ...]] = set()
        self.round_no = 0
        self.next_labels: list[_Label] = []

    # ----- driver -------------------------------------------------------
    def run(self) -> list[RouteCandidate]:
        frontier = self._seeds()
        for round_no in range(self.max_rides):
            self.round_no = round_no
            self.next_labels = []
            for label in frontier:
                if self._should_stop():
                    break
                self._expand(label)
            if self._should_stop():
                break
            frontier = self._prune(self.next_labels)
            if not frontier:
                break
        return self.found

    def _should_stop(self) -> bool:
        if self.stats.truncated:
            return True
        if _time.monotonic() > self.deadline:
            self.stats.truncate("time budget reached")
            return True
        return False

    # ----- seeds --------------------------------------------------------
    def _seeds(self) -> list[_Label]:
        ends, opts = self.ends, self.options
        labels: list[_Label] = []
        for code in sorted(ends.origin_zero):
            if self.graph.serves(code):
                labels.append(
                    _Label(
                        station=code,
                        earliest=self.window_start,
                        latest=self.window_end,
                        legs=(),
                        touched=frozenset({code}),
                        last_run=None,
                        journey_start=None,
                    )
                )
        if self.max_legs < 2:
            return labels  # a feeder plus a train already needs one transfer
        for code, estimate in sorted(ends.origin_feeders.items()):
            if not self.graph.serves(code):
                continue
            lead = timedelta(minutes=estimate.minutes + opts.feeder_buffer_minutes)
            labels.append(
                _Label(
                    station=code,
                    earliest=self.window_start + lead,
                    latest=self.window_end + lead,
                    legs=(),
                    # A train from a feeder station must not pass back through the origin.
                    touched=frozenset(ends.origin_zero | {ends.origin_anchor, code}),
                    last_run=None,
                    journey_start=None,
                    pending_feeder=estimate,
                )
            )
        return labels

    # ----- expansion ----------------------------------------------------
    def _expand(self, label: _Label) -> None:
        legs_now = len(label.legs) + (1 if label.pending_feeder else 0)
        if legs_now + 1 > self.max_legs:
            return
        scan_from = label.arrived_at if label.arrived_at is not None else label.earliest
        for dep in self.graph.departures(label.station, scan_from, label.latest):
            if self._should_stop():
                return
            self.stats.departures_scanned += 1
            if dep.run.key == label.last_run:
                continue  # staying on the same train is handled by split tickets
            if dep.time < label.earliest:
                self._reject_connection(label, dep)
                continue
            unreserved_only = not dep.run.train.classes
            if unreserved_only and not self.allow_unreserved:
                continue
            prefix = label.legs
            start = label.journey_start
            if label.pending_feeder is not None:
                feeder = label.pending_feeder
                feeder_dep = dep.time - timedelta(
                    minutes=feeder.minutes + self.options.feeder_buffer_minutes
                )
                if not (self.window_start <= feeder_dep <= self.window_end):
                    continue
                prefix = prefix + (RoadLeg(feeder, feeder_dep, "feeder"),)
                start = feeder_dep
            elif start is None:
                start = dep.time
            self._ride(label, dep, prefix, start, unreserved_only)

    def _ride(
        self,
        label: _Label,
        dep: Departure,
        prefix: tuple[Leg, ...],
        start: datetime,
        unreserved_only: bool,
    ) -> None:
        opts, ends, stats = self.options, self.ends, self.stats
        stops = dep.run.train.stops
        board = dep.index
        board_km = stops[board].km
        passed: list[str] = [stops[board].station]
        in_destination: list[int] = []
        for j in range(board + 1, len(stops)):
            stop = stops[j]
            if stop.station in label.touched or stop.station in passed:
                stats.loops_prevented += 1
                break
            passed.append(stop.station)
            arr = dep.run.arr_at(j)
            if minutes_between(start, arr) > self.max_duration:
                stats.duration_pruned += 1
                break
            if unreserved_only and stop.km - board_km > opts.max_unreserved_km:
                break  # long unreserved rides are not suggested
            if stop.technical:
                continue  # the train halts but passengers may not alight
            if stop.station in ends.dest_zero:
                in_destination.append(j)
                continue
            if in_destination:
                break  # the train has left the destination area
            if stop.station in ends.origin_zero:
                continue  # never change trains inside the origin itself: start there instead
            if not self.graph.detour_ok(
                ends.origin_anchor, ends.dest_anchor, stop.station, opts.detour_factor, opts.detour_slack_km
            ):
                stats.detour_pruned += 1
                continue
            stats.expansions += 1
            if stats.expansions > self.limits.max_expansions:
                stats.truncate("expansion limit reached")
                break
            legs = prefix + (RideLeg(dep.run, board, j),)
            touched = label.touched.union(passed)
            onward = ends.dest_onward.get(stop.station)
            if onward is not None and len(legs) + 1 <= self.max_legs:
                road = RoadLeg(onward, arr + timedelta(minutes=opts.exit_buffer_minutes), "onward")
                if minutes_between(start, road.arr) <= self.max_duration:
                    self._record(legs + (road,))
            if self.round_no + 1 >= self.max_rides or len(legs) + 1 > self.max_legs:
                continue
            if not self.graph.is_transfer_point(stop.station) or not self.graph.progress_ok(
                ends.origin_anchor, ends.dest_anchor, stop.station, opts.progress_slack_km
            ):
                continue  # not a sensible place to change trains on the way there
            self._push(
                _Label(
                    station=stop.station,
                    earliest=arr + timedelta(minutes=opts.min_transfer_minutes),
                    latest=arr + timedelta(minutes=opts.max_wait_minutes),
                    legs=legs,
                    touched=touched,
                    last_run=dep.run.key,
                    journey_start=start,
                    arrived_at=arr,
                    arrived_by=dep.run.train.number,
                )
            )
            if len(legs) + 2 > self.max_legs:
                continue
            for estimate in self.graph.city_transfers(stop.station):
                target = estimate.to_code
                if target in touched or target in ends.dest_zero or target in ends.dest_onward:
                    continue
                road = RoadLeg(estimate, arr + timedelta(minutes=opts.exit_buffer_minutes), "transfer")
                self._push(
                    _Label(
                        station=target,
                        earliest=road.arr + timedelta(minutes=opts.min_transfer_minutes),
                        latest=road.arr + timedelta(minutes=opts.max_wait_minutes),
                        legs=legs + (road,),
                        touched=touched | {target},
                        last_run=dep.run.key,
                        journey_start=start,
                    )
                )
        if in_destination:
            j = self._preferred_alight(dep.run.train, in_destination)
            self._record(prefix + (RideLeg(dep.run, board, j),))

    def _preferred_alight(self, train: Train, indices: list[int]) -> int:
        for j in indices:
            if train.stops[j].station == self.ends.dest_anchor:
                return j
        return indices[0]

    # ----- bookkeeping --------------------------------------------------
    def _record(self, legs: tuple[Leg, ...]) -> None:
        candidate = RouteCandidate(legs=legs, travel_date=self.travel_date)
        signature = candidate.signature()
        if signature in self.seen:
            self.stats.duplicates_removed += 1
            return
        self.seen.add(signature)
        self.found.append(candidate)
        if len(self.found) >= self.limits.max_candidates:
            self.stats.truncate("candidate limit reached")

    def _push(self, label: _Label) -> None:
        self.next_labels.append(label)
        self.stats.labels_created += 1

    def _prune(self, labels: list[_Label]) -> list[_Label]:
        """Bound the frontier while keeping it diverse in time.

        Per station, at most ``max_labels_per_run`` labels per arriving train run are
        kept (fewest legs first, then the earliest boarding), and runs are then sampled
        round-robin in arrival order so an evening connection is not crowded out by
        many morning ones.
        """
        by_station: dict[str, dict[str | None, list[_Label]]] = {}
        for label in labels:
            by_station.setdefault(label.station, {}).setdefault(label.last_run, []).append(label)
        kept: list[_Label] = []
        for runs in by_station.values():
            lanes: list[list[_Label]] = []
            for group in runs.values():
                group.sort(key=lambda lab: (len(lab.legs), lab.journey_start or lab.earliest))
                unique: list[_Label] = []
                seen: set[tuple[tuple[str, ...], ...]] = set()
                for lab in group:
                    key = tuple(leg.signature() for leg in lab.legs)
                    if key not in seen:
                        seen.add(key)
                        unique.append(lab)
                lanes.append(unique[: self.limits.max_labels_per_run])
            lanes.sort(key=lambda lane: lane[0].earliest)
            chosen: list[_Label] = []
            depth = 0
            while len(chosen) < self.limits.max_labels_per_station and any(depth < len(l) for l in lanes):
                for lane in lanes:
                    if depth < len(lane) and len(chosen) < self.limits.max_labels_per_station:
                        chosen.append(lane[depth])
                depth += 1
            total = sum(len(group) for group in runs.values())
            self.stats.labels_pruned += total - len(chosen)
            kept.extend(chosen)
        kept.sort(key=lambda lab: lab.earliest)
        if len(kept) > self.limits.max_frontier:
            self.stats.labels_pruned += len(kept) - self.limits.max_frontier
            kept = kept[: self.limits.max_frontier]
        return kept

    def _reject_connection(self, label: _Label, dep: Departure) -> None:
        self.stats.rejected_short_connections += 1
        if label.arrived_at is None or len(self.stats.rejected_examples) >= 5:
            return
        ends = self.ends
        later = dep.run.train.stops[dep.index + 1 :]
        if not any(s.station in ends.dest_zero or s.station in ends.dest_onward for s in later):
            return  # only report connections that could actually have finished the trip
        example = {
            "station": label.station,
            "arriving_train": label.arrived_by,
            "arrives": to_iso(label.arrived_at),
            "departing_train": dep.run.train.number,
            "departs": to_iso(dep.time),
            "gap_minutes": minutes_between(label.arrived_at, dep.time),
            "required_minutes": self.options.min_transfer_minutes,
        }
        if example not in self.stats.rejected_examples:
            self.stats.rejected_examples.append(example)
