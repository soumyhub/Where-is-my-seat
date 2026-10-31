"""Opt-in live seat availability through RailRadar, with the traveller's own API key.

RailRadar (https://railradar.in) is an independent third party, not IRCTC. Its sandbox key
allows about 100 requests a month at no cost, so this provider is built to never spend more
than a hard monthly limit and to reuse every answer it gets:

* one request returns several dates for the same train, stations, class and quota — all of
  them are cached;
* answers are reused for ``cache_minutes``;
* requests are counted over the last 30 days (RailRadar's cycle) and stored on disk, so
  restarts do not reset the count;
* it is never used by the journey search, only when a traveller asks to check one ticket.

Nothing here scrapes IRCTC, books tickets or handles payments.
"""

from __future__ import annotations

import json
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..timeutil import Clock
from .base import (
    AvailabilityObservation,
    AvailabilityProvider,
    AvailabilityStatus,
    ProviderError,
    ProviderNotConfigured,
    TicketQuery,
)

BASE_URL = "https://api.railradar.in/v1"
SOURCE = "RailRadar (third-party, not IRCTC)"
PLAN_MESSAGE = (
    "RailRadar's free plan doesn't include seat availability (it needs their paid Developer plan) — "
    "check seats on IRCTC instead."
)

# fetch(url, headers, timeout) -> parsed JSON
Fetch = Callable[[str, dict[str, str], float], Any]


class PlanNotIncluded(ProviderError):
    """The key works, but its RailRadar plan does not cover this endpoint."""


def _tls() -> ssl.SSLContext:
    # python.org builds of Python ship without CA certificates; certifi provides them.
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _http_fetch(url: str, headers: dict[str, str], timeout: float) -> Any:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_tls()) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            code = (json.loads(exc.read().decode("utf-8")).get("error") or {}).get("code")
        except (ValueError, AttributeError, OSError):
            code = None
        if code == "PLAN_UPGRADE_REQUIRED":
            raise PlanNotIncluded("RailRadar's free plan does not include seat availability") from exc
        if exc.code in (401, 403):
            raise ProviderError("RailRadar rejected the API key") from exc
        if exc.code == 429:
            raise ProviderError("RailRadar's request limit is used up for now") from exc
        raise ProviderError(f"RailRadar returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ProviderError("Could not reach RailRadar") from exc


class RollingQuota:
    """Requests counted over the last 30 days (RailRadar's quota runs on a 30-day cycle).

    Each request's time is kept in a small JSON file, so restarts never reset the count.
    """

    WINDOW = timedelta(days=30)

    def __init__(self, path: Path | None, limit: int) -> None:
        self.path = path
        self.limit = limit
        self._lock = threading.Lock()
        self._times: list[datetime] = []
        if path and path.exists():
            try:
                saved = json.loads(path.read_text())
                self._times = [datetime.fromisoformat(t) for t in saved.get("requests", [])]
            except (ValueError, OSError, TypeError):
                pass

    def used(self, now: datetime) -> int:
        return sum(1 for t in self._times if now - t < self.WINDOW)

    def remaining(self, now: datetime) -> int:
        return max(0, self.limit - self.used(now))

    def take(self, now: datetime) -> bool:
        """Count one request; False (and nothing counted) when the 30-day limit is reached."""
        with self._lock:
            self._times = [t for t in self._times if now - t < self.WINDOW]
            if len(self._times) >= self.limit:
                return False
            self._times.append(now)
            self._save()
            return True

    def refund(self, now: datetime) -> None:
        """Give back a request that failed (only successful requests count)."""
        with self._lock:
            if now in self._times:
                self._times.remove(now)
                self._save()

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"requests": [t.isoformat() for t in self._times]}))
        except OSError:
            pass


