"""Opt-in live seats through RailRadar: mapping, cache, monthly cap — all without the network."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

from fastapi.testclient import TestClient

from app.config import load_settings
from app.core.availability import AvailabilityStatus, RailRadarProvider, TicketQuery
from app.core.availability.railradar import parse_entry
from app.core.timeutil import FixedClock
from app.main import create_app

NOW = datetime(2026, 10, 30, 10, 0)

# The documented example response (railradar.in/docs/seat-availability), trimmed.
SAMPLE = {
    "success": True,
    "data": {
        "trainNumber": "12958",
        "classCode": "3A",
        "quotaCode": "GN",
        "calendar": [
            {"date": "2026-11-06", "status": "AVAILABLE-0042", "statusCode": "AVAILABLE",
             "isAvailable": True, "availableSeats": 42},
            {"date": "2026-11-07", "status": "RAC 24/RAC 12", "statusCode": "RAC", "isAvailable": False,
             "waitlistNumber": 12},
            {"date": "2026-11-08", "status": "GNWL24/WL11", "statusCode": "WAITLIST", "isAvailable": False,
             "waitlistNumber": 11, "waitlistType": "GNWL"},
            {"date": "2026-11-09", "status": "REGRET/WL", "statusCode": "REGRET", "isAvailable": False},
        ],
    },
}


class FakeFetch:
    def __init__(self, body=SAMPLE):
        self.body = body
        self.urls: list[str] = []

    def __call__(self, url, headers, timeout):
        assert headers["Authorization"] == "Bearer test-key"
        self.urls.append(url)
        return self.body


def query(day: str) -> TicketQuery:
    return TicketQuery("12958", date.fromisoformat(day), "NDLS", "JP", "3A")


def test_statuses_map_to_seat_states():
    entries = SAMPLE["data"]["calendar"]
    assert parse_entry(entries[0]) == (AvailabilityStatus.CONFIRMED, 42)
    assert parse_entry(entries[1]) == (AvailabilityStatus.RAC, 12)
    assert parse_entry(entries[2]) == (AvailabilityStatus.WAITLISTED, 11)
    assert parse_entry(entries[3]) == (AvailabilityStatus.UNAVAILABLE, None)
    assert parse_entry({"status": "SOMETHING NEW"}) == (AvailabilityStatus.UNKNOWN, None)


def test_one_request_answers_every_date_it_returns(tmp_path):
    fetch = FakeFetch()
    p = RailRadarProvider("test-key", FixedClock(NOW), state_path=tmp_path / "usage.json", fetch=fetch)
    first = p.check(query("2026-11-06"))
    assert first.status is AvailabilityStatus.CONFIRMED and first.count == 42 and first.is_live
    assert "journeyDate=2026-11-06" in fetch.urls[0] and "source=NDLS" in fetch.urls[0]
    assert p.check(query("2026-11-08")).label == "WL 11"
    assert p.check(query("2026-11-06")).count == 42
    assert len(fetch.urls) == 1  # the other dates came from the cache
    assert p.describe()["used_this_month"] == 1


def test_30_day_limit_is_never_exceeded_and_survives_restarts(tmp_path):
    state = tmp_path / "usage.json"
    clock = FixedClock(NOW)
    fetch = FakeFetch({"success": True, "data": {"calendar": []}})
    p = RailRadarProvider("test-key", clock, monthly_limit=2, cache_minutes=0, state_path=state, fetch=fetch)
    for _ in range(5):
        p.check(query("2026-11-20"))
    assert len(fetch.urls) == 2
    again = RailRadarProvider("test-key", clock, monthly_limit=2, state_path=state, fetch=fetch)
    blocked = again.check(query("2026-11-21"))
    assert blocked.status is AvailabilityStatus.UNKNOWN and "used up" in (blocked.note or "")
    assert len(fetch.urls) == 2
    clock.current = datetime(2026, 11, 20, 9, 0)  # still inside the same 30 days: blocked
    again.check(query("2026-11-22"))
    assert len(fetch.urls) == 2
    clock.current = datetime(2026, 11, 30, 10, 1)  # 30 days after the first requests: free again
    again.check(query("2026-11-21"))
    assert len(fetch.urls) == 3


def test_live_key_is_used_for_ticket_checks_but_never_inside_search(tmp_path, monkeypatch):
    fetch = FakeFetch()
    monkeypatch.setattr("app.core.availability.railradar._http_fetch", fetch)
    settings = replace(
        load_settings(env_file=None), timetable="tag2026", availability_provider="railradar",
        railradar_key="test-key", state_dir=tmp_path,
    )
    client = TestClient(create_app(settings, clock=FixedClock(NOW)))
    meta = client.get("/meta").json()["data_notice"]
    assert meta["live_checks"] is True and meta["mode"] == "timetable"
    search = client.post("/journeys/search", json={"origin": "NDLS", "destination": "JP", "date": "2026-11-06"})
    assert search.status_code == 200 and fetch.urls == []
    check = client.post(
        "/availability/check",
        json={"checks": [{"train_number": "12958", "journey_date": "2026-11-06", "from_code": "NDLS",
                          "to_code": "JP", "travel_class": "3A"}]},
    ).json()
    result = check["results"][0]["availability"]
    assert result["status"] == "CONFIRMED" and result["is_live"] and "RailRadar" in result["source"]
    assert check["live_usage"]["used_this_month"] == 1 and check["live_usage"]["remaining_this_month"] == 89
    assert client.get("/availability/usage").json()["used_this_month"] == 1


def test_free_plan_without_seats_switches_live_checks_off(tmp_path, monkeypatch):
    from app.core.availability.railradar import PlanNotIncluded

    calls: list[str] = []

    def no_seats(url, headers, timeout):
        calls.append(url)
        raise PlanNotIncluded("RailRadar's free plan does not include seat availability")

    monkeypatch.setattr("app.core.availability.railradar._http_fetch", no_seats)
    settings = replace(
        load_settings(env_file=None), timetable="tag2026", availability_provider="railradar",
        railradar_key="test-key", state_dir=tmp_path,
    )
    clock = FixedClock(NOW)
    client = TestClient(create_app(settings, clock=clock))
    assert client.get("/meta").json()["data_notice"]["live_checks"] is True
    check = {"checks": [{"train_number": "12958", "journey_date": "2026-11-06", "from_code": "NDLS",
                         "to_code": "JP", "travel_class": "3A"}]}
    body = client.post("/availability/check", json=check).json()
    result = body["results"][0]["availability"]
    assert result["status"] == "UNKNOWN" and "paid Developer plan" in result["note"]
    assert body["live_usage"]["used_this_month"] == 0  # failed requests are given back
    assert body["live_usage"]["available"] is False and body["live_usage"]["blocked_reason"]
    assert body["data_notice"]["live_checks"] is False
    client.post("/availability/check", json=check)
    assert len(calls) == 1  # no more requests while the plan lacks seats
    # A restart remembers it; a day later it asks RailRadar again.
    again = TestClient(create_app(settings, clock=clock))
    assert again.get("/meta").json()["data_notice"]["live_checks"] is False
    clock.current = datetime(2026, 10, 31, 11, 0)
    again.post("/availability/check", json=check)
    assert len(calls) == 2
