"""Non-simulated providers: 'not configured' and the authorized live-provider stub."""

from __future__ import annotations

from ..timeutil import Clock
from .base import (
    AvailabilityObservation,
    AvailabilityProvider,
    AvailabilityStatus,
    ProviderError,
    ProviderNotConfigured,
    TicketQuery,
)


class NotConfiguredProvider(AvailabilityProvider):
    """Used when no availability source is configured: everything is UNKNOWN."""

    name = "none"
    is_live = False
    is_simulated = False

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def check(self, query: TicketQuery) -> AvailabilityObservation:
        return AvailabilityObservation(
            status=AvailabilityStatus.UNKNOWN,
            count=None,
            source="No availability provider configured",
            observed_at=self._clock.now(),
            is_live=False,
            is_simulated=False,
            note="Seat availability was not checked. A timetable never implies a seat.",
        )


class AuthorizedLiveProvider(AvailabilityProvider):
    """Integration point for a licensed / authorized availability API.

    This build ships no live integration. It must never scrape IRCTC, bypass CAPTCHAs
    or automate bookings. Implement ``_fetch`` against a contract you are allowed to
    use, map the response into an ``AvailabilityObservation`` with ``is_live=True``,
    and keep the source and observation timestamp.
    """

    name = "live"
    is_live = True
    is_simulated = False

    def __init__(self, base_url: str | None, api_key: str | None, clock: Clock, timeout: float = 4.0):
        if not base_url or not api_key:
            raise ProviderNotConfigured(
                "Live availability needs WIMS_LIVE_PROVIDER_URL and WIMS_LIVE_PROVIDER_KEY"
            )
        self._base_url = base_url
        self._api_key = api_key
        self._clock = clock
        self._timeout = timeout

    def check(self, query: TicketQuery) -> AvailabilityObservation:
        return self._fetch(query)

    def _fetch(self, query: TicketQuery) -> AvailabilityObservation:
        raise ProviderError("Live availability integration is not implemented in this build")
