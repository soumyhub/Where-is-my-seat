"""Deterministic availability simulator for demo mode.

Scripted rules (``availability_rules.json``) make the demo scenarios reproducible; any
ticket without a rule gets a pseudo-random but deterministic status derived from a hash
of the query, nudged by festival rush and weekends. Every observation it returns is
flagged ``is_simulated=True`` and ``is_live=False``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Any

from ..festivals import RushCalendar
from ..timeutil import Clock
from .base import AvailabilityObservation, AvailabilityProvider, AvailabilityStatus, TicketQuery

SIMULATOR_SOURCE = "Where Is My Seat simulator — deterministic demo data, not live"


def _as_set(value: Any) -> frozenset[str] | None:
    if value in (None, "*"):
        return None
    if isinstance(value, str):
        return frozenset({value})
    return frozenset(value)


@dataclass(frozen=True, slots=True)
class _Rule:
    order: int
    train: str
    from_codes: frozenset[str] | None
    to_codes: frozenset[str] | None
    classes: frozenset[str] | None
    day_offsets: frozenset[int] | None
    status: AvailabilityStatus
    count: int | None
    note: str | None

    @classmethod
    def parse(cls, order: int, row: dict[str, Any]) -> _Rule:
        offsets = row.get("day_offsets")
        return cls(
            order=order,
            train=row["train"],
            from_codes=_as_set(row.get("from")),
            to_codes=_as_set(row.get("to")),
            classes=_as_set(row.get("class")),
            day_offsets=frozenset(offsets) if offsets is not None else None,
            status=AvailabilityStatus(row["status"]),
            count=row.get("count"),
            note=row.get("note"),
        )

    def matches(self, q: TicketQuery, offset: int) -> bool:
        return (
            self.train == q.train_number
            and (self.from_codes is None or q.from_code in self.from_codes)
            and (self.to_codes is None or q.to_code in self.to_codes)
            and (self.classes is None or q.travel_class in self.classes)
            and (self.day_offsets is None or offset in self.day_offsets)
        )

    @property
    def specificity(self) -> int:
        return sum(
            part is not None for part in (self.from_codes, self.to_codes, self.classes, self.day_offsets)
        )


class SimulatedAvailabilityProvider(AvailabilityProvider):
    name = "simulated"
    is_live = False
    is_simulated = True

    def __init__(self, rules_doc: dict[str, Any], anchor_date: date, rush: RushCalendar, clock: Clock):
        self._rules = [_Rule.parse(i, row) for i, row in enumerate(rules_doc.get("rules", []))]
        self._anchor = anchor_date
        self._rush = rush
        self._clock = clock

    def describe(self) -> dict[str, object]:
        return {
            **super().describe(),
            "source": SIMULATOR_SOURCE,
            "anchor_date": self._anchor.isoformat(),
            "scripted_rules": len(self._rules),
        }

    def check(self, query: TicketQuery) -> AvailabilityObservation:
        offset = (query.journey_date - self._anchor).days
        matches = [r for r in self._rules if r.matches(query, offset)]
        if matches:
            rule = max(matches, key=lambda r: (r.specificity, -r.order))
            status, count, note = rule.status, rule.count, rule.note
        else:
            status, count = self._generate(query)
            note = None
        status, count, note = self._fit_party(status, count, query.passengers, note)
        return AvailabilityObservation(
            status=status,
            count=count,
            source=SIMULATOR_SOURCE,
            observed_at=self._clock.now(),
            is_live=False,
            is_simulated=True,
            note=note,
        )

    def _generate(self, q: TicketQuery) -> tuple[AvailabilityStatus, int | None]:
        key = "|".join(
            [q.train_number, q.journey_date.isoformat(), q.from_code, q.to_code, q.travel_class, q.quota]
        )
        digest = hashlib.sha256(key.encode()).digest()
        u = int.from_bytes(digest[:8], "big") / 2**64
        v = int.from_bytes(digest[8:16], "big") / 2**64
        pressure = self._rush.factor(q.journey_date)
        if q.journey_date.weekday() >= 4:  # Fri-Sun
            pressure += 0.08
        days_ahead = (q.journey_date - self._clock.now().date()).days
        if days_ahead <= 3:
            pressure += 0.10
        if q.travel_class in ("SL", "3A"):
            pressure += 0.05
        score = u - pressure
        if score > 0.55:
            return AvailabilityStatus.CONFIRMED, 1 + int(v * 80)
        if score > 0.45:
            return AvailabilityStatus.RAC, 1 + int(v * 24)
        if score > 0.10:
            return AvailabilityStatus.WAITLISTED, 1 + int(v * 90)
        return AvailabilityStatus.UNAVAILABLE, None

    @staticmethod
    def _fit_party(
        status: AvailabilityStatus, count: int | None, passengers: int, note: str | None
    ) -> tuple[AvailabilityStatus, int | None, str | None]:
        if status is AvailabilityStatus.CONFIRMED and count is not None and count < passengers:
            return (
                AvailabilityStatus.WAITLISTED,
                passengers - count,
                f"Only {count} seat{'s' if count != 1 else ''} for {passengers} travellers",
            )
        return status, count, note
