"""Translate engine objects into API response dicts (validated by the schemas)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..core.availability import AvailabilityObservation, AvailabilityService
from ..core.fares import FARE_BASIS, FareEstimator
from ..core.models import CLASS_LABELS
from ..core.search import Itinerary, RideLeg, RoadLeg, SearchResult, Ticket
from ..core.stations import Place, StationDirectory
from ..core.timeutil import format_clock, format_duration, minutes_between, to_iso
from ..services import DataNotice

IRCTC_URL = "https://www.irctc.co.in/nget/train-search"
UTS_URL = "https://www.utsonmobile.indianrail.gov.in/"


class Serializer:
    def __init__(
        self,
        directory: StationDirectory,
        availability: AvailabilityService,
        notice: DataNotice,
        fares: FareEstimator | None = None,
    ):
        self.directory = directory
        self.availability = availability
        self.notice = notice
        self.fares = fares or FareEstimator()

    # ----- small pieces -------------------------------------------------
    def station(self, code: str) -> dict[str, str]:
        s = self.directory.get(code)
        return {"code": code, "name": s.name if s else code, "city": s.city if s else ""}

    def place(self, place: Place) -> dict[str, Any]:
        if place.kind == "city":
            listed = ", ".join(place.codes[:5]) + ("…" if len(place.codes) > 5 else "")
            subtitle = f"All {len(place.codes)} stations · {listed}"
            code = None
        else:
            s = self.directory.get(place.anchor)
            city = self.directory.city(s.city) if s else None
            city_name = city.name if city else ""
            state = s.state if s and s.state and s.state != city_name else ""
            subtitle = f"{place.anchor} · {city_name}{', ' + state if state else ''}"
            if s and not s.served:
                subtitle = f"{place.anchor}{' · ' + s.state if s.state else ''} · no trains here — we use the nearest station"
            code = place.anchor
        return {
            "kind": place.kind,
            "key": place.key,
            "code": code,
            "name": f"{place.name} (all stations)" if place.kind == "city" else place.name,
            "subtitle": subtitle,
            "city": place.city,
            "codes": list(place.codes),
            "served": place.kind == "city" or bool((st := self.directory.get(place.anchor)) and st.served),
        }

    def observation(self, obs: AvailabilityObservation) -> dict[str, Any]:
        return {
            "status": obs.status.value,
            "count": obs.count,
            "label": obs.label,
            "display": obs.display,
            "source": obs.source,
            "observed_at": to_iso(obs.observed_at),
            "is_live": obs.is_live,
            "is_simulated": obs.is_simulated,
            "stale": self.availability.is_stale(obs.observed_at),
            "note": obs.note,
        }

    def booking(self, ticket: Ticket) -> dict[str, Any]:
        simulated = ticket.run.train.simulated
        unreserved = ticket.kind == "unreserved"
        if simulated:
            return {
                "channel": "Not bookable — simulated demo train",
                "url": UTS_URL if unreserved else IRCTC_URL,
                "bookable": False,
                "note": "This train exists only in the demo. Search real trains on the official site.",
            }
        if unreserved:
            return {
                "channel": "UTS app (official)",
                "url": UTS_URL,
                "bookable": True,
                "note": "Unreserved tickets: UTS app or the station counter.",
            }
        return {
            "channel": "IRCTC (official)",
            "url": IRCTC_URL,
            "bookable": True,
            "note": "Book on the official IRCTC site or app. This app never books or takes payment.",
        }

    def ticket(self, ticket: Ticket, passengers: int) -> dict[str, Any]:
        return {
            "kind": ticket.kind,
            "train_number": ticket.run.train.number,
            "from_station": self.station(ticket.from_code),
            "to_station": self.station(ticket.to_code),
            "journey_date": ticket.journey_date.isoformat(),
            "travel_class": ticket.travel_class,
            "class_label": CLASS_LABELS.get(ticket.travel_class, ticket.travel_class),
            "quota": ticket.quota,
            "strategy": ticket.strategy,
            "class_mismatch": ticket.class_mismatch,
            "distance_km": ticket.km,
            "availability": self.observation(ticket.availability) if ticket.availability else None,
            "fare": {
                "per_person": ticket.fare_per_person,
                "total": ticket.fare_per_person * passengers,
                "is_estimate": True,
                "basis": FARE_BASIS,
            },
            "booking": self.booking(ticket),
        }

    # ----- legs ---------------------------------------------------------
    def _instructions(self, leg: RideLeg | RoadLeg, tickets: list[Ticket]) -> list[str]:
        d = self.directory
        if isinstance(leg, RoadLeg):
            mode = leg.estimate.mode.lower()
            if leg.purpose == "feeder":
                return [
                    f"Make your own way to {d.name(leg.to_code)} by {mode} (about {format_duration(leg.minutes)}, estimate).",
                    f"Aim to reach by {format_clock(leg.arr)} — this is not a train and is not booked here.",
                ]
            if leg.purpose == "transfer":
                return [f"Change stations: {d.name(leg.from_code)} → {d.name(leg.to_code)} by {mode} (estimate)."]
            return [f"Continue to {d.name(leg.to_code)} by {mode} — about {format_duration(leg.minutes)} (estimate)."]
        lines = [f"Board {leg.train.number} {leg.train.name} at {d.name(leg.from_code)} ({format_clock(leg.dep)})."]
        if tickets and tickets[0].kind == "unreserved":
            lines.append("Unreserved ticket: General (UR) coaches only — never a reserved coach or berth.")
        else:
            lines.append("Reserved ticket: sit only in the coach and berth printed on your ticket.")
        if len(tickets) == 2:
            lines.append(f"At {d.name(tickets[0].to_code)}, switch to the seat on your second ticket.")
        lines.append(f"Get off at {d.name(leg.to_code)} ({format_clock(leg.arr)}).")
        return lines

    def leg(self, pl, passengers: int) -> dict[str, Any]:
        leg = pl.leg
        base = {
            "from_station": self.station(leg.from_code),
            "to_station": self.station(leg.to_code),
            "depart_at": to_iso(leg.dep),
            "arrive_at": to_iso(leg.arr),
            "duration_minutes": minutes_between(leg.dep, leg.arr),
            "day_change": (leg.arr.date() - leg.dep.date()).days,
            "distance_km": leg.km,
            "buffer_before_minutes": pl.buffer_before,
            "instructions": self._instructions(leg, pl.tickets),
            "cost_per_person": pl.cost_per_person,
        }
        if isinstance(leg, RoadLeg):
            return {
                **base,
                "kind": "road",
                "purpose": leg.purpose,
                "train": None,
                "road": {
                    "mode": leg.estimate.mode,
                    "km": leg.km,
                    "cost_per_person": leg.estimate.cost_per_person,
                    "basis": leg.estimate.basis,
                },
                "tickets": [],
                "stops": [],
                "class_fares": {},
            }
        train = leg.train
        stops = []
        for stop in train.stops[leg.board : leg.alight + 1]:
            stops.append(
                {
                    "code": stop.station,
                    "name": self.directory.name(stop.station),
                    "arr": to_iso(leg.run.at(stop.arr)) if stop.arr is not None else None,
                    "dep": to_iso(leg.run.at(stop.dep)) if stop.dep is not None else None,
                    "km": stop.km - train.stops[leg.board].km,
                    "day": stop.day,
                    "role": "board" if stop.index == leg.board else "alight" if stop.index == leg.alight else "halt",
                }
            )
        return {
            **base,
            "kind": "train",
            "purpose": "ride",
            "train": {
                "number": train.number,
                "name": train.name,
                "category": train.category,
                "runs_on": train.runs_on_label(),
                "classes": list(train.classes),
                "unreserved": train.unreserved,
                "superfast": train.superfast,
                "simulated": train.simulated,
                "source": train.source,
                "notes": list(train.notes),
                "start_date": leg.run.start_date.isoformat(),  # the day it leaves its first station
            },
            "road": None,
            "tickets": [self.ticket(t, passengers) for t in pl.tickets],
            "stops": stops,
            "class_fares": {
                cls: self.fares.estimate(train, cls, leg.km) for cls in (train.classes or ("UR",))
            },
        }

    # ----- itineraries --------------------------------------------------
    def itinerary(self, it: Itinerary) -> dict[str, Any]:
        return {
            "id": it.id,
            "categories": it.categories,
            "primary_category": it.primary_category,
            "headline": it.headline,
            "legs": [self.leg(pl, it.passengers) for pl in it.legs],
            "depart_at": to_iso(it.depart_at),
            "arrive_at": to_iso(it.arrive_at),
            "total_minutes": it.total_minutes,
            "travel_date": it.travel_date.isoformat(),
            "date_offset": it.date_offset,
            "passengers": it.passengers,
            "cost_per_person": it.cost_per_person,
            "cost_total": it.cost_total,
            "transfers": it.transfers,
            "train_changes": it.train_changes,
            "tickets_count": len(it.tickets),
            "reserved_tickets_count": len(it.reserved_tickets),
            "separate_tickets": it.separate_tickets,
            "single_train": len(it.rides) == 1 and not it.has_road,
            "overall_status": it.overall_status,
            "availability_score": round(it.availability_score, 3),
            "convenience_score": it.convenience_score,
            "score": it.score,
            "connection_quality": it.connection_quality,
            "why": it.why,
            "fits": it.fits,
            "warnings": it.warnings,
            "tips": it.tips,
            "booking_tip": it.booking_tip,
            "vs_preferred": it.vs_preferred,
            "ideas": [
                {
                    "strategy": idea.strategy,
                    "title": idea.title,
                    "detail": idea.detail,
                    "tickets": [self.ticket(t, it.passengers) for t in idea.tickets],
                    "extra_road": idea.extra_road,
                }
                for idea in it.ideas
            ],
            "contains_simulated": it.contains_simulated,
            "contains_estimates": True,
        }

    def notice_dict(self) -> dict[str, Any]:
        data = asdict(self.notice)
        data.pop("extra", None)
        return data

    def search(self, result: SearchResult, generated_at: str) -> dict[str, Any]:
        p = result.params
        return {
            "query": {
                "origin": self.place(p.origin),
                "destination": self.place(p.destination),
                "date": p.travel_date.isoformat(),
                "passengers": p.passengers,
                "travel_class": p.travel_class,
                "max_budget": p.max_budget,
                "max_duration_hours": (p.max_duration_minutes / 60) if p.max_duration_minutes else None,
                "max_transfers": p.max_transfers,
                "flexible_days": p.flexible_days,
                "include_nearby": p.include_nearby,
                "allow_unreserved": p.allow_unreserved,
                "smart_tickets": p.smart_tickets,
                "sort": p.sort,
            },
            "data_notice": self.notice_dict(),
            "summary": result.summary,
            "preferred": self.itinerary(result.preferred) if result.preferred else None,
            "itineraries": [self.itinerary(it) for it in result.itineraries],
            "date_strip": result.date_strip,
            "rush": result.rush,
            "hidden": result.hidden,
            "no_results_reason": result.no_results_reason,
            "no_results_message": result.no_results_message,
            "search_stats": result.stats,
            "generated_at": generated_at,
        }
