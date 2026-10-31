"""Caching, error-isolating facade the search engine talks to."""

from __future__ import annotations

from datetime import datetime, timedelta

from ..timeutil import Clock
from .base import AvailabilityObservation, AvailabilityProvider, AvailabilityStatus, ProviderError, TicketQuery


class AvailabilitySession:
    """Per-request cache with a call budget. Never raises; failures become UNKNOWN."""

    def __init__(self, provider: AvailabilityProvider, clock: Clock, max_checks: int) -> None:
        self._provider = provider
        self._clock = clock
        self._max_checks = max_checks
        self._cache: dict[TicketQuery, AvailabilityObservation] = {}
        self.calls = 0
        self.errors = 0
        self.skipped = 0

    def check(self, query: TicketQuery) -> AvailabilityObservation:
        cached = self._cache.get(query)
        if cached is not None:
            return cached
        if self.calls >= self._max_checks:
            self.skipped += 1
            return self._unknown("Not checked: availability check limit for this search reached")
        self.calls += 1
        try:
            observation = self._provider.check(query)
            if not isinstance(observation, AvailabilityObservation):
                raise TypeError("provider returned an invalid observation")
        except ProviderError as exc:
            self.errors += 1
            observation = self._unknown(f"Availability provider error ({exc}) — status unknown, check on IRCTC")
        except Exception:  # provider failures must never look like seats
            self.errors += 1
            observation = self._unknown("Availability provider error — status unknown")
        self._cache[query] = observation
        return observation

    def _unknown(self, note: str) -> AvailabilityObservation:
        return AvailabilityObservation(
            status=AvailabilityStatus.UNKNOWN,
            count=None,
            source=getattr(self._provider, "name", "provider"),
            observed_at=self._clock.now(),
            is_live=False,
            is_simulated=bool(getattr(self._provider, "is_simulated", False)),
            note=note,
        )


class AvailabilityService:
    def __init__(self, provider: AvailabilityProvider, clock: Clock, stale_after_minutes: int = 360):
        self.provider = provider
        self.clock = clock
        self.stale_after = timedelta(minutes=stale_after_minutes)

    def session(self, max_checks: int = 800) -> AvailabilitySession:
        return AvailabilitySession(self.provider, self.clock, max_checks)

    def is_stale(self, observed_at: datetime, now: datetime | None = None) -> bool:
        return (now or self.clock.now()) - observed_at > self.stale_after
