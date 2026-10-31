"""Scenario 8: missing or simulated availability is never presented as live confirmation."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.availability import (
    AvailabilityObservation,
    AvailabilityProvider,
    AvailabilityService,
    AvailabilityStatus,
    NotConfiguredProvider,
    ProviderError,
    TicketQuery,
)
from app.core.availability.providers import AuthorizedLiveProvider
from app.core.search.ranking import ticket_weight
from app.core.timeutil import FixedClock

from .conftest import NOW, TRAVEL_DATE, build_engine, params


class ExplodingProvider(AvailabilityProvider):
    name = "exploding"
    is_live = True

    def check(self, query: TicketQuery) -> AvailabilityObservation:
        raise ProviderError("upstream timeout")


def test_simulated_availability_is_always_labelled_simulated(engine):
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A", flexible_days=1))
    tickets = [t for it in result.itineraries for t in it.reserved_tickets]
    assert tickets
    for t in tickets:
        obs = t.availability
        assert obs is not None
        assert obs.is_live is False
        assert obs.is_simulated is True
        assert "simulated" in obs.display
        assert "not live" in obs.source


def test_no_provider_means_unknown_never_confirmed():
    engine = build_engine(provider=NotConfiguredProvider(FixedClock(NOW)))
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A"))
    assert result.itineraries
    for it in result.itineraries:
        assert it.overall_status != "CONFIRMED"
        for t in it.reserved_tickets:
            assert t.status is AvailabilityStatus.UNKNOWN
            assert t.availability.is_live is False
            assert t.availability.display.startswith("Unknown")
    assert result.summary["direct_confirmed"] == 0


def test_provider_errors_degrade_to_unknown():
    engine = build_engine(provider=ExplodingProvider())
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A"))
    assert result.itineraries
    assert result.stats["availability_errors"] > 0
    for it in result.itineraries:
        assert it.overall_status != "CONFIRMED"
        for t in it.reserved_tickets:
            assert t.status is AvailabilityStatus.UNKNOWN
            assert t.availability.is_live is False
            assert "error" in (t.availability.note or "")


def test_live_provider_requires_configuration():
    with pytest.raises(ProviderError):
        AuthorizedLiveProvider(None, None, FixedClock(NOW))


def test_timetable_alone_never_implies_a_seat():
    # Same timetable, no availability source: a train that clearly runs is still UNKNOWN.
    engine = build_engine(provider=NotConfiguredProvider(FixedClock(NOW)))
    result = engine.search(params(engine, "ORG", "DST", travel_class="3A"))
    direct = next(it for it in result.itineraries if [r.train.number for r in it.rides] == ["T100"])
    assert direct.overall_status == "UNKNOWN"
    assert ticket_weight(direct.reserved_tickets[0]) < 1.0  # ranked below a real confirmation


def test_stale_observations_are_flagged():
    clock = FixedClock(NOW)
    service = AvailabilityService(NotConfiguredProvider(clock), clock, stale_after_minutes=60)
    fresh = NOW - timedelta(minutes=30)
    old = NOW - timedelta(hours=7)
    assert service.is_stale(fresh) is False
    assert service.is_stale(old) is True


def test_party_size_larger_than_seats_is_not_confirmed():
    engine = build_engine()
    result = engine.search(params(engine, "NBR", "DST", travel_class="3A", passengers=6, include_nearby=False))
    t500 = next(it for it in result.itineraries if [r.train.number for r in it.rides] == ["T500"])
    # T500 shows 5 seats; six travellers cannot all be confirmed.
    assert t500.overall_status == "WAITLISTED"
    assert "Only 5 seats" in (t500.reserved_tickets[0].availability.note or "")


def test_availability_session_caches_and_caps_calls():
    clock = FixedClock(NOW)
    calls = []

    class Counting(AvailabilityProvider):
        name = "counting"

        def check(self, query):
            calls.append(query)
            return AvailabilityObservation(AvailabilityStatus.RAC, 1, "test", clock.now(), False, True)

    session = AvailabilityService(Counting(), clock).session(max_checks=2)
    q = lambda to: TicketQuery("T1", TRAVEL_DATE, "A", to, "3A")
    assert session.check(q("B")).status is AvailabilityStatus.RAC
    assert session.check(q("B")).status is AvailabilityStatus.RAC  # cached
    session.check(q("C"))
    capped = session.check(q("D"))
    assert len(calls) == 2
    assert capped.status is AvailabilityStatus.UNKNOWN and "limit" in capped.note
