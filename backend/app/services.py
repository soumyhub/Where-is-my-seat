"""Wiring: build the data layer, providers and search engine from settings."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .config import Settings
from .core.availability import (
    AuthorizedLiveProvider,
    AvailabilityProvider,
    AvailabilityService,
    NotConfiguredProvider,
    ProviderNotConfigured,
    RailRadarProvider,
    SimulatedAvailabilityProvider,
)
from .core.data_loader import load_dataset
from .core.fares import FARE_BASIS, FareEstimator
from .core.festivals import RushCalendar
from .core.availability.railradar import RollingQuota
from .core.live import RailRadarLive
from .core.railmap import RailMap
from .core.road import RoadEstimator
from .core.search import JourneySearchEngine, SearchLimits, SearchOptions
from .core.stations import StationDirectory
from .core.timetable import Timetable
from .core.timeutil import Clock, SystemClock

log = logging.getLogger("wims")

SIMULATED_LABEL = "SIMULATED DATA — NOT LIVE RAILWAY AVAILABILITY"


@dataclass(frozen=True)
class DataNotice:
    mode: str  # "demo" | "timetable" (real trains, seats not live) | "live"
    label: str
    details: list[str]
    timetable_source: str
    timetable_version: str
    timetable_updated: str
    timetable_simulated: bool
    availability_source: str
    availability_live: bool
    availability_simulated: bool
    fare_basis: str
    coverage: str
    provider_note: str | None = None
    live_checks: bool = False  # single tickets can be checked live (see /availability/usage)
    live_checks_source: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Services:
    def __init__(
        self,
        settings: Settings,
        clock: Clock | None = None,
        options: SearchOptions | None = None,
        limits: SearchLimits | None = None,
    ) -> None:
        self.settings = settings
        self.clock = clock or SystemClock()
        dataset = load_dataset(settings.data_dir, settings.timetable)
        self.dataset = dataset
        self.directory = StationDirectory(dataset.stations, dataset.cities)
        self.timetable = Timetable(dataset.trains, dataset.timetable_meta)
        self.road = RoadEstimator(self.directory, dataset.road_overrides)
        self.fares = FareEstimator()
        # Track shapes for maps (OpenStreetMap, ODbL); optional — maps fall back to straight lines.
        self.railmap = RailMap.load(settings.data_dir / "osm" / "rail_graph.json")
        self.rush = RushCalendar(dataset.festivals)
        self.demo_date: date = settings.demo_date or (self.clock.now().date() + timedelta(days=7))
        state = settings.state_dir
        # One request budget for everything that calls RailRadar (seat checks and live tools).
        self.railradar_quota = RollingQuota(
            state / "railradar_usage.json" if state else None, settings.live_monthly_limit
        )
        self.live = (
            RailRadarLive(
                settings.railradar_key, self.clock, self.railradar_quota,
                cache_path=state / "railradar_cache.json" if state else None, base_url=settings.railradar_url,
            )
            if settings.railradar_key
            else None
        )
        self.check_provider, self.provider_note = self._build_provider()
        # A provider with a small request quota answers single-ticket checks only; the journey
        # search (hundreds of tickets) then runs without seat data.
        self.provider = (
            NotConfiguredProvider(self.clock) if getattr(self.check_provider, "quota_limited", False)
            else self.check_provider
        )
        self.availability = AvailabilityService(self.provider, self.clock, settings.stale_after_minutes)
        self.check_availability = (
            self.availability if self.check_provider is self.provider
            else AvailabilityService(self.check_provider, self.clock, settings.stale_after_minutes)
        )
        self.engine = JourneySearchEngine(
            directory=self.directory,
            timetable=self.timetable,
            road=self.road,
            fares=self.fares,
            availability=self.availability,
            rush=self.rush,
            clock=self.clock,
            options=options,
            limits=limits,
            max_advance_days=settings.max_advance_days,
        )
        self.notice = self._notice()

    @property
    def simulated_timetable(self) -> bool:
        meta = self.dataset.timetable_meta
        return bool(meta.get("simulated")) or all(t.simulated for t in self.timetable.trains())

    def _build_provider(self) -> tuple[AvailabilityProvider, str | None]:
        choice = self.settings.availability_provider
        if choice == "auto":
            # Simulated seats only ever go with the simulated demo timetable.
            choice = "simulated" if self.simulated_timetable else "none"
        if choice == "simulated":
            return (
                SimulatedAvailabilityProvider(
                    self.dataset.availability_rules, self.demo_date, self.rush, self.clock
                ),
                None,
            )
        if choice == "railradar":
            try:
                state = self.settings.state_dir
                return (
                    RailRadarProvider(
                        self.settings.railradar_key,
                        self.clock,
                        monthly_limit=self.settings.live_monthly_limit,
                        cache_minutes=self.settings.live_cache_minutes,
                        state_path=state / "railradar_usage.json" if state else None,
                        base_url=self.settings.railradar_url,
                        quota=self.railradar_quota,
                    ),
                    None,
                )
            except ProviderNotConfigured as exc:
                log.warning("RailRadar not configured (%s); seat status will be UNKNOWN", exc)
                return NotConfiguredProvider(self.clock), str(exc)
        if choice == "live":
            try:
                return (
                    AuthorizedLiveProvider(
                        self.settings.live_provider_url, self.settings.live_provider_key, self.clock
                    ),
                    None,
                )
            except ProviderNotConfigured as exc:
                log.warning("Live availability not configured (%s); seat status will be UNKNOWN", exc)
                return NotConfiguredProvider(self.clock), str(exc)
        return NotConfiguredProvider(self.clock), "Seat availability is not connected to a live source"

    def _notice(self) -> DataNotice:
        meta = self.dataset.timetable_meta
        simulated_tt = self.simulated_timetable
        provider = self.provider
        details = []
        if simulated_tt:
            mode, label = "demo", SIMULATED_LABEL
            details.append(
                "Trains (numbers start with SIM-), timetables and fares are invented for this demo. "
                "Station names and codes are real."
            )
        elif provider.is_simulated:
            mode, label = "demo", "SIMULATED SEAT AVAILABILITY — NOT LIVE"
            details.append("Real trains, but seat status comes from a simulator — never book from it.")
        elif provider.is_live:
            mode, label = "live", "Live seat availability from an authorized provider"
        else:
            mode, label = "timetable", "SEAT AVAILABILITY IS NOT LIVE — CHECK ON IRCTC BEFORE YOU BOOK"
            details.append(
                "Trains and timings come from Indian Railways' official Trains at a Glance 2026 "
                "(main halts). Retimings after publication are not included."
            )
            if self.check_provider.is_live:
                details.append(
                    "Live seats: tap Check live seats on a ticket. Answers come from RailRadar, a third party "
                    f"(not IRCTC), with a limit of {self.settings.live_monthly_limit} checks per 30 days."
                )
            else:
                details.append("Seat availability is not checked here: use the IRCTC links to see live seats.")
        if provider.is_simulated and not simulated_tt:
            details.append("Seat availability is simulated by a deterministic generator — not live inventory.")
        details.append("Fares are estimates from a simplified distance model, not official IRCTC fares.")
        details.append("Road / metro legs are rough estimates. Nothing here can be booked through this app.")
        return DataNotice(
            mode=mode,
            label=label,
            details=details,
            timetable_source=meta.get("source", "unknown"),
            timetable_version=meta.get("version", "unknown"),
            timetable_updated=meta.get("last_updated", "unknown"),
            timetable_simulated=simulated_tt,
            availability_source=getattr(provider, "name", "provider"),
            availability_live=provider.is_live,
            availability_simulated=provider.is_simulated,
            fare_basis=FARE_BASIS,
            coverage=self.dataset.station_meta.get(
                "coverage", f"{len(self.directory.all())} stations"
            ),
            provider_note=self.provider_note,
            live_checks=self.check_provider.is_live,
            live_checks_source=getattr(self.check_provider, "describe")().get("source") if self.check_provider.is_live else None,
        )

    def live_usage(self) -> dict[str, Any]:
        info = self.check_provider.describe()
        now = self.clock.now()
        return {
            "available": self.check_provider.is_live,
            "tools": self.live is not None,
            "requests_used": self.railradar_quota.used(now) if self.live else None,
            "requests_left": self.railradar_quota.remaining(now) if self.live else None,
            "source": info.get("source") or info.get("name"),
            "monthly_limit": info.get("monthly_limit"),
            "used_this_month": info.get("used_this_month"),
            "remaining_this_month": info.get("remaining_this_month"),
            "blocked_reason": info.get("blocked_reason"),
        }

    def refresh_notice(self) -> bool:
        """Rebuild the data notice if live checks were switched off or on; True when it changed."""
        if self.notice.live_checks == self.check_provider.is_live:
            return False
        self.notice = self._notice()
        return True

    def samples(self) -> list[dict[str, Any]]:
        day = self.demo_date.isoformat()
        if self.simulated_timetable:
            return self._demo_samples(day)
        routes = [
            ("delhi-jaipur", "Delhi", "Jaipur", "city:delhi", "city:jaipur", "3A",
             "Shatabdi, Double Decker and overnight expresses, plus backup tickets if they are full."),
            ("mumbai-delhi", "Mumbai", "Delhi", "city:mumbai", "city:delhi", "3A",
             "Rajdhani, Duronto and Superfast options across Mumbai and Delhi stations."),
            ("bengaluru-chennai", "Bengaluru", "Chennai", "city:bengaluru", "city:chennai", "CC",
             "Short day trip: Shatabdi, Vande Bharat and intercity trains."),
            ("kolkata-patna", "Kolkata", "Patna", "city:kolkata", "city:patna", "SL",
             "Busy festival route: overnight trains and changes at major junctions."),
        ]
        return [
            {
                "id": rid,
                "title": f"{a} → {b}",
                "description": text,
                "shows": [],
                "from_name": a,
                "to_name": b,
                "request": {
                    "origin": o,
                    "destination": t,
                    "date": day,
                    "passengers": 1,
                    "travel_class": cls,
                    "max_transfers": 2,
                    "flexible_days": 0,
                },
            }
            for rid, a, b, o, t, cls, text in routes
            if self._resolvable(o) and self._resolvable(t)
        ]

    def _resolvable(self, key: str) -> bool:
        try:
            self.directory.resolve(key)
            return True
        except LookupError:
            return False

    def _demo_samples(self, day: str) -> list[dict[str, Any]]:
        return [
            {
                "id": "delhi-jaipur-diwali",
                "title": "Diwali rush: Delhi → Jaipur",
                "description": (
                    "Every direct train is waitlisted. Board at Rewari, change at Bandikui, "
                    "split one train into two tickets, or book to Ajmer and get off early."
                ),
                "shows": ["Different boarding station", "Connecting trains", "Smart tickets"],
                "from_name": "Delhi",
                "to_name": "Jaipur",
                "request": {"origin": "city:delhi", "destination": "city:jaipur", "date": day, "passengers": 1,
                            "travel_class": "3A", "max_transfers": 2, "flexible_days": 0},
            },
            {
                "id": "delhi-ajmer-sleeper",
                "title": "New Delhi → Ajmer in Sleeper",
                "description": "Direct is waitlisted: get off one stop early at Kishangarh, or change at Jaipur.",
                "shows": ["Nearby destination", "Connecting trains"],
                "from_name": "New Delhi",
                "to_name": "Ajmer Jn",
                "request": {"origin": "NDLS", "destination": "AII", "date": day, "passengers": 1,
                            "travel_class": "SL", "max_transfers": 2, "flexible_days": 0},
            },
            {
                "id": "nizamuddin-kota-overnight",
                "title": "Overnight: Nizamuddin → Kota",
                "description": "The night train is waitlisted end to end, but two shorter tickets are not — plus flexible dates.",
                "shows": ["Smart tickets", "Overnight", "Another date"],
                "from_name": "Hazrat Nizamuddin",
                "to_name": "Kota Jn",
                "request": {"origin": "NZM", "destination": "KOTA", "date": day, "passengers": 1,
                            "travel_class": "3A", "max_transfers": 2, "flexible_days": 1},
            },
        ]
