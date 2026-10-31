"""Dataset loading and validation."""

from __future__ import annotations

import copy

import pytest

from app.config import load_settings
from app.core.data_loader import DatasetError, load_dataset, parse_trains

from .conftest import STATIONS_DOC, TRAINS_DOC

KNOWN = {s["code"] for s in STATIONS_DOC["stations"]}


def test_demo_dataset_loads_and_is_fully_simulated():
    ds = load_dataset(load_settings().data_dir, "simulated")
    assert len(ds.stations) >= 30
    assert ds.trains and all(t.simulated for t in ds.trains)
    assert all(t.number.startswith("SIM-") for t in ds.trains)
    assert ds.timetable_meta["simulated"] is True
    codes = {s.code for s in ds.stations}
    assert {"NDLS", "JP", "RE", "AII", "KOTA"} <= codes


def test_overnight_times_get_running_days():
    ds = load_dataset(load_settings().data_dir, "simulated")
    night = next(t for t in ds.trains if t.number == "SIM-1407")
    jp = night.stops[night.index_of("JP")]
    assert jp.day == 2 and jp.arr == 1440 + 4 * 60 + 10


def _with(change) -> dict:
    doc = copy.deepcopy(TRAINS_DOC)
    change(doc["trains"][0])
    return doc


def test_times_going_backwards_are_rejected():
    def broken(train):
        train["stops"][1]["arr"] = "07:00"  # before the 08:00 departure
    with pytest.raises(DatasetError, match="backwards"):
        parse_trains(_with(broken), KNOWN)


def test_unknown_station_is_rejected():
    def broken(train):
        train["stops"][1]["code"] = "ZZZ"
    with pytest.raises(DatasetError, match="unknown station"):
        parse_trains(_with(broken), KNOWN)


def test_simulated_folder_only_accepts_simulated_records():
    def real(train):
        train["simulated"] = False
    doc = _with(real)
    doc["meta"]["simulated"] = False
    with pytest.raises(DatasetError, match="simulated"):
        parse_trains(doc, KNOWN, require_simulated=True)


def test_unknown_class_is_rejected():
    def broken(train):
        train["classes"] = ["9Z"]
    with pytest.raises(DatasetError, match="unknown class"):
        parse_trains(_with(broken), KNOWN)
