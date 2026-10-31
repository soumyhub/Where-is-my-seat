"""Train paths on track for the map: routing on a tiny graph, honest fallbacks, and the API."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from fastapi.testclient import TestClient

from app.config import load_settings
from app.core.railmap import RailMap
from app.core.timeutil import FixedClock
from app.main import create_app

# A —— B —— C along latitude 20; D is a detached piece of track; E sits on a long detour from A.
DOC = {
    "nodes": [[2000000, 7500000], [2000000, 7510000], [2000000, 7520000], [2050000, 7550000], [2100000, 7510000]],
    "edges": [
        [0, 1, 10450, [0, 5000]],  # A–B with one shape point halfway
        [1, 2, 10450, []],  # B–C
        [0, 4, 120000, []],  # A–E: far north
        [4, 2, 120000, []],  # E–C: and back
    ],
    "stations": {"A": [0, 10], "B": [1, 10], "C": [2, 10], "D": [3, 10], "E": [4, 10], "FAR": [0, 9000]},
}


def test_path_follows_track_through_intermediate_points():
    rm = RailMap(DOC)
    seg = rm.segment("A", "C", None, None)
    assert seg is not None and seg.matched
    assert seg.points[0] == (20.0, 75.0) and seg.points[-1] == (20.0, 75.2)
    assert (20.0, 75.05) in seg.points  # the shape point between A and B
    assert seg.km == 20.9


def test_gaps_and_far_stations_fall_back_to_straight_lines():
    rm = RailMap(DOC)
    gap = rm.segment("A", "D", (20.0, 75.0), (20.5, 75.5))
    assert gap is not None and not gap.matched and gap.points == ((20.0, 75.0), (20.5, 75.5))
    assert not rm.knows("FAR")  # snapped too far from any track
    assert rm.segment("A", "D", None, None) is None


def test_long_detours_are_not_drawn_as_the_route():
    rm = RailMap({**DOC, "edges": DOC["edges"][2:]})  # only the A–E–C detour is left
    seg = rm.segment("A", "C", (20.0, 75.0), (20.0, 75.2))
    assert seg is not None and not seg.matched


def test_journey_map_endpoint_draws_each_leg():
    settings = replace(load_settings(env_file=None), timetable="tag2026", availability_provider="none")
    client = TestClient(create_app(settings, clock=FixedClock(datetime(2026, 10, 30, 10, 0))))
    search = client.post(
        "/journeys/search", json={"origin": "NDLS", "destination": "JP", "date": "2026-11-06", "travel_class": "3A"}
    ).json()
    it = search["itineraries"][0]
    body = client.get(f"/journeys/{it['id']}/map").json()
    assert body["attribution"].startswith("Railway lines © OpenStreetMap")
    train = body["legs"][0]
    assert train["kind"] == "train" and train["stops"][0]["role"] == "board" and train["stops"][-1]["role"] == "alight"
    assert all(len(s["points"]) >= 2 for s in train["segments"])
    lat_min, lon_min = body["bounds"][0]
    assert 26 < lat_min < 29 and 75 < lon_min < 78
    if body["available"]:
        assert body["track_share"] >= 0.5  # most of Delhi–Jaipur follows mapped track
    assert client.get("/journeys/not-a-real-journey-id/map").status_code == 400