def parse_entry(entry: dict[str, Any]) -> tuple[AvailabilityStatus, int | None]:
    """Map one RailRadar calendar entry to a status and a count (seats, RAC or WL number)."""
    code = str(entry.get("statusCode") or "").upper()
    raw = str(entry.get("status") or "").upper()
    if entry.get("isAvailable") is True or code in ("AVAILABLE", "AVL", "CURR_AVBL"):
        return AvailabilityStatus.CONFIRMED, _int(entry.get("availableSeats"))
    if any(word in raw or word in code for word in ("REGRET", "NOT AVAILABLE", "CANCEL", "CLOSED", "DEPARTED")):
        return AvailabilityStatus.UNAVAILABLE, None
    if code == "RAC" or raw.startswith("RAC"):
        return AvailabilityStatus.RAC, _int(entry.get("waitlistNumber"))
    if code in ("WAITLIST", "WL") or "WL" in raw:
        return AvailabilityStatus.WAITLISTED, _int(entry.get("waitlistNumber"))
    return AvailabilityStatus.UNKNOWN, None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class RailRadarProvider(AvailabilityProvider):
    name = "railradar"
    is_live = True
    is_simulated = False
    # Too few free requests to run inside the journey search: checks are made one ticket at a time.
    quota_limited = True

    def __init__(
        self,
        api_key: str | None,
        clock: Clock,
        monthly_limit: int = 90,
        cache_minutes: int = 30,
        state_path: Path | None = None,
        fetch: Fetch | None = None,
        base_url: str = BASE_URL,
        timeout: float = 6.0,
        quota: RollingQuota | None = None,
    ) -> None:
        if not api_key:
            raise ProviderNotConfigured("RailRadar needs WIMS_RAILRADAR_KEY (your own key from railradar.in)")
        self._key = api_key
        self._clock = clock
        self._fetch = fetch or _http_fetch
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._ttl = timedelta(minutes=cache_minutes)
        self._cache: dict[tuple[str, str, str, str, str, date], AvailabilityObservation] = {}
        self._lock = threading.Lock()
        self.quota = quota or RollingQuota(state_path, monthly_limit)  # shared with live tools
        self._plan_path = state_path.with_name("railradar_plan.json") if state_path else None
        self._blocked_at: datetime | None = None  # last time RailRadar said the plan lacks seats
        if self._plan_path and self._plan_path.exists():
            try:
                self._blocked_at = datetime.fromisoformat(json.loads(self._plan_path.read_text())["seats_blocked_at"])
            except (ValueError, KeyError, OSError, TypeError):
                pass

    PLAN_RECHECK = timedelta(hours=24)

    @property
    def seats_blocked(self) -> bool:
        """True while RailRadar recently said this key's plan has no seat availability."""
        return self._blocked_at is not None and self._clock.now() - self._blocked_at < self.PLAN_RECHECK

    @property
    def is_live(self) -> bool:  # type: ignore[override]
        return not self.seats_blocked

    def _set_blocked(self, when: datetime | None) -> None:
        self._blocked_at = when
        if self._plan_path:
            try:
                if when is None:
                    self._plan_path.unlink(missing_ok=True)
                else:
                    self._plan_path.parent.mkdir(parents=True, exist_ok=True)
                    self._plan_path.write_text(json.dumps({"seats_blocked_at": when.isoformat()}))
            except OSError:
                pass

    def describe(self) -> dict[str, object]:
        now = self._clock.now()
        return {
            **super().describe(),
            "source": SOURCE,
            "monthly_limit": self.quota.limit,
            "used_this_month": self.quota.used(now),
            "remaining_this_month": self.quota.remaining(now),
            "blocked_reason": PLAN_MESSAGE if self.seats_blocked else None,
        }

    def check(self, query: TicketQuery) -> AvailabilityObservation:
        key = (query.train_number, query.from_code, query.to_code, query.travel_class, query.quota, query.journey_date)
        now = self._clock.now()
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None and now - cached.observed_at <= self._ttl:
            return cached
        if self.seats_blocked:
            return self._unknown(PLAN_MESSAGE)
        if not self.quota.take(now):
            return self._unknown(
                f"The {self.quota.limit} free live checks for the last 30 days are used up — check on IRCTC instead."
            )
        params = urllib.parse.urlencode(
            {
                "source": query.from_code,
                "destination": query.to_code,
                "journeyDate": query.journey_date.isoformat(),
                "classCode": query.travel_class,
                "quotaCode": query.quota,
            }
        )
        try:
            body = self._fetch(
                f"{self._base_url}/trains/{urllib.parse.quote(query.train_number)}/seats?{params}",
                {"Authorization": f"Bearer {self._key}", "Accept": "application/json"},
                self._timeout,
            )
        except PlanNotIncluded:
            self.quota.refund(now)  # RailRadar only counts successful requests
            self._set_blocked(now)
            return self._unknown(PLAN_MESSAGE)
        except ProviderError:
            self.quota.refund(now)
            raise
        if self._blocked_at is not None:
            self._set_blocked(None)  # the plan covers seats again
        if not isinstance(body, dict) or not body.get("success") or not isinstance(body.get("data"), dict):
            raise ProviderError("RailRadar returned an unexpected response")
        found: AvailabilityObservation | None = None
        with self._lock:
            for entry in body["data"].get("calendar") or []:
                try:
                    day = date.fromisoformat(str(entry.get("rawDate") or entry.get("date"))[:10])
                except ValueError:
                    continue
                status, count = parse_entry(entry)
                raw = entry.get("status") or entry.get("statusCode") or "?"
                obs = AvailabilityObservation(
                    status=status,
                    count=count,
                    source=SOURCE,
                    observed_at=now,
                    is_live=status is not AvailabilityStatus.UNKNOWN,
                    is_simulated=False,
                    note=(
                        f"RailRadar shows “{raw}” — their availability feed or forecast, not IRCTC itself. "
                        "Confirm on IRCTC before you pay."
                    ),
                )
                self._cache[(*key[:5], day)] = obs
                if day == query.journey_date:
                    found = obs
        return found or self._unknown("RailRadar had no status for this date — check on IRCTC.")

    def _unknown(self, note: str) -> AvailabilityObservation:
        return AvailabilityObservation(
            status=AvailabilityStatus.UNKNOWN,
            count=None,
            source=SOURCE,
            observed_at=self._clock.now(),
            is_live=False,
            is_simulated=False,
            note=note,
        )
