"""The real Trains at a Glance 2026 network: data integrity and honest behaviour without live seats."""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.core.data_loader import load_dataset
from app.core.models import Stop, Train
from app.core.timeutil import FixedClock
from app.main import create_app

NOW = datetime(2026, 10, 30, 10, 0)
FRIDAY = "2026-11-06"


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(load_settings().data_dir, "tag2026")


@pytest.fixture(scope="module")
def client() -> TestClient:
    settings = replace(load_settings(), timetable="tag2026", availability_provider="auto")
    return TestClient(create_app(settings, clock=FixedClock(NOW)))


def test_real_dataset_has_national_coverage(dataset):
    assert len(dataset.trains) >= 2500
    assert len(dataset.stations) >= 800
    assert sum(s.junction for s in dataset.stations) >= 300
    assert not any(t.simulated for t in dataset.trains)
    assert all(len(t.number) == 5 and t.number.isdigit() for t in dataset.trains)
    codes = {s.code for s in dataset.stations}
    assert {"NDLS", "HWH", "CSMT", "MAS", "SBC", "SC", "JP", "DDU", "VGLJ", "ET", "BPL"} <= codes


def test_known_train_has_real_name_and_times(dataset):
    shatabdi = next(t for t in dataset.trains if t.number == "12015")
    assert "Ajmer Shatabdi" in shatabdi.name
    assert shatabdi.stops[0].station == "NDLS" and shatabdi.stops[-1].station == "AII"
    assert shatabdi.stops[0].dep == 6 * 60 + 10  # 06:10 per TAG 2026
    assert set(shatabdi.classes) == {"EC", "CC"}


def test_seasonal_window_wraps_the_year():
    stop = Stop(0, "A", None, 0, 0)
    end = Stop(1, "B", 60, None, 50)
    winter = Train("1", "t", "Express", frozenset(range(7)), ("SL",), False, False, (stop, end), False, "x",
                   valid_from="11-01", valid_to="06-09")
    assert winter.runs_on_date(date(2026, 12, 25))
    assert winter.runs_on_date(date(2027, 3, 1))
    assert not winter.runs_on_date(date(2026, 8, 15))


def test_notice_is_honest_about_seats(client):
    meta = client.get("/meta").json()
    notice = meta["data_notice"]
    assert notice["mode"] == "timetable"
    assert notice["timetable_simulated"] is False
    assert notice["availability_live"] is False and notice["availability_simulated"] is False
    assert "NOT LIVE" in notice["label"]
    assert meta["samples"], "real-network sample searches must resolve"


def test_station_search_knows_junctions_and_old_names(client):
    assert client.get("/stations", params={"query": "VGLJ"}).json()[0]["code"] == "VGLJ"
    assert any(p["code"] == "DDU" for p in client.get("/stations", params={"query": "mughalsarai"}).json())
    names = [p["name"] for p in client.get("/stations", params={"query": "mumbai"}).json()]
    assert names[0] == "Mumbai (all stations)"


def test_delhi_jaipur_lists_real_trains_without_claiming_seats(client):
    started = time.monotonic()
    body = client.post(
        "/journeys/search",
        json={"origin": "city:delhi", "destination": "city:jaipur", "date": FRIDAY, "travel_class": "3A"},
    ).json()
    assert time.monotonic() - started < 8
    direct = [it for it in body["itineraries"] if it["primary_category"] == "direct"]
    assert len(direct) >= 5
    assert "full" not in body["summary"]["headline"].lower()
    for it in body["itineraries"]:
        assert it["contains_simulated"] is False
        assert it["overall_status"] in ("UNKNOWN", "UNRESERVED")
        for leg in it["legs"]:
            for t in leg["tickets"]:
                if t["availability"]:
                    assert t["availability"]["status"] == "UNKNOWN"
                    assert t["availability"]["is_live"] is False and t["availability"]["is_simulated"] is False
                assert t["booking"]["bookable"] is True  # real train: book on the official site
    strategies = {i["strategy"] for it in direct for i in it["ideas"]}
    assert {"book_beyond", "upstream_boarding", "split"} & strategies


def test_long_distance_search_finds_direct_trains(client):
    body = client.post(
        "/journeys/search",
        json={"origin": "city:delhi", "destination": "city:chennai", "date": FRIDAY, "travel_class": "3A"},
    ).json()
    direct = [it for it in body["itineraries"] if it["primary_category"] == "direct"]
    assert direct, body["no_results_message"]
    assert all(it["total_minutes"] > 20 * 60 for it in direct)
    assert any(leg["day_change"] >= 1 for it in direct for leg in it["legs"])


def test_full_station_directory_reaches_small_stations(client, dataset):
    assert len(dataset.stations) >= 8000
    served = [s for s in dataset.stations if s.served]
    assert 700 <= len(served) < len(dataset.stations)
    hits = client.get("/stations", params={"query": "bareilly", "limit": 5}).json()
    assert hits[0]["served"] is True  # stations with trains come before ones without
    badhal = client.get("/stations", params={"query": "badhal"}).json()[0]
    assert badhal["code"] == "BDHL" and badhal["served"] is False


def test_search_from_station_without_trains_starts_at_nearest_station(client):
    body = client.post(
        "/journeys/search",
        json={"origin": "BDHL", "destination": "city:delhi", "date": FRIDAY, "include_nearby": False},
    ).json()
    assert body["summary"]["headline"] == "No train in our timetable stops at Badhal"
    assert "Ringus" in body["summary"]["subline"]
    first = body["itineraries"][0]["legs"][0]
    assert first["kind"] == "road" and first["from_station"]["code"] == "BDHL"


def test_trains_recovered_from_their_own_name_are_flagged(dataset):
    nandigram = next(t for t in dataset.trains if t.number == "11002")
    assert nandigram.stops[0].station == "BPQ"
    assert any("first listed station" in n for n in nandigram.notes)
