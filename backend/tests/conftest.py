"""Deterministic fixture network for route-search tests (no files, no network).

Station codes here are fake on purpose; the real demo network is tested in test_api.py.

    UPS ── ORG ──────── MID ──────── DST ── BEY        (T800 runs UPS→ORG→MID→DST→BEY)
            │ \\                    / │
            │  └── JNC ───────────┘  └ DS2 (same city as DST), NDS (nearby)
           NBR (nearby origin), LON (no trains), PAS / TEC (express passes / technical halt)
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

import pytest

# Tests never use a real live-availability key, even when backend/.env has one.
os.environ["WIMS_RAILRADAR_KEY"] = ""
os.environ["WIMS_AVAILABILITY_PROVIDER"] = "auto"

from app.core.availability import AvailabilityService, SimulatedAvailabilityProvider
from app.core.availability.base import AvailabilityProvider
from app.core.data_loader import parse_stations, parse_trains
from app.core.fares import FareEstimator
from app.core.festivals import RushCalendar
from app.core.road import RoadEstimator
from app.core.search import JourneySearchEngine, SearchLimits, SearchOptions, SearchParams
from app.core.stations import StationDirectory
from app.core.timetable import Timetable
from app.core.timeutil import FixedClock

TRAVEL_DATE = date(2026, 11, 10)  # a Tuesday
NOW = datetime(2026, 11, 1, 9, 0)


def _st(code, lat, lon, city=None, junction=False):
    return {"code": code, "name": f"{code} Station", "city": city or code.lower(), "state": "Test", "lat": lat, "lon": lon, "junction": junction}


STATIONS_DOC: dict[str, Any] = {
    "cities": {
        **{c: {"name": c.title(), "anchor": c.upper()} for c in ["org", "nbr", "lon", "mid", "jnc", "nds", "pas", "tec", "lpa", "lpb", "ups", "bey", "far"]},
        "dest": {"name": "Dest City", "anchor": "DST"},
    },
    "stations": [
        _st("UPS", 28.30, 77.30),
        _st("ORG", 28.00, 77.00),
        _st("NBR", 28.00, 76.70),
        _st("LON", 28.10, 76.55),
        _st("MID", 27.50, 76.50, junction=True),
        _st("JNC", 27.30, 76.40, junction=True),
        _st("PAS", 27.40, 76.10),
        _st("TEC", 27.20, 76.00),
        _st("DST", 27.00, 75.80, city="dest", junction=True),
        _st("DS2", 27.02, 75.83, city="dest"),
        _st("NDS", 27.00, 75.55),
        _st("BEY", 26.80, 75.30),
        _st("LPA", 28.10, 77.10),
        _st("LPB", 28.15, 77.00),
        _st("FAR", 31.00, 80.00),
    ],
}


def _stops(*rows):
    out = []
    for code, arr, dep, km, *extra in rows:
        row = {"code": code, "km": km, "day": extra[0] if extra else 1}
        if arr:
            row["arr"] = arr
        if dep:
            row["dep"] = dep
        if len(extra) > 1:
            row["technical"] = extra[1]
        out.append(row)
    return out


def _train(number, classes, stops, runs="daily", **kw):
    return {"number": number, "name": f"Test {number}", "simulated": True, "classes": classes, "runs_on": runs, "stops": stops, **kw}


TRAINS_DOC: dict[str, Any] = {
    "meta": {"simulated": True, "version": "test", "source": "fixture"},
    "trains": [
        # 1. plain direct
        _train("T100", ["3A", "SL"], _stops(("ORG", None, "08:00", 0), ("MID", "09:30", "09:32", 90), ("DST", "11:00", None, 180))),
        # 3. connecting via JNC with a comfortable 45 min change
        _train("T200", ["3A"], _stops(("ORG", None, "07:00", 0), ("JNC", "09:00", None, 110))),
        _train("T300", ["3A"], _stops(("JNC", None, "09:45", 0), ("DST", "11:15", None, 80))),
        # 4. a 10 min change at JNC that must be rejected
        _train("T201", ["3A"], _stops(("ORG", None, "06:00", 0), ("JNC", "08:30", None, 110))),
        _train("T301", ["3A"], _stops(("JNC", None, "08:40", 0), ("DST", "10:00", None, 80))),
        # 5. overnight: leaves 22:00, arrives 05:00 next day
        _train("T400", ["3A", "SL"], _stops(("ORG", None, "22:00", 0), ("MID", "01:30", "01:35", 90, 2), ("DST", "05:00", None, 180, 2))),
        # 2. only reachable from a nearby station
        _train("T500", ["3A"], _stops(("NBR", None, "10:00", 0), ("DST", "12:30", None, 150))),
        # 7. express that passes PAS without halting and has a technical halt at TEC
        _train("T600", ["3A"], _stops(("ORG", None, "09:00", 0), ("TEC", "10:00", "10:05", 120, 1, True), ("DST", "10:40", None, 170))),
        _train("T601", ["SL"], _stops(("PAS", None, "11:00", 0), ("DST", "12:00", None, 50))),
        # 6. a loop: T700 heads away, T701 comes back through ORG
        _train("T700", ["3A"], _stops(("ORG", None, "12:00", 0), ("LPA", "12:30", "12:32", 15), ("LPB", "13:00", None, 25))),
        _train("T701", ["3A"], _stops(("LPB", None, "13:40", 0), ("ORG", "14:10", "14:15", 20), ("DST", "16:00", None, 200))),
        # smart tickets: starts upstream at UPS and continues beyond DST to BEY
        _train("T800", ["3A"], _stops(("UPS", None, "06:00", 0), ("ORG", "06:40", "06:45", 40), ("MID", "08:15", "08:20", 130), ("DST", "09:40", "09:50", 220), ("BEY", "10:40", None, 270))),
        # runs only on Sundays (not on the Tuesday travel date)
        _train("T900", ["3A"], _stops(("ORG", None, "15:00", 0), ("DST", "17:00", None, 180)), runs=["Sun"]),
    ],
}

RULES_DOC: dict[str, Any] = {
    "rules": [
        {"train": "T100", "status": "CONFIRMED", "count": 20},
        {"train": "T200", "status": "CONFIRMED", "count": 10},
        {"train": "T300", "status": "CONFIRMED", "count": 12},
        {"train": "T201", "status": "CONFIRMED", "count": 9},
        {"train": "T301", "status": "CONFIRMED", "count": 9},
        {"train": "T400", "status": "WAITLISTED", "count": 7},
        {"train": "T500", "status": "CONFIRMED", "count": 5},
        {"train": "T600", "status": "RAC", "count": 3},
        {"train": "T601", "status": "CONFIRMED", "count": 30},
        {"train": "T700", "status": "CONFIRMED", "count": 8},
        {"train": "T701", "status": "WAITLISTED", "count": 50},
        {"train": "T800", "status": "WAITLISTED", "count": 30},
        {"train": "T800", "from": "ORG", "to": "BEY", "status": "CONFIRMED", "count": 3},
        {"train": "T800", "from": "UPS", "to": "DST", "status": "CONFIRMED", "count": 2},
        {"train": "T800", "from": "ORG", "to": "MID", "status": "CONFIRMED", "count": 6},
        {"train": "T800", "from": "MID", "to": "DST", "status": "CONFIRMED", "count": 6},
        {"train": "T900", "status": "CONFIRMED", "count": 40},
    ]
}


def build_engine(
    *,
    trains_doc: dict[str, Any] | None = None,
    stations_doc: dict[str, Any] | None = None,
    rules_doc: dict[str, Any] | None = None,
    provider: AvailabilityProvider | None = None,
    options: SearchOptions | None = None,
    limits: SearchLimits | None = None,
    now: datetime = NOW,
) -> JourneySearchEngine:
    stations, cities, _ = parse_stations(stations_doc or STATIONS_DOC)
    trains, meta = parse_trains(trains_doc or TRAINS_DOC, {s.code for s in stations}, require_simulated=True)
    directory = StationDirectory(stations, cities)
    clock = FixedClock(now)
    rush = RushCalendar([])
    provider = provider or SimulatedAvailabilityProvider(rules_doc or RULES_DOC, TRAVEL_DATE, rush, clock)
    return JourneySearchEngine(
        directory=directory,
        timetable=Timetable(trains, meta),
        road=RoadEstimator(directory, []),
        fares=FareEstimator(),
        availability=AvailabilityService(provider, clock),
        rush=rush,
        clock=clock,
        options=options,
        limits=limits,
    )


def params(engine: JourneySearchEngine, origin: str, destination: str, **kw) -> SearchParams:
    return SearchParams(
        origin=engine.resolve_place(origin),
        destination=engine.resolve_place(destination),
        travel_date=kw.pop("travel_date", TRAVEL_DATE),
        **kw,
    )


def ride_numbers(it) -> list[str]:
    return [r.train.number for r in it.rides]


@pytest.fixture
def engine() -> JourneySearchEngine:
    return build_engine()
