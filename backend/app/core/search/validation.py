"""Independent itinerary validation.

The explorer only builds feasible routes, but every itinerary is re-checked here before
it is shown, and so is any itinerary decoded from a saved or shared ID (untrusted input).
"""

from __future__ import annotations

from ..timetable import Timetable
from ..timeutil import minutes_between
from .explorer import Leg, RideLeg, RoadLeg
from .itinerary import Ticket
from .params import SearchOptions


class InvalidItinerary(ValueError):
    """The itinerary breaks a timetable or connection rule."""


def validate_ride(ride: RideLeg, timetable: Timetable) -> None:
    train = timetable.train(ride.train.number)
    if train is None:
        raise InvalidItinerary(f"Train {ride.train.number} is not in the current timetable")
    if not train.runs_on_date(ride.run.start_date):
        raise InvalidItinerary(
            f"{train.number} does not run on {ride.run.start_date:%a %d %b} ({train.runs_on_label()})"
        )
    if not 0 <= ride.board < ride.alight < len(train.stops):
        raise InvalidItinerary(f"{train.number}: boarding must come before alighting")
    board, alight = train.stops[ride.board], train.stops[ride.alight]
    if not board.boardable:
        raise InvalidItinerary(f"{train.number} does not let passengers board at {board.station}")
    if not alight.alightable:
        raise InvalidItinerary(f"{train.number} does not let passengers alight at {alight.station}")


def validate_tickets(ride: RideLeg, tickets: list[Ticket]) -> None:
    if not tickets:
        raise InvalidItinerary(f"{ride.train.number}: a train leg needs a ticket")
    for t in tickets:
        if t.run.key != ride.run.key:
            raise InvalidItinerary("A ticket belongs to a different train run than its leg")
    ordered = sorted(tickets, key=lambda t: t.from_idx)
    if ordered[0].from_idx > ride.board or ordered[-1].to_idx < ride.alight:
        raise InvalidItinerary(f"{ride.train.number}: tickets do not cover the whole ride")
    for a, b in zip(ordered, ordered[1:]):
        if a.to_idx != b.from_idx:
            raise InvalidItinerary(f"{ride.train.number}: split tickets must meet at the same station")
    for t in ordered:
        stops = ride.train.stops
        if t.from_idx < ride.board and not stops[t.from_idx].boardable:
            raise InvalidItinerary("A ticket starts where the train does not take passengers")
        if t.to_idx > ride.alight and not stops[t.to_idx].alightable:
            raise InvalidItinerary("A ticket ends where the train does not set down passengers")


def validate_route(legs: list[Leg], timetable: Timetable, options: SearchOptions) -> None:
    if not legs:
        raise InvalidItinerary("An itinerary needs at least one leg")
    if not any(isinstance(leg, RideLeg) for leg in legs):
        raise InvalidItinerary("An itinerary needs at least one train")
    touched: set[str] = set()
    for i, leg in enumerate(legs):
        if isinstance(leg, RideLeg):
            validate_ride(leg, timetable)
        stations = leg.stations()
        if i == 0:
            touched.add(stations[0])
        for code in stations[1:]:
            if code in touched:
                raise InvalidItinerary(f"The route passes {code} twice (circular route)")
            touched.add(code)
        if i == 0:
            continue
        prev = legs[i - 1]
        if prev.to_code != leg.from_code:
            raise InvalidItinerary(f"Leg {i + 1} starts at {leg.from_code}, not where leg {i} ended")
        gap = minutes_between(prev.arr, leg.dep)
        if gap < 0:
            raise InvalidItinerary(f"Leg {i + 1} departs before leg {i} arrives")
        if isinstance(prev, RideLeg) and isinstance(leg, RideLeg):
            if prev.run.key == leg.run.key:
                raise InvalidItinerary("Consecutive legs on the same train must be a split ticket")
            if gap < options.min_transfer_minutes:
                raise InvalidItinerary(
                    f"Only {gap} min to change trains at {leg.from_code}; "
                    f"at least {options.min_transfer_minutes} min is required"
                )
        if isinstance(prev, RoadLeg) and isinstance(leg, RoadLeg):
            raise InvalidItinerary("Two road legs in a row should be one road leg")
