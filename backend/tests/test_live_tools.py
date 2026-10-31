"""Live tools from RailRadar's free plan: normalised answers, caching, one shared budget."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from fastapi.testclient import TestClient

from app.config import load_settings
from app.core.availability.railradar import PlanNotIncluded
from app.core.timeutil import FixedClock
from app.main import create_app

NOW = datetime(2026, 10, 30, 10, 0)

# Small answers shaped like RailRadar's documented responses.
ANSWERS = {
    "/trains/12958/live": {
        "trainNumber": "12958", "trainName": "Swarna Jayanti Rajdhani", "startDate": "2026-10-30",
        "status": "running", "isLive": True, "trackingMode": "real-time", "delayMinutes": 12,
        "lastUpdatedAt": "2026-10-30T09:55:00+05:30",
        "currentLocation": {"stationCode": "RE", "stationName": "Rewari", "status": "departed", "speedKmh": 96.4},
        "previousHalt": {"stationCode": "RE", "stationName": "Rewari"},
        "nextHalt": {"stationCode": "JP", "stationName": "Jaipur Jn"},
        "exceptions": [{"type": "rescheduled", "message": "Rescheduled by 10 min"}],
        "route": [
            {"stationCode": "NDLS", "stationName": "New Delhi", "isHalt": True,
             "scheduledDeparture": "2026-10-30T19:55:00+05:30", "actualDeparture": "2026-10-30T20:05:00+05:30",
             "delayDeparture": 10, "platform": "1", "status": "departed"},
            {"stationCode": "XYZ", "stationName": "Passing", "isHalt": False},
            {"stationCode": "JP", "stationName": "Jaipur Jn", "isHalt": True,
             "scheduledArrival": "2026-10-30T23:45:00+05:30", "delayArrival": 12, "status": "upcoming"},
        ],
    },
    "/stations/NDLS/live": {
        "station": {"code": "NDLS", "name": "New Delhi"}, "window": {"from": "08:00", "to": "12:00"},
        "trains": [
            {"train": {"number": "12015", "name": "Ajmer Shatabdi", "type": "Shatabdi", "source": "NDLS", "destination": "AII"},
             "stop": {"arrival": None, "departure": "06:10"},
             "live": {"type": "departed", "expectedDepartureTime": "2026-10-30T06:20:00+05:30", "platform": "1", "delayMinutes": 10}},
        ],
    },
    "/trains/12958/fare": {"distance": 309, "breakdown": {"baseFare": 585, "reservationCharge": 40, "cateringCharge": 185,
                                                          "goodsServiceTax": 46, "dynamicFare": 234, "superfastCharge": 45,
                                                          "tatkalFare": 0, "totalFare": 1135}},
    "/trains/12958/coaches/JP": {"station": {"code": "JP", "name": "Jaipur Jn", "platform": "2"}, "reversal": False,
                                 "rake": [{"position": 1, "code": "ENG", "classType": "LOCO", "className": "Engine"},
                                          {"position": 2, "code": "B1", "classType": "3A", "className": "AC 3-Tier"}]},
    "/trains/12958/delay": {"summary": {"averageArrivalDelayMinutes": 7, "averageDepartureDelayMinutes": 12,
                                        "punctualityPercentage": 60,
                                        "maxDelayStation": {"stationCode": "ABR", "stationName": "Abu Road", "delayMinutes": 22}},
                            "route": [{"stationCode": "JP", "stationName": "Jaipur Jn", "arrivalDelayMinutes": 5}]},
    "/trains/exceptions": {"summary": {"updatedAt": "2026-10-30T05:00:00Z"},
                           "trains": [{"trainNumber": "12958", "startDate": "2026-10-30", "primaryType": "DIVERTED",
                                       "message": "Diverted via Alwar"},
                                      {"trainNumber": "18426", "primaryType": "CANCELLED", "message": "Cancelled"}]},
}


class Fake:
    def __init__(self):
        self.urls: list[str] = []

    def __call__(self, url, headers, timeout):
        assert headers["Authorization"] == "Bearer test-key"
        self.urls.append(url)
        path = url.split("/v1", 1)[1].split("?")[0]
        if path == "/trains/99999/live":
            raise PlanNotIncluded("not in plan")
        return {"success": True, "data": ANSWERS[path]}


def make(tmp_path, monkeypatch, limit=90):
    fake = Fake()
    monkeypatch.setattr("app.core.live._http_fetch", fake)
    settings = replace(
        load_settings(env_file=None), timetable="tag2026", availability_provider="none",
        railradar_key="test-key", state_dir=tmp_path, live_monthly_limit=limit,
    )
    clock = FixedClock(NOW)
    return TestClient(create_app(settings, clock=clock)), fake, clock


def test_running_status_is_normalised_and_cached(tmp_path, monkeypatch):
    client, fake, clock = make(tmp_path, monkeypatch)
    body = client.get("/live/trains/12958", params={"date": "2026-10-30"}).json()
    d = body["data"]
    assert d["delay_minutes"] == 12 and d["current"]["name"] == "Rewari" and d["next_halt"]["code"] == "JP"
    assert [h["code"] for h in d["halts"]] == ["NDLS", "JP"]  # non-halting points dropped
    assert d["halts"][0]["actual_departure"] == "20:05" and d["alerts"] == ["Rescheduled by 10 min"]
    assert "RailRadar" in body["source"] and body["cached"] is False and body["requests_left"] == 89
    again = client.get("/live/trains/12958", params={"date": "2026-10-30"}).json()
    assert again["cached"] is True and len(fake.urls) == 1
    clock.current = datetime(2026, 10, 30, 10, 3)  # running status is reused for 2 minutes only
    assert client.get("/live/trains/12958", params={"date": "2026-10-30"}).json()["cached"] is False


def test_every_free_tool_answers(tmp_path, monkeypatch):
    client, fake, _ = make(tmp_path, monkeypatch)
    board = client.get("/live/stations/ndls", params={"hours": 3}).json()["data"]
    assert board["station"]["code"] == "NDLS" and board["trains"][0]["expected_departure"] == "06:20"
    assert "hours=2" in fake.urls[-1] or "hours=4" in fake.urls[-1]
    fare = client.get("/live/fare", params={"train": "12958", "from_code": "NDLS", "to_code": "JP",
                                            "date": "2026-11-06", "travel_class": "3A"}).json()["data"]
    assert fare["total"] == 1135 and fare["parts"]["Catering"] == 185 and "Tatkal" not in fare["parts"]
    coaches = client.get("/live/trains/12958/coaches/JP").json()["data"]
    assert coaches["station"]["platform"] == "2" and coaches["coaches"][1]["code"] == "B1"
    punctual = client.get("/live/trains/12958/punctuality").json()["data"]
    assert punctual["on_time_percent"] == 60 and punctual["worst"]["name"] == "Abu Road"
    alerts = client.get("/live/trains/12958/alerts").json()["data"]
    assert alerts["items"] == [{"start_date": "2026-10-30", "type": "diverted", "message": "Diverted via Alwar"}]
    assert client.get("/live/trains/18426/alerts").json()["data"]["items"][0]["type"] == "cancelled"
    assert len(fake.urls) == 5  # the second alerts call reused the shared list
    usage = client.get("/availability/usage").json()
    assert usage["tools"] is True and usage["requests_used"] == 5 and usage["requests_left"] == 85


def test_limits_errors_and_missing_key(tmp_path, monkeypatch):
    client, fake, _ = make(tmp_path, monkeypatch, limit=1)
    blocked = client.get("/live/trains/99999")
    assert blocked.status_code == 402 and blocked.json()["error"]["code"] == "NOT_IN_FREE_PLAN"
    assert client.get("/availability/usage").json()["requests_used"] == 0  # failures are given back
    assert client.get("/live/trains/12958/punctuality").status_code == 200
    capped = client.get("/live/trains/12958/coaches/JP")
    assert capped.status_code == 429 and capped.json()["error"]["code"] == "LIVE_LIMIT_REACHED"
    assert client.get("/live/trains/123").status_code == 422
    plain = TestClient(create_app(replace(load_settings(env_file=None), timetable="tag2026", state_dir=tmp_path)))
    missing = plain.get("/live/trains/12958")
    assert missing.status_code == 409 and missing.json()["error"]["code"] == "LIVE_NOT_CONFIGURED"
