"""HTTP API and the scripted demo scenarios on the simulated demo dataset."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from app.services import SIMULATED_LABEL
from app.core.timeutil import FixedClock

NOW = datetime(2026, 10, 30, 10, 0)
DEMO_DATE = date(2026, 11, 6)


@pytest.fixture(scope="module")
def client() -> TestClient:
    settings = replace(load_settings(), timetable="simulated", demo_date=DEMO_DATE, availability_provider="simulated")
    return TestClient(create_app(settings, clock=FixedClock(NOW)))


@pytest.fixture(scope="module")
def samples(client) -> dict[str, dict]:
    return {s["id"]: s["request"] for s in client.get("/meta").json()["samples"]}


def _search(client, request: dict) -> dict:
    response = client.post("/journeys/search", json=request)
    assert response.status_code == 200, response.text
    return response.json()


def test_health_and_meta(client):
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["mode"] == "demo"
    assert health["availability_live"] is False
    meta = client.get("/meta").json()
    assert meta["demo_date"] == DEMO_DATE.isoformat()
    assert meta["data_notice"]["label"] == SIMULATED_LABEL
    assert len(meta["samples"]) >= 3
    assert any(p["name"] == "Diwali" for p in meta["rush_periods"])


def test_station_autocomplete(client):
    names = [p["name"] for p in client.get("/stations", params={"query": "jai"}).json()]
    assert names[0] == "Jaipur (all stations)"
    assert "Jaipur Jn" in names
    by_code = client.get("/stations", params={"query": "NDLS"}).json()
    assert by_code[0]["code"] == "NDLS"
    assert client.get("/stations", params={"query": "gurgaon"}).json()[0]["code"] == "GGN"
    assert client.get("/stations", params={"query": ""}).json() == []


def test_demo_delhi_to_jaipur_finds_alternatives_when_direct_is_full(client, samples):
    body = _search(client, samples["delhi-jaipur-diwali"])
    assert body["data_notice"]["label"] == SIMULATED_LABEL
    assert body["data_notice"]["mode"] == "demo"
    assert body["rush"]["festival"] == "Diwali"
    preferred = body["preferred"]
    assert preferred is not None and preferred["overall_status"] != "CONFIRMED"
    direct = [it for it in body["itineraries"] if it["primary_category"] == "direct"]
    assert direct and all(it["overall_status"] != "CONFIRMED" for it in direct)
    confirmed = [it for it in body["itineraries"] if it["overall_status"] == "CONFIRMED"]
    assert confirmed, "at least one alternative must have (simulated) seats"
    kinds = {it["primary_category"] for it in confirmed}
    assert {"alternative_boarding", "connecting", "smart_ticket"} <= kinds
    assert body["itineraries"][0]["overall_status"] == "CONFIRMED"
    best = body["itineraries"][0]
    assert best["why"] and best["fits"] and best["vs_preferred"] is not None
    for it in body["itineraries"]:
        assert it["contains_simulated"] is True
        for leg in it["legs"]:
            if leg["kind"] == "train":
                assert leg["train"]["simulated"] is True and leg["train"]["number"].startswith("SIM-")
                for t in leg["tickets"]:
                    assert t["booking"]["bookable"] is False
                    assert t["fare"]["is_estimate"] is True
                    if t["availability"]:
                        assert t["availability"]["is_live"] is False
                        assert t["availability"]["is_simulated"] is True
    rewari = next(it for it in confirmed if it["primary_category"] == "alternative_boarding")
    assert rewari["legs"][-1]["from_station"]["code"] == "RE"
    assert any("Rewari" in line for line in rewari["why"])
    assert body["search_stats"]["rejected_short_connections"] > 0


def test_demo_ajmer_offers_nearby_destination(client, samples):
    body = _search(client, samples["delhi-ajmer-sleeper"])
    top = body["itineraries"][0]
    assert top["primary_category"] == "alternative_destination"
    assert top["overall_status"] == "CONFIRMED"
    assert top["legs"][-1]["kind"] == "road" and top["legs"][-1]["purpose"] == "onward"
    assert top["legs"][0]["to_station"]["code"] == "KSG"


def test_demo_kota_offers_overnight_split_and_other_dates(client, samples):
    body = _search(client, samples["nizamuddin-kota-overnight"])
    split = next(it for it in body["itineraries"] if it["legs"][0]["tickets"] and len(it["legs"][0]["tickets"]) == 2)
    assert split["overall_status"] == "CONFIRMED"
    assert split["legs"][0]["day_change"] == 1
    assert split["arrive_at"].startswith("2026-11-07")
    assert body["date_strip"] and len(body["date_strip"]) == 3
    assert any(it["primary_category"] == "flexible_date" and it["overall_status"] == "CONFIRMED" for it in body["itineraries"])


def test_sort_parameter_orders_results(client, samples):
    for mode, key in (("cheapest", "cost_per_person"), ("fastest", "total_minutes"), ("fewest_transfers", "transfers")):
        body = _search(client, {**samples["delhi-jaipur-diwali"], "sort": mode})
        values = [it[key] for it in body["itineraries"]]
        assert values == sorted(values), mode


def test_saved_journey_can_be_rechecked(client, samples):
    body = _search(client, samples["delhi-jaipur-diwali"])
    chosen = body["itineraries"][2]
    response = client.get(f"/journeys/{chosen['id']}")
    assert response.status_code == 200
    again = response.json()["itinerary"]
    assert [leg["from_station"]["code"] for leg in again["legs"]] == [leg["from_station"]["code"] for leg in chosen["legs"]]
    assert again["overall_status"] == chosen["overall_status"]
    assert response.json()["data_notice"]["label"] == SIMULATED_LABEL


@pytest.mark.parametrize(
    ("change", "status", "code"),
    [
        ({"destination": "NDLS"}, 422, "SAME_ORIGIN_DESTINATION"),
        ({"date": "2026-10-01"}, 422, "INVALID_DATE"),
        ({"date": "2027-03-01"}, 422, "INVALID_DATE"),
        ({"origin": "Xyzzy"}, 404, "UNKNOWN_STATION"),
        ({"passengers": 9}, 422, "INVALID_REQUEST"),
        ({"travel_class": "EC"}, 422, "INVALID_REQUEST"),
        ({"max_transfers": 7}, 422, "INVALID_REQUEST"),
    ],
)
def test_bad_searches_get_friendly_errors(client, samples, change, status, code):
    response = client.post("/journeys/search", json={**samples["delhi-jaipur-diwali"], **change})
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"] and "Traceback" not in response.text


def test_invalid_journey_links(client):
    assert client.get("/journeys/not-a-real-journey").json()["error"]["code"] == "INVALID_JOURNEY_LINK"
    assert client.get("/no/such/route").json()["error"]["code"] == "NOT_FOUND"


def test_availability_check_endpoint(client):
    payload = {
        "passengers": 1,
        "checks": [
            {"train_number": "SIM-1203", "journey_date": "2026-11-06", "from_code": "RE", "to_code": "JP", "travel_class": "3A"},
            {"train_number": "SIM-1203", "journey_date": "2026-11-06", "from_code": "DO", "to_code": "JP", "travel_class": "3A"},
            {"train_number": "SIM-1305", "journey_date": "2026-11-08", "from_code": "NDLS", "to_code": "JP", "travel_class": "CC"},
            {"train_number": "SIM-9999", "journey_date": "2026-11-06", "from_code": "NDLS", "to_code": "JP", "travel_class": "3A"},
        ],
    }
    results = client.post("/availability/check", json=payload).json()["results"]
    assert results[0]["ok"] and results[0]["availability"]["status"] == "CONFIRMED"
    assert results[0]["availability"]["is_simulated"] is True and results[0]["availability"]["is_live"] is False
    assert not results[1]["ok"] and "does not halt" in results[1]["error"]
    assert not results[2]["ok"] and "does not leave" in results[2]["error"]  # Peacock Intercity skips Sundays
    assert not results[3]["ok"] and "not in the timetable" in results[3]["error"]


def test_no_provider_configured_shows_unknown(samples):
    settings = replace(load_settings(), timetable="simulated", demo_date=DEMO_DATE, availability_provider="none")
    client = TestClient(create_app(settings, clock=FixedClock(NOW)))
    body = _search(client, samples["delhi-jaipur-diwali"])
    assert body["data_notice"]["mode"] == "demo"
    assert all(it["overall_status"] != "CONFIRMED" for it in body["itineraries"])
    statuses = {t["availability"]["status"] for it in body["itineraries"] for leg in it["legs"] for t in leg["tickets"] if t["availability"]}
    assert statuses == {"UNKNOWN"}
