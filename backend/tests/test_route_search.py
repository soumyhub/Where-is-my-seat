"""Route-search engine scenarios (the ten required cases plus edge cases)."""

from __future__ import annotations

import random
import time
from datetime import date, timedelta

import pytest

from app.core.models import TrainRun
from app.core.search import (
    InvalidItinerary,
    RideLeg,
    RoadLeg,
    SearchLimits,
    SearchRequestError,
    sort_itineraries,
    validate_route,
)
from app.core.search.validation import validate_ride
from app.core.stations import UnknownPlaceError

from .conftest import TRAVEL_DATE, build_engine, params, ride_numbers


def _stations_visited(it) -> list[str]:
    out = [it.legs[0].leg.from_code]
    for pl in it.legs:
        out.extend(pl.leg.stations()[1:])
    return out


# 1 ---------------------------------------------------------------------------
def test_direct_train_is_found_and_confirmed(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A"))
    direct = [it for it in result.itineraries if it.primary_category == "direct" and ride_numbers(it) == ["T100"]]
    assert direct, "the direct T100 must be offered"
    it = direct[0]
    assert it.overall_status == "CONFIRMED"
    assert it.transfers == 0 and it.train_changes == 0
    assert it.legs[0].leg.dep.strftime("%H:%M") == "08:00"
    assert it.arrive_at.strftime("%H:%M") == "11:00"
    assert result.summary["direct_confirmed"] >= 1


# 2 ---------------------------------------------------------------------------
def test_no_direct_route_but_alternative_boarding_station_works(engine):
    result = engine.search(params(engine, "LON", "DST", travel_class="3A"))
    assert result.itineraries, "an alternative must be found"
    assert all(it.primary_category != "direct" for it in result.itineraries)
    via_nbr = [it for it in result.itineraries if ride_numbers(it) == ["T500"]]
    assert via_nbr, "boarding T500 at the nearby station NBR should be suggested"
    it = via_nbr[0]
    feeder, ride = it.legs[0].leg, it.legs[1].leg
    assert isinstance(feeder, RoadLeg) and feeder.purpose == "feeder"
    assert (feeder.from_code, feeder.to_code) == ("LON", "NBR")
    assert isinstance(ride, RideLeg) and ride.from_code == "NBR"
    assert feeder.arr <= ride.dep - timedelta(minutes=engine.options.feeder_buffer_minutes)
    assert "alternative_boarding" in it.categories
    assert any("NBR" in line or "Nbr" in line for line in it.fits)


# 3 ---------------------------------------------------------------------------
def test_connecting_journey_through_junction(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A"))
    conn = [it for it in result.itineraries if ride_numbers(it) == ["T200", "T300"]]
    assert conn, "T200 -> T300 via JNC must be offered"
    it = conn[0]
    first, second = it.rides
    assert first.to_code == second.from_code == "JNC"
    gap = (second.dep - first.arr).total_seconds() / 60
    assert gap == 45 >= engine.options.min_transfer_minutes
    assert "connecting" in it.categories
    assert it.overall_status == "CONFIRMED"
    assert any("separate tickets" in w.lower() for w in it.warnings)


# 4 ---------------------------------------------------------------------------
def test_too_short_transfer_is_rejected(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A"))
    for it in result.itineraries:
        numbers = ride_numbers(it)
        assert not ("T201" in numbers and "T301" in numbers), "10 min change must never be offered"
    assert result.stats["rejected_short_connections"] >= 1
    example = next(e for e in result.stats["rejected_examples"] if e["departing_train"] == "T301")
    assert example["gap_minutes"] == 10 and example["required_minutes"] == 30

    timetable = engine.timetable
    run_a = TrainRun(timetable.train("T201"), TRAVEL_DATE)
    run_b = TrainRun(timetable.train("T301"), TRAVEL_DATE)
    with pytest.raises(InvalidItinerary, match="change trains"):
        validate_route([RideLeg(run_a, 0, 1), RideLeg(run_b, 0, 1)], timetable, engine.options)


# 5 ---------------------------------------------------------------------------
def test_overnight_journey_arrives_next_day(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A"))
    night = [it for it in result.itineraries if ride_numbers(it) == ["T400"]]
    assert night
    it = night[0]
    ride = it.rides[0]
    assert ride.dep.date() == TRAVEL_DATE and ride.dep.strftime("%H:%M") == "22:00"
    assert it.arrive_at.date() == TRAVEL_DATE + timedelta(days=1)
    assert it.arrive_at.strftime("%H:%M") == "05:00"
    assert it.total_minutes == 7 * 60
    assert any("overnight" in line for line in it.fits)


# 6 ---------------------------------------------------------------------------
def test_circular_route_is_never_returned(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A", max_transfers=3))
    for it in result.itineraries:
        visited = _stations_visited(it)
        assert len(visited) == len(set(visited)), f"loop in {ride_numbers(it)}: {visited}"
        assert ride_numbers(it) != ["T700", "T701"]
    assert result.stats["loops_prevented"] >= 1

    timetable = engine.timetable
    away = RideLeg(TrainRun(timetable.train("T700"), TRAVEL_DATE), 0, 2)  # ORG -> LPB
    back = RideLeg(TrainRun(timetable.train("T701"), TRAVEL_DATE), 0, 2)  # LPB -> ORG -> DST
    with pytest.raises(InvalidItinerary, match="circular"):
        validate_route([away, back], timetable, engine.options)


# 7 ---------------------------------------------------------------------------
def test_train_that_does_not_stop_is_never_used(engine):
    # T600 passes PAS without halting; only the T601 local serves PAS.
    result = engine.search(params(engine, "PAS", "DST", travel_class="SL", include_nearby=False))
    assert result.itineraries
    assert all("T600" not in ride_numbers(it) for it in result.itineraries)
    assert {n for it in result.itineraries for n in ride_numbers(it)} == {"T601"}

    # T600 also has a technical halt at TEC: no boarding, no alighting there.
    for it in engine.search(params(engine, "ORG", "DST", travel_class="3A")).itineraries:
        for ride in it.rides:
            assert "TEC" not in (ride.from_code, ride.to_code)

    t600 = engine.timetable.train("T600")
    assert t600.index_of("PAS") is None
    with pytest.raises(InvalidItinerary, match="does not let passengers"):
        validate_ride(RideLeg(TrainRun(t600, TRAVEL_DATE), 1, 2), engine.timetable)  # board at TEC
    with pytest.raises(InvalidItinerary, match="does not run"):
        t900 = engine.timetable.train("T900")
        validate_ride(RideLeg(TrainRun(t900, TRAVEL_DATE), 0, 1), engine.timetable)  # Sunday-only train


def test_non_running_day_is_not_offered(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A"))
    assert all("T900" not in ride_numbers(it) for it in result.itineraries)
    sunday = TRAVEL_DATE + timedelta(days=(6 - TRAVEL_DATE.weekday()))
    on_sunday = engine.search(params(engine, "ORG", "DST", travel_class="3A", travel_date=sunday))
    assert any(ride_numbers(it) == ["T900"] for it in on_sunday.itineraries)


# 9 ---------------------------------------------------------------------------
def _dense_network(n_stations: int = 30, n_trains: int = 400, seed: int = 7):
    rng = random.Random(seed)
    codes = [f"S{i:02d}" for i in range(n_stations)]
    stations_doc = {
        "cities": {c.lower(): {"name": c, "anchor": c} for c in codes},
        "stations": [
            {"code": c, "name": c, "city": c.lower(), "state": "T", "lat": 27 + rng.random(), "lon": 76 + rng.random()}
            for c in codes
        ],
    }
    trains = []
    for t in range(n_trains):
        path = rng.sample(codes, rng.randint(3, 8))
        minute = rng.randint(0, 23 * 60)
        stops = []
        for k, code in enumerate(path):
            day = minute // 1440 + 1
            hhmm = f"{(minute % 1440) // 60:02d}:{minute % 60:02d}"
            row = {"code": code, "km": k * 40, "day": day}
            if k > 0:
                row["arr"] = hhmm
            if k < len(path) - 1:
                row["dep"] = hhmm
            stops.append(row)
            minute += rng.randint(20, 90)
        trains.append({"number": f"D{t}", "name": f"Dense {t}", "simulated": True, "classes": ["SL"], "stops": stops})
    return stations_doc, {"meta": {"simulated": True}, "trains": trains}


def test_search_limits_bound_the_exploration():
    stations_doc, trains_doc = _dense_network()
    tight = SearchLimits(max_expansions=300, max_candidates=40, max_frontier=50, time_budget_seconds=2.0)
    engine = build_engine(stations_doc=stations_doc, trains_doc=trains_doc, rules_doc={"rules": []}, limits=tight)
    started = time.monotonic()
    result = engine.search(params(engine, "S00", "S01", travel_class="SL", max_transfers=3))
    elapsed = time.monotonic() - started
    stats = result.stats
    assert stats["truncated"] is True
    assert stats["expansions"] <= tight.max_expansions + 1
    assert stats["routes_found"] <= tight.max_candidates
    assert elapsed < 3.0
    assert all(it.transfers <= 3 for it in result.itineraries)

    # The same network with generous limits explores more, but still terminates quickly.
    loose = build_engine(stations_doc=stations_doc, trains_doc=trains_doc, rules_doc={"rules": []})
    started = time.monotonic()
    full = loose.search(params(loose, "S00", "S01", travel_class="SL", max_transfers=2))
    assert time.monotonic() - started < loose.limits.time_budget_seconds + 2
    assert full.stats["expansions"] >= stats["expansions"]


def test_max_transfers_is_respected(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A", max_transfers=0))
    assert result.itineraries
    assert all(it.transfers == 0 for it in result.itineraries)


# 10 --------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["best", "cheapest", "fastest", "fewest_transfers"])
def test_results_are_sorted_by_selected_criterion(engine, mode):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A", sort=mode, max_transfers=3))
    items = result.itineraries
    assert len(items) >= 3
    keys = {
        "best": lambda it: -it.score,
        "cheapest": lambda it: it.cost_per_person,
        "fastest": lambda it: it.total_minutes,
        "fewest_transfers": lambda it: it.transfers,
    }[mode]
    values = [keys(it) for it in items]
    assert values == sorted(values)
    resorted = sort_itineraries(list(reversed(items)), mode)
    assert [keys(it) for it in resorted] == values


def test_best_ranking_prefers_confirmed_seats(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A"))
    top = result.itineraries[0]
    assert top.overall_status == "CONFIRMED"
    waitlisted = [it for it in result.itineraries if it.overall_status == "WAITLISTED"]
    assert waitlisted and all(top.score > it.score for it in waitlisted)


# smart tickets -----------------------------------------------------------------
def test_smart_ticket_strategies_are_found_when_direct_is_waitlisted(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A"))
    t800 = [it for it in result.itineraries if ride_numbers(it) == ["T800"] and not it.has_road]
    strategies = {t.strategy for it in t800 for t in it.tickets}
    assert {"standard", "book_beyond", "upstream_boarding", "split"} <= strategies
    beyond = next(it for it in t800 if it.tickets[0].strategy == "book_beyond")
    assert beyond.tickets[0].to_code == "BEY" and beyond.rides[0].to_code == "DST"
    assert beyond.overall_status == "CONFIRMED"
    assert any("not refunded" in w for w in beyond.warnings)
    split = next(it for it in t800 if len(it.tickets) == 2)
    assert [t.to_code for t in split.tickets] == ["MID", "DST"]
    upstream = next(it for it in t800 if it.tickets[0].strategy == "upstream_boarding")
    assert upstream.tickets[0].from_code == "UPS" and upstream.rides[0].from_code == "ORG"
    assert any("boarding point" in w for w in upstream.warnings)


def test_smart_tickets_can_be_switched_off(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A", smart_tickets=False))
    assert all(t.strategy == "standard" for it in result.itineraries for t in it.tickets)


# request validation & no-result reasons ---------------------------------------
def test_same_origin_and_destination_is_rejected(engine):
    with pytest.raises(SearchRequestError) as exc:
        engine.search(params(engine, "DST", "city:dest"))
    assert exc.value.code == "SAME_ORIGIN_DESTINATION"


def test_invalid_dates_are_rejected(engine):
    with pytest.raises(SearchRequestError) as past:
        engine.search(params(engine, "ORG", "DST", travel_date=date(2026, 10, 1)))
    assert past.value.code == "INVALID_DATE"
    with pytest.raises(SearchRequestError) as far:
        engine.search(params(engine, "ORG", "DST", travel_date=date(2027, 6, 1)))
    assert far.value.code == "INVALID_DATE" and "60 days" in far.value.message


def test_unknown_station_suggests_alternatives(engine):
    with pytest.raises(UnknownPlaceError) as exc:
        engine.resolve_place("ORX")
    assert exc.value.suggestions


def test_no_timetable_at_origin(engine):
    result = engine.search(params(engine, "FAR", "DST"))
    assert result.itineraries == []
    assert result.no_results_reason == "NO_TIMETABLE_AT_ORIGIN"


def test_no_route_within_limits(engine):
    result = engine.search(params(engine, "LON", "DST", max_transfers=0))
    assert result.itineraries == []
    assert result.no_results_reason == "NO_ROUTE_WITHIN_LIMITS"
    assert "transfers" in (result.no_results_message or "")


def test_budget_filter_hides_expensive_options(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A", max_budget=50))
    assert result.itineraries == []
    assert result.no_results_reason == "ALL_FILTERED"
    assert result.hidden["over_budget"] > 0


def test_results_have_no_duplicate_routes(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A", max_transfers=3))
    signatures = [it.route_signature() for it in result.itineraries]
    assert len(signatures) == len(set(signatures))


def test_every_returned_itinerary_revalidates(engine):
    result = engine.search(params(engine, "LON", "DST", travel_class="3A", max_transfers=3))
    for it in result.itineraries:
        validate_route([pl.leg for pl in it.legs], engine.timetable, engine.options)


def test_itinerary_id_round_trip_and_tampering(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A"))
    original = next(it for it in result.itineraries if len(it.tickets) == 2 and len(it.rides) == 1)
    rebuilt, _ = engine.resolve_itinerary(original.id)
    assert rebuilt.route_signature() == original.route_signature()
    assert rebuilt.overall_status == original.overall_status
    with pytest.raises(InvalidItinerary):
        engine.resolve_itinerary(original.id[:-6] + "AAAAAA")
    with pytest.raises(InvalidItinerary):
        engine.resolve_itinerary("not-a-journey")


def test_flexible_dates_add_other_days(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A", flexible_days=1))
    offsets = {it.date_offset for it in result.itineraries}
    assert {-1, 0, 1} <= offsets
    assert [d["date"] for d in result.date_strip] == [
        (TRAVEL_DATE + timedelta(days=k)).isoformat() for k in (-1, 0, 1)
    ]
    flex = next(it for it in result.itineraries if it.date_offset != 0)
    assert "flexible_date" in flex.categories
