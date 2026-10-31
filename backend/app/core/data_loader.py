"""Load and validate the JSON datasets.

The loader is strict on purpose: a broken timetable must fail at startup with a clear
message instead of producing wrong journeys later. Parsers accept already-decoded
dicts so tests can build small fixture networks without touching the filesystem.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .festivals import Festival
from .models import RESERVED_CLASSES, WEEKDAY_NAMES, City, Station, Stop, Train
from .timeutil import parse_hhmm


class DatasetError(ValueError):
    """Raised when a dataset file is missing or inconsistent."""


@dataclass(frozen=True)
class Dataset:
    stations: list[Station]
    cities: list[City]
    trains: list[Train]
    station_meta: dict[str, Any] = field(default_factory=dict)
    timetable_meta: dict[str, Any] = field(default_factory=dict)
    road_overrides: list[dict[str, Any]] = field(default_factory=list)
    festivals: list[Festival] = field(default_factory=list)
    availability_rules: dict[str, Any] = field(default_factory=dict)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise DatasetError(f"Dataset file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"{path.name} is not valid JSON: {exc}") from exc


def load_dataset(data_dir: Path, timetable: str = "tag2026") -> Dataset:
    """Load stations, the chosen timetable set and supporting files from ``data_dir``.

    A timetable folder may carry its own ``stations.json`` (the real network does);
    otherwise the shared ``data/stations.json`` is used.
    """
    timetable_dir = data_dir / timetable
    if not timetable_dir.is_dir():
        raise DatasetError(f"Unknown timetable {timetable!r}: no folder {timetable_dir}")
    station_file = timetable_dir / "stations.json"
    if not station_file.exists():
        station_file = data_dir / "stations.json"
    stations, cities, station_meta = parse_stations(_read_json(station_file))
    trains, timetable_meta = parse_trains(
        _read_json(timetable_dir / "trains.json"),
        {s.code for s in stations},
        require_simulated=(timetable == "simulated"),
    )
    rules_path = timetable_dir / "availability_rules.json"
    rules = _read_json(rules_path) if rules_path.exists() else {}
    road_path = data_dir / "road_transfers.json"
    road = _read_json(road_path).get("pairs", []) if road_path.exists() else []
    festivals_path = data_dir / "festivals.json"
    festivals = parse_festivals(_read_json(festivals_path)) if festivals_path.exists() else []
    return Dataset(
        stations=stations,
        cities=cities,
        trains=trains,
        station_meta=station_meta,
        timetable_meta=timetable_meta,
        road_overrides=road,
        festivals=festivals,
        availability_rules=rules,
    )


def parse_stations(doc: dict[str, Any]) -> tuple[list[Station], list[City], dict[str, Any]]:
    raw_cities = doc.get("cities", {})
    raw_stations = doc.get("stations", [])
    if not raw_stations:
        raise DatasetError("stations.json contains no stations")
    stations: list[Station] = []
    seen: set[str] = set()
    for row in raw_stations:
        code = str(row.get("code", "")).strip().upper()
        if not code or code in seen:
            raise DatasetError(f"Missing or duplicate station code: {code!r}")
        seen.add(code)
        city = row.get("city")
        if city not in raw_cities:
            raise DatasetError(f"Station {code} refers to unknown city {city!r}")
        stations.append(
            Station(
                code=code,
                name=row["name"],
                city=city,
                state=row.get("state", ""),
                lat=row.get("lat"),
                lon=row.get("lon"),
                junction=bool(row.get("junction", False)),
                aliases=tuple(a.lower() for a in row.get("aliases", [])),
                halts=row.get("halts"),
            )
        )
    cities: list[City] = []
    for key, row in raw_cities.items():
        anchor = row.get("anchor")
        if anchor not in seen:
            raise DatasetError(f"City {key} has unknown anchor station {anchor!r}")
        cities.append(
            City(
                key=key,
                name=row["name"],
                anchor=anchor,
                aliases=tuple(a.lower() for a in row.get("aliases", [])),
            )
        )
    return stations, cities, doc.get("meta", {})


def _parse_runs_on(value: Any, number: str) -> frozenset[int]:
    if value == "daily":
        return frozenset(range(7))
    if not isinstance(value, list) or not value:
        raise DatasetError(f"{number}: runs_on must be 'daily' or a list of weekday names")
    days: set[int] = set()
    for name in value:
        if name not in WEEKDAY_NAMES:
            raise DatasetError(f"{number}: unknown weekday {name!r}")
        days.add(WEEKDAY_NAMES.index(name))
    return frozenset(days)


def _parse_stops(rows: list[dict[str, Any]], number: str, known: set[str]) -> tuple[Stop, ...]:
    if len(rows) < 2:
        raise DatasetError(f"{number}: a train needs at least two stops")
    stops: list[Stop] = []
    last_minute = -1
    last_km = -1
    seen: set[str] = set()
    for index, row in enumerate(rows):
        code = row.get("code")
        if code not in known:
            raise DatasetError(f"{number}: stop {index} uses unknown station {code!r}")
        if code in seen:
            raise DatasetError(f"{number}: visits {code} twice; split looping services")
        seen.add(code)
        day = int(row.get("day", 1))
        base = (day - 1) * 1440
        arr = base + parse_hhmm(row["arr"]) if row.get("arr") else None
        dep = base + parse_hhmm(row["dep"]) if row.get("dep") else None
        if arr is not None and dep is not None and dep < arr:
            dep += 1440  # departs after midnight
        if index == 0 and (dep is None or arr is not None):
            raise DatasetError(f"{number}: the first stop must have only a departure time")
        if index == len(rows) - 1 and (arr is None or dep is not None):
            raise DatasetError(f"{number}: the last stop must have only an arrival time")
        if 0 < index < len(rows) - 1 and (arr is None or dep is None):
            raise DatasetError(f"{number}: intermediate stop {code} needs arrival and departure")
        for moment in (arr, dep):
            if moment is not None:
                if moment < last_minute:
                    raise DatasetError(f"{number}: times go backwards at {code} (check 'day')")
                last_minute = moment
        km = int(row.get("km", 0))
        if km < last_km:
            raise DatasetError(f"{number}: distance decreases at {code}")
        last_km = km
        stops.append(
            Stop(
                index=index,
                station=code,
                arr=arr,
                dep=dep,
                km=km,
                technical=bool(row.get("technical", False)),
            )
        )
    return tuple(stops)


def parse_trains(
    doc: dict[str, Any], known_stations: set[str], *, require_simulated: bool = False
) -> tuple[list[Train], dict[str, Any]]:
    meta = doc.get("meta", {})
    trains: list[Train] = []
    numbers: set[str] = set()
    for row in doc.get("trains", []):
        number = str(row.get("number", "")).strip()
        if not number or number in numbers:
            raise DatasetError(f"Missing or duplicate train number: {number!r}")
        numbers.add(number)
        simulated = bool(row.get("simulated", meta.get("simulated", False)))
        if require_simulated and not simulated:
            raise DatasetError(
                f"{number}: the simulated timetable may only contain records marked simulated"
            )
        classes = tuple(row.get("classes", []))
        for cls in classes:
            if cls not in RESERVED_CLASSES:
                raise DatasetError(f"{number}: unknown class {cls!r}")
        unreserved = bool(row.get("unreserved", not classes))
        if not classes and not unreserved:
            raise DatasetError(f"{number}: train sells no tickets (no classes, no UR)")
        valid = row.get("valid") or {}
        for key in ("from", "to"):
            if valid and not re.fullmatch(r"\d{2}-\d{2}", str(valid.get(key, ""))):
                raise DatasetError(f"{number}: seasonal window needs MM-DD 'from' and 'to'")
        trains.append(
            Train(
                number=number,
                name=row["name"],
                category=row.get("category", "Express"),
                runs_on=_parse_runs_on(row.get("runs_on", "daily"), number),
                classes=classes,
                unreserved=unreserved,
                superfast=bool(row.get("superfast", False)),
                stops=_parse_stops(row.get("stops", []), number, known_stations),
                simulated=simulated,
                source=row.get("source", meta.get("source", "unknown")),
                valid_from=valid.get("from"),
                valid_to=valid.get("to"),
                notes=tuple(row.get("notes") or ()),
            )
        )
    if not trains:
        raise DatasetError("Timetable contains no trains")
    return trains, meta


def parse_festivals(doc: dict[str, Any]) -> list[Festival]:
    out: list[Festival] = []
    for row in doc.get("periods", []):
        out.append(
            Festival(
                name=row["name"],
                date=date.fromisoformat(row["date"]),
                before=int(row.get("before", 3)),
                after=int(row.get("after", 2)),
                level=row.get("level", "medium"),
            )
        )
    return out
