"""Live railway information from RailRadar's free plan, with the traveller's own key.

RailRadar (https://railradar.in) is an independent third party — not Indian Railways, IRCTC
or NTES — and calls its data crowd-powered. The free Sandbox key allows 100 requests per 30
days for personal, non-commercial use and covers everything except seat availability and
PNR. To make that last:

* every request goes through the same rolling 30-day cap as seat checks (default 90);
* answers are cached in memory and on disk, for as long as each kind of data stays useful
  (a minute or two for running status, a day for fares and coach positions, a week for
  punctuality) — a cached answer costs nothing;
* nothing is fetched in the background or inside a journey search; only when asked.

Every answer is normalised here, so the app does not depend on RailRadar's field names.
"""

from __future__ import annotations

import hashlib
import json
import threading
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .availability.base import ProviderError
from .availability.railradar import BASE_URL, SOURCE, Fetch, PlanNotIncluded, RollingQuota, _http_fetch
from .timeutil import Clock

TTL = {
    "train_live": timedelta(minutes=2),
    "station_live": timedelta(minutes=2),
    "fare": timedelta(hours=24),
    "coaches": timedelta(hours=24),
    "delay": timedelta(days=7),
    "exceptions": timedelta(hours=3),
}


class LiveUnavailable(ProviderError):
    """Live data cannot be fetched right now; ``code`` says why (for the API)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class LiveAnswer:
    data: dict[str, Any]
    fetched_at: datetime
    cached: bool


def _hhmm(value: Any) -> str | None:
    """'2026-10-29T19:55:00+05:30' or '19:55' -> '19:55'."""
    if not value or not isinstance(value, str):
        return None
    return value[11:16] if "T" in value else value[:5]


def _int(value: Any) -> int | None:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


class RailRadarLive:
    def __init__(
        self,
        api_key: str,
        clock: Clock,
        quota: RollingQuota,
        cache_path: Path | None = None,
        fetch: Fetch | None = None,
        base_url: str = BASE_URL,
        timeout: float = 10.0,
    ) -> None:
        self._key = api_key
        self._clock = clock
        self.quota = quota
        self._fetch = fetch or _http_fetch
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._cache_path = cache_path
        self._lock = threading.Lock()
        self._cache: dict[str, dict[str, Any]] = {}
        if cache_path and cache_path.exists():
            try:
                self._cache = json.loads(cache_path.read_text())
            except (ValueError, OSError):
                self._cache = {}

    source = SOURCE

    # ----- plumbing -----------------------------------------------------
    def _get(self, kind: str, path: str, params: dict[str, Any], shape: Callable[[Any], dict[str, Any]]) -> LiveAnswer:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{self._base}{path}" + (f"?{query}" if query else "")
        key = hashlib.sha1(f"{kind}|{url}".encode()).hexdigest()
        now = self._clock.now()
        with self._lock:
            hit = self._cache.get(key)
        if hit and now - datetime.fromisoformat(hit["at"]) <= TTL[kind]:
            return LiveAnswer(hit["data"], datetime.fromisoformat(hit["at"]), True)
        if not self.quota.take(now):
            raise LiveUnavailable(
                "LIVE_LIMIT_REACHED",
                f"The {self.quota.limit} free RailRadar requests for the last 30 days are used up.",
            )
        try:
            body = self._fetch(url, {"Authorization": f"Bearer {self._key}", "Accept": "application/json"}, self._timeout)
        except PlanNotIncluded as exc:
            self.quota.refund(now)
            raise LiveUnavailable("NOT_IN_FREE_PLAN", "RailRadar's free plan does not include this.") from exc
        except ProviderError as exc:
            self.quota.refund(now)
            raise LiveUnavailable("LIVE_SOURCE_ERROR", str(exc)) from exc
        if not isinstance(body, dict) or not body.get("success") or "data" not in body:
            raise LiveUnavailable("LIVE_SOURCE_ERROR", "RailRadar returned an unexpected answer.")
        data = shape(body["data"])
        with self._lock:
            self._cache[key] = {"at": now.isoformat(), "kind": kind, "data": data}
            self._cache = {
                k: v for k, v in self._cache.items()
                if now - datetime.fromisoformat(v["at"]) <= TTL.get(v.get("kind", ""), timedelta(0))
            }
            if self._cache_path:
                try:
                    self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                    self._cache_path.write_text(json.dumps(self._cache, separators=(",", ":")))
                except OSError:
                    pass
        return LiveAnswer(data, now, False)

    # ----- what the app offers ---------------------------------------------
    def train_live(self, number: str, start_date: date | None) -> LiveAnswer:
        def shape(d: dict[str, Any]) -> dict[str, Any]:
            cur = d.get("currentLocation") or {}
            halts = []
            for s in d.get("route") or []:
                if not s.get("isHalt", True):
                    continue
                halts.append({
                    "code": s.get("stationCode"), "name": s.get("stationName"),
                    "scheduled_arrival": _hhmm(s.get("scheduledArrival")),
                    "scheduled_departure": _hhmm(s.get("scheduledDeparture")),
                    "actual_arrival": _hhmm(s.get("actualArrival")),
                    "actual_departure": _hhmm(s.get("actualDeparture")),
                    "delay_minutes": _int(s.get("delayArrival") if s.get("delayArrival") is not None else s.get("delayDeparture")),
                    "platform": s.get("platform") or None,
                    "status": s.get("status"),
                })
            names = {h["code"]: h["name"] for h in halts}
            return {
                "train_number": d.get("trainNumber"),
                "train_name": d.get("trainName"),
                "start_date": d.get("startDate"),
                "status": d.get("status"),
                "is_live": bool(d.get("isLive")),
                "tracking_mode": d.get("trackingMode"),
                "delay_minutes": _int(d.get("delayMinutes")),
                "last_updated_at": d.get("lastUpdatedAt"),
                "current": {
                    "code": cur.get("stationCode"),
                    "name": cur.get("stationName") or names.get(cur.get("stationCode")),
                    "status": cur.get("status"),
                    "speed_kmh": _int(cur.get("speedKmh")),
                } if cur else None,
                "previous_halt": {"code": (p := d.get("previousHalt") or {}).get("stationCode"), "name": p.get("stationName")}
                if d.get("previousHalt") else None,
                "next_halt": {"code": (n := d.get("nextHalt") or {}).get("stationCode"), "name": n.get("stationName")}
                if d.get("nextHalt") else None,
                "alerts": [e.get("message") for e in d.get("exceptions") or [] if e.get("message")],
                "halts": halts,
            }

        return self._get(
            "train_live", f"/trains/{urllib.parse.quote(number)}/live",
            {"date": start_date.isoformat() if start_date else None, "haltsOnly": "true"}, shape,
        )

    def station_board(self, code: str, hours: int) -> LiveAnswer:
        def shape(d: dict[str, Any]) -> dict[str, Any]:
            st = d.get("station") or {}
            rows = []
            for t in d.get("trains") or []:
                train, stop, live = t.get("train") or {}, t.get("stop") or {}, t.get("live") or {}
                rows.append({
                    "number": train.get("number"), "name": train.get("name"), "type": train.get("type"),
                    "from": train.get("source"), "to": train.get("destination"),
                    "arrival": _hhmm(stop.get("arrival")), "departure": _hhmm(stop.get("departure")),
                    "platform": live.get("platform") or stop.get("platform") or None,
                    "state": live.get("type"),
                    "expected_arrival": _hhmm(live.get("expectedArrivalTime")),
                    "expected_departure": _hhmm(live.get("expectedDepartureTime")),
                    "delay_minutes": _int(live.get("delayMinutes")),
                })
            rows.sort(key=lambda r: r["expected_departure"] or r["expected_arrival"] or r["departure"] or r["arrival"] or "")
            return {"station": {"code": st.get("code"), "name": st.get("name")}, "window": d.get("window"), "trains": rows}

        return self._get("station_live", f"/stations/{urllib.parse.quote(code)}/live", {"hours": hours}, shape)

    def fare(self, number: str, from_code: str, to_code: str, day: date, cls: str, quota: str = "GN") -> LiveAnswer:
        def shape(d: dict[str, Any]) -> dict[str, Any]:
            b = d.get("breakdown") or {}
            parts = {
                "Base fare": b.get("baseFare"), "Reservation": b.get("reservationCharge"),
                "Superfast": b.get("superfastCharge"), "Catering": b.get("cateringCharge"),
                "Dynamic fare": b.get("dynamicFare"), "Tatkal": b.get("tatkalFare"),
                "GST": b.get("goodsServiceTax"), "Other": b.get("otherCharge"),
            }
            return {
                "total": _int(b.get("totalFare")),
                "distance_km": _int(d.get("distance")),
                "parts": {k: _int(v) for k, v in parts.items() if _int(v)},
                "class": cls, "quota": quota,
            }

        return self._get(
            "fare", f"/trains/{urllib.parse.quote(number)}/fare",
            {"source": from_code, "destination": to_code, "journeyDate": day.isoformat(), "classCode": cls, "quotaCode": quota},
            shape,
        )

    def coaches(self, number: str, station: str) -> LiveAnswer:
        def shape(d: dict[str, Any]) -> dict[str, Any]:
            st = d.get("station") or {}
            return {
                "station": {"code": st.get("code"), "name": st.get("name"), "platform": st.get("platform") or None},
                "reversal": bool(d.get("reversal")),
                "coaches": [
                    {"position": c.get("position"), "code": c.get("code"), "class": c.get("classType"), "name": c.get("className")}
                    for c in d.get("rake") or []
                ],
            }

        return self._get("coaches", f"/trains/{urllib.parse.quote(number)}/coaches/{urllib.parse.quote(station)}", {}, shape)

    def punctuality(self, number: str) -> LiveAnswer:
        def shape(d: dict[str, Any]) -> dict[str, Any]:
            s = d.get("summary") or {}
            worst = s.get("maxDelayStation") or {}
            return {
                "average_arrival_delay": _int(s.get("averageArrivalDelayMinutes")),
                "average_departure_delay": _int(s.get("averageDepartureDelayMinutes")),
                "on_time_percent": _int(s.get("punctualityPercentage")),
                "worst": {"code": worst.get("stationCode"), "name": worst.get("stationName"), "delay": _int(worst.get("delayMinutes"))}
                if worst else None,
                "halts": [
                    {"code": r.get("stationCode"), "name": r.get("stationName"),
                     "arrival_delay": _int(r.get("arrivalDelayMinutes")), "departure_delay": _int(r.get("departureDelayMinutes"))}
                    for r in d.get("route") or []
                ],
            }

        return self._get("delay", f"/trains/{urllib.parse.quote(number)}/delay", {}, shape)

    def alerts(self, number: str) -> tuple[list[dict[str, Any]], LiveAnswer]:
        """Today's cancellations, diversions and reschedules for one train (one shared list)."""

        def shape(d: dict[str, Any]) -> dict[str, Any]:
            items: dict[str, list[dict[str, Any]]] = {}
            for t in d.get("trains") or []:
                items.setdefault(str(t.get("trainNumber")), []).append({
                    "start_date": t.get("startDate"),
                    "type": (t.get("primaryType") or "").lower() or None,
                    "message": t.get("message") or "; ".join(e.get("message", "") for e in t.get("exceptions") or []),
                })
            return {"updated_at": (d.get("summary") or {}).get("updatedAt"), "by_train": items}

        answer = self._get("exceptions", "/trains/exceptions", {"type": "all"}, shape)
        return answer.data["by_train"].get(number, []), answer
