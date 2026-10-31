"""Plain-language explanations: what kind of alternative this is, why it helps,
how the legs fit together, and what to watch out for."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..availability import AvailabilityStatus
from ..models import CLASS_LABELS
from ..stations import StationDirectory
from ..timeutil import format_clock, format_day, format_duration, minutes_between
from .explorer import Endpoints, RideLeg, RoadLeg
from .itinerary import Itinerary, Ticket
from .params import SearchOptions, SearchParams
from .ranking import connections, ticket_weight

CATEGORY_PRIORITY = (
    "flexible_date",
    "smart_ticket",
    "alternative_boarding",
    "alternative_destination",
    "connecting",
    "direct",
)


@dataclass
class ExplainContext:
    directory: StationDirectory
    ends: Endpoints
    params: SearchParams
    options: SearchOptions
    preferred: Itinerary | None = None
    informative: bool = True  # False when seat availability is unknown (no live source)
    direct_by_run: dict[str, Itinerary] = field(default_factory=dict)
    standard_labels: dict[tuple[str, str, str, str], str] = field(default_factory=dict)


def classify(it: Itinerary, ends: Endpoints) -> list[str]:
    rides = it.rides
    first, last = it.legs[0].leg, it.legs[-1].leg
    feeder_ride = len(rides) >= 2 and not rides[0].train.classes and any(r.train.classes for r in rides[1:])
    cats: list[str] = []
    if it.date_offset:
        cats.append("flexible_date")
    if any(t.strategy != "standard" for t in it.tickets):
        cats.append("smart_ticket")
    if isinstance(first, RoadLeg) or feeder_ride or rides[0].from_code not in ends.origin_zero:
        cats.append("alternative_boarding")
    if isinstance(last, RoadLeg) or rides[-1].to_code not in ends.dest_zero:
        cats.append("alternative_destination")
    if (len(rides) >= 2 and not feeder_ride) or len(rides) >= 3:
        cats.append("connecting")
    if not cats:
        cats.append("direct")
    return cats


def primary_category(categories: list[str]) -> str:
    for cat in CATEGORY_PRIORITY:
        if cat in categories:
            return cat
    return "direct"


def main_ride(it: Itinerary) -> RideLeg:
    reserved = [pl.leg for pl in it.legs if isinstance(pl.leg, RideLeg) and pl.tickets[0].kind == "reserved"]
    pool = reserved or it.rides
    return max(pool, key=lambda r: r.km)


def train_label(ride: RideLeg) -> str:
    return f"{ride.train.number} {ride.train.name}"


def _tickets_for(it: Itinerary, ride: RideLeg) -> list[Ticket]:
    for pl in it.legs:
        if pl.leg is ride:
            return pl.tickets
    return []


def _special_ticket(it: Itinerary) -> tuple[RideLeg, Ticket] | None:
    for pl in it.legs:
        for t in pl.tickets:
            if t.strategy != "standard" and isinstance(pl.leg, RideLeg):
                return pl.leg, t
    return None


def _sim(it: Itinerary) -> str:
    return " (simulated)" if any(t.availability and t.availability.is_simulated for t in it.tickets) else ""


def headline(it: Itinerary, ctx: ExplainContext) -> str:
    d = ctx.directory
    main = main_ride(it)
    p = it.primary_category
    if p == "flexible_date":
        return f"Travel on {format_day(it.travel_date)} instead"
    if p == "smart_ticket":
        special = _special_ticket(it)
        if special:
            leg, t = special
            if t.strategy == "book_beyond":
                return f"Book to {d.name(t.to_code)}, get off at {d.name(leg.to_code)}"
            if t.strategy == "upstream_boarding":
                return f"Book from {d.name(t.from_code)}, board at {d.name(leg.from_code)}"
            return f"Same train, two tickets split at {d.name(t.to_code)}"
    if p == "alternative_boarding":
        rides = it.rides
        first = rides[0] if rides[0].train.classes else main  # skip an unreserved feeder train
        text = f"Board at {d.name(first.from_code)} instead of {ctx.ends.origin_label}"
        if first is not rides[0]:
            text += f" (general-class train from {d.name(rides[0].from_code)})"
        changes = [r for r in rides if r.train.classes and r is not first and r.dep > first.dep]
        if changes:
            text += f", change at {d.name(changes[0].from_code)}"
        return text
    if p == "alternative_destination":
        last = it.legs[-1].leg
        station = it.rides[-1].to_code
        km = last.km if isinstance(last, RoadLeg) else 0
        tail = f", {km} km from {ctx.ends.destination_label}" if km else ""
        return f"Get off at {d.name(station)}{tail}"
    if p == "connecting":
        names = [d.name(r.to_code) for r in it.rides[:-1]]
        return "Change at " + " and ".join(names)
    return f"Direct: {main.train.name}"


def _std_label(ctx: ExplainContext, ride: RideLeg, from_code: str, to_code: str, cls: str) -> str | None:
    return ctx.standard_labels.get((ride.run.key, from_code, to_code, cls))


def build_why(it: Itinerary, ctx: ExplainContext) -> list[str]:
    d = ctx.directory
    out: list[str] = []
    main = main_ride(it)
    main_tickets = _tickets_for(it, main)
    status = it.overall_status
    sim = _sim(it)
    p = it.primary_category
    if not ctx.informative:
        out.append(_plain_reason(it, ctx))
    elif status == AvailabilityStatus.CONFIRMED.value:
        if p == "smart_ticket" and (special := _special_ticket(it)):
            leg, t = special
            std = _std_label(ctx, leg, leg.from_code, leg.to_code, t.travel_class)
            if t.strategy == "book_beyond":
                out.append(
                    f"A ticket to {d.name(t.to_code)} shows {t.availability.label}{sim}"
                    + (f", while one only to {d.name(leg.to_code)} is {std}." if std else ".")
                )
            elif t.strategy == "upstream_boarding":
                out.append(
                    f"A ticket from {d.name(t.from_code)} shows {t.availability.label}{sim}"
                    + (f"; from {d.name(leg.from_code)} it is {std}." if std else ".")
                )
            else:
                halves = [x for x in _tickets_for(it, leg)]
                out.append(
                    f"Both halves ({halves[0].from_code}→{halves[0].to_code} and "
                    f"{halves[-1].from_code}→{halves[-1].to_code}) show seats{sim}, so you stay on one train"
                    + (f" even though the full ticket is {std}." if std else ".")
                )
        elif p == "alternative_boarding":
            t = main_tickets[0]
            contrast = ctx.direct_by_run.get(main.run.key)
            if contrast and contrast.overall_status != AvailabilityStatus.CONFIRMED.value:
                c_ride = contrast.rides[0]
                c_label = contrast.legs[0].tickets[0].availability.label if contrast.legs[0].tickets[0].availability else "not checked"
                out.append(
                    f"{train_label(main)} shows {t.availability.label}{sim} from {d.name(main.from_code)}, "
                    f"while the same train is {c_label} from {d.name(c_ride.from_code)}."
                )
            else:
                out.append(f"{train_label(main)} shows {t.availability.label}{sim} from {d.name(main.from_code)}.")
        elif p == "alternative_destination":
            t = main_tickets[-1]
            out.append(
                f"Seats show to {d.name(main.to_code)} ({t.availability.label}{sim}); "
                f"you finish the last stretch to {ctx.ends.destination_label} by road."
            )
        elif p == "connecting":
            parts = [
                f"{r.train.number} {_tickets_for(it, r)[0].availability.label if _tickets_for(it, r)[0].availability else 'UR'}"
                for r in it.rides
            ]
            out.append("Every train on this route shows seats" + sim + ": " + ", ".join(parts) + ".")
        elif p == "flexible_date":
            t = main_tickets[0]
            out.append(f"{train_label(main)} shows {t.availability.label}{sim} on {format_day(it.travel_date)}.")
        else:
            t = main_tickets[0]
            out.append(f"Direct train with seats showing as {t.availability.label}{sim}.")
    elif status == "UNRESERVED":
        out.append("No reservation needed: general (UR) tickets only, so seats are not guaranteed.")
    else:
        labels = [
            f"{t.run.train.number} {t.availability.label if t.availability else 'not checked'}"
            for t in it.reserved_tickets
        ]
        out.append(f"Seat status {', '.join(labels)}{sim} — a confirmed seat is not certain.")

    pref = ctx.preferred
    if pref is not None and pref is not it:
        pref_name = pref.rides[0].train.number
        leave_gap = abs(minutes_between(pref.depart_at, it.depart_at))
        arrive_gap = minutes_between(pref.arrive_at, it.arrive_at)
        if leave_gap <= 90:
            if abs(arrive_gap) < 10:
                out.append(f"Arrives about when the direct {pref_name} does.")
            else:
                word = "later" if arrive_gap > 0 else "earlier"
                out.append(f"Arrives {format_duration(abs(arrive_gap))} {word} than the direct {pref_name}.")
        else:
            extra = it.total_minutes - pref.total_minutes
            if abs(extra) < 10:
                timing = f"about as long as the direct {pref_name}"
            else:
                timing = f"{format_duration(abs(extra))} {'longer' if extra > 0 else 'shorter'} than the direct {pref_name}"
            out.append(
                f"Takes {format_duration(it.total_minutes)} door to door — {timing} "
                f"(which leaves at {format_clock(pref.depart_at)})."
            )
        cost = it.cost_per_person - pref.cost_per_person
        if cost > 0:
            out.append(f"About ₹{cost} more per person than the direct train (estimated fares).")
        elif cost < 0:
            out.append(f"About ₹{-cost} cheaper per person than the direct train (estimated fares).")
    elif pref is it:
        out.append("Fastest direct train in your class — the option most people would pick first.")
    if it.connection_quality == "comfortable":
        out.append("Connection buffer is comfortable for typical delays.")
    return out


def _plain_reason(it: Itinerary, ctx: ExplainContext) -> str:
    """Why an option exists, without claiming anything about seats."""
    d = ctx.directory
    main = main_ride(it)
    p = it.primary_category
    origin, destination = ctx.ends.origin_label, ctx.ends.destination_label
    if p == "alternative_boarding":
        first = it.rides[0] if it.rides[0].train.classes else main
        return (
            f"Starts from {d.name(first.from_code)} instead of {origin} — a separate option if trains from "
            f"{origin} are full."
        )
    if p == "alternative_destination":
        return f"Ends at {d.name(it.rides[-1].to_code)}, close to {destination}; finish the last stretch by road."
    if p == "connecting":
        joints = " and ".join(d.name(r.to_code) for r in it.rides[:-1])
        return f"Two trains with a change at {joints} — useful when no direct train has seats."
    if p == "flexible_date":
        return f"{train_label(main)} also runs on {format_day(it.travel_date)}."
    return f"Direct: {train_label(main)} — no change of train."


def build_fits(it: Itinerary, ctx: ExplainContext) -> list[str]:
    d, opts = ctx.directory, ctx.options
    out: list[str] = []
    legs = it.legs
    for idx, pl in enumerate(legs):
        leg = pl.leg
        if isinstance(leg, RoadLeg):
            if leg.purpose == "feeder" and idx + 1 < len(legs):
                nxt = legs[idx + 1].leg
                out.append(
                    f"Leave {d.name(leg.from_code)} by {format_clock(leg.dep)}: about "
                    f"{format_duration(leg.minutes)} by {leg.estimate.mode.lower()} (estimate) gets you to "
                    f"{d.name(leg.to_code)} {opts.feeder_buffer_minutes} min before "
                    f"{nxt.train.number if isinstance(nxt, RideLeg) else 'departure'} leaves at {format_clock(nxt.dep)}."
                )
            elif leg.purpose == "onward":
                out.append(
                    f"From {d.name(leg.from_code)}, continue to {d.name(leg.to_code)} by "
                    f"{leg.estimate.mode.lower()} — about {format_duration(leg.minutes)} (estimate)."
                )
            continue
        train = leg.train
        days = train.runs_on_label()
        runs = "daily" if days == "Daily" else f"on {days}"
        out.append(
            f"{train.number} halts at both {d.name(leg.from_code)} ({format_clock(leg.dep)}) and "
            f"{d.name(leg.to_code)} ({format_clock(leg.arr)}). It runs {runs}, so "
            f"{format_day(leg.run.start_date)} is a running day."
        )
        if leg.arr.date() > leg.dep.date():
            out.append(
                f"{train.number} runs overnight: you reach {d.name(leg.to_code)} on {format_day(leg.arr.date())}."
            )
        tickets = pl.tickets
        if len(tickets) == 2:
            m = tickets[0].to_code
            m_time = leg.run.arr_at(tickets[0].to_idx)
            out.append(
                f"Stay on {train.number}: your first ticket ends and the second starts at {d.name(m)} "
                f"({format_clock(m_time)}). You may need to move to another coach or berth there."
            )
        elif tickets and tickets[0].strategy == "book_beyond":
            out.append(
                f"Your ticket runs to {d.name(tickets[0].to_code)}; simply get off at {d.name(leg.to_code)}."
            )
        elif tickets and tickets[0].strategy == "upstream_boarding":
            out.append(
                f"Your ticket starts at {d.name(tickets[0].from_code)}; change the boarding point to "
                f"{d.name(leg.from_code)} so the seat is held for you there."
            )
    for c in connections(it):
        a, b = c["arrive"], c["depart"]
        if c["station_change"]:
            out.append(
                f"{a.train.number} reaches {d.name(a.to_code)} at {format_clock(a.arr)}; cross to "
                f"{d.name(b.from_code)} by road (estimate), and {b.train.number} leaves at "
                f"{format_clock(b.dep)} — {format_duration(c['slack'])} to spare."
            )
        else:
            out.append(
                f"{a.train.number} reaches {d.name(a.to_code)} at {format_clock(a.arr)}; {b.train.number} "
                f"leaves at {format_clock(b.dep)} — {format_duration(c['gap'])} to change "
                f"(minimum {opts.min_transfer_minutes} min)."
            )
    return out


def build_warnings(it: Itinerary, ctx: ExplainContext) -> list[str]:
    d = ctx.directory
    out: list[str] = []
    rides_with_reserved = {t.run.key for t in it.reserved_tickets}
    train_runs = {r.run.key for r in it.rides}
    if len(train_runs) >= 2:
        out.append(
            "Separate tickets: each booking stands alone. If one train is late and you miss the next, "
            "the next ticket is not protected as a single through journey."
        )
    elif len(it.reserved_tickets) >= 2 and len(rides_with_reserved) == 1:
        out.append("Two PNRs on one train: cancelling or changing one does not change the other.")
    if any(t.kind == "unreserved" for t in it.tickets):
        out.append(
            "Unreserved (UR) ticket: travel only in General coaches. Never sit in reserved coaches or "
            "berths with it. Buy it on the UTS app or at the station counter."
        )
    for pl in it.legs:
        for t in pl.tickets:
            if t.strategy == "book_beyond" and isinstance(pl.leg, RideLeg):
                out.append(
                    f"You pay the fare to {d.name(t.to_code)}. Getting off early at "
                    f"{d.name(pl.leg.to_code)} is allowed, but the unused part is not refunded."
                )
            if t.strategy == "upstream_boarding" and isinstance(pl.leg, RideLeg):
                out.append(
                    f"Change the boarding point to {d.name(pl.leg.from_code)} through the official booking "
                    f"channel before its deadline. If you neither board at {d.name(t.from_code)} nor change it, "
                    "the berth can be given to someone else."
                )
    for c in connections(it):
        if c["slack"] < ctx.options.comfortable_buffer_minutes:
            out.append(
                f"Tight connection at {d.name(c['depart'].from_code)} ({format_duration(c['slack'])}). "
                "Trains often run late — consider a later option."
            )
        elif c["slack"] > 240:
            out.append(f"Long wait at {d.name(c['depart'].from_code)} ({format_duration(c['gap'])}).")
    mismatched = [t for t in it.reserved_tickets if t.class_mismatch]
    if mismatched:
        t = mismatched[0]
        out.append(
            f"Class differs from your choice: {CLASS_LABELS.get(t.travel_class, t.travel_class)} "
            f"instead of {CLASS_LABELS.get(it.preferred_class, it.preferred_class)} on {t.run.train.number}."
        )
    statuses = {t.status for t in it.reserved_tickets}
    if AvailabilityStatus.WAITLISTED in statuses:
        out.append(
            "Waitlisted e-tickets that are still fully waitlisted after the chart is prepared are "
            "cancelled automatically — you cannot travel on them."
        )
    if AvailabilityStatus.RAC in statuses:
        out.append("RAC gives you a shared berth; it may upgrade to a full berth if others cancel.")
    if AvailabilityStatus.UNKNOWN in statuses and ctx.informative:
        out.append("Seat availability was not checked for at least one ticket.")
    for note in dict.fromkeys(n for r in it.rides for n in r.train.notes):
        out.append(f"{note}")
    if it.has_road:
        out.append("Road times and costs are rough estimates — check a maps app before you go.")
    return out


def build_tips(it: Itinerary, ctx: ExplainContext) -> list[str]:
    d = ctx.directory
    tips: list[str] = []
    last = it.rides[-1]
    stops = last.train.stops
    for k in range(last.board + 1, last.alight):
        code = stops[k].station
        if code in ctx.ends.dest_zero and stops[k].alightable:
            tips.append(
                f"{last.train.number} also halts at {d.name(code)} at {format_clock(last.run.arr_at(k))} "
                "if that is closer for you."
            )
    return tips


def booking_tip(it: Itinerary) -> str | None:
    reserved = it.reserved_tickets
    unreserved = [t for t in it.tickets if t.kind == "unreserved"]
    if len(reserved) >= 2:
        ordered = sorted(reserved, key=ticket_weight)
        first = ordered[0]
        return (
            f"Book the scarcest ticket first: {first.run.train.number} "
            f"{first.from_code}→{first.to_code} ({first.availability.label if first.availability else 'unchecked'}), "
            "then the rest."
        )
    if reserved and unreserved:
        return (
            f"Book {reserved[0].run.train.number} first; buy the unreserved ticket on the day "
            "(UTS app or counter)."
        )
    return None


def explain(it: Itinerary, ctx: ExplainContext) -> None:
    it.headline = headline(it, ctx)
    it.why = build_why(it, ctx)
    it.fits = build_fits(it, ctx)
    it.warnings = build_warnings(it, ctx)
    it.tips = build_tips(it, ctx)
    it.booking_tip = booking_tip(it)
    pref = ctx.preferred
    if pref is not None and pref is not it:
        it.vs_preferred = {
            "extra_cost_per_person": it.cost_per_person - pref.cost_per_person,
            "extra_minutes": it.total_minutes - pref.total_minutes,
            "arrival_delta_minutes": minutes_between(pref.arrive_at, it.arrive_at),
        }
    else:
        it.vs_preferred = None
