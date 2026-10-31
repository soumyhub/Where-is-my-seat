"""Ticketing: choose a class per ride, check availability, price it, and try
smart-ticket strategies when the plain ticket is not confirmed.

Strategies (all keep the traveller on a valid ticket for the journey actually made):

* ``book_beyond``  — buy to a later stop on the same train and get off early.
* ``upstream_boarding`` — buy from an earlier stop and officially change the boarding
  point to where you actually board.
* ``split`` — two tickets on the same train that meet at an intermediate halt.
"""

from __future__ import annotations

from ..availability import STATUS_RANK, AvailabilitySession, AvailabilityStatus, TicketQuery
from ..fares import FareEstimator
from ..models import Train, TrainRun
from ..stations import StationDirectory
from ..road import RoadEstimate
from .explorer import RideLeg, RoadLeg, RouteCandidate
from .itinerary import Itinerary, PricedLeg, Ticket, TicketIdea
from .params import SearchLimits, SearchParams

# Closest substitute when a train does not carry the preferred class.
CLASS_FALLBACKS: dict[str, tuple[str, ...]] = {
    "1A": ("2A", "3A", "CC"),
    "2A": ("3A", "1A", "CC"),
    "3A": ("CC", "2A", "SL"),
    "SL": ("2S", "3A", "CC"),
    "CC": ("3A", "2S", "2A"),
    "2S": ("SL", "CC", "3A"),
}
ANY_CLASS_ORDER = ("3A", "SL", "CC", "2S", "2A", "1A")


class TicketPlanner:
    def __init__(
        self,
        session: AvailabilitySession,
        fares: FareEstimator,
        directory: StationDirectory,
        params: SearchParams,
        limits: SearchLimits,
        informative: bool = True,
    ) -> None:
        self.session = session
        self.fares = fares
        self.directory = directory
        self.params = params
        self.limits = limits
        # False when no live or simulated availability exists: strategies then become
        # "ideas to check" instead of verified alternatives.
        self.informative = informative

    # ----- itineraries --------------------------------------------------
    def price(self, candidates: list[RouteCandidate]) -> list[Itinerary]:
        out: list[Itinerary] = []
        for index, candidate in enumerate(candidates):
            base_legs = [self._priced_leg(leg) for leg in candidate.legs]
            out.append(self.build_itinerary(base_legs, candidate))
            if not self.informative or not self.params.smart_tickets or index >= self.limits.strategy_candidates:
                continue
            reserved = [i for i, pl in enumerate(base_legs) if pl.tickets and pl.tickets[0].kind == "reserved"]
            if len(reserved) != 1:
                continue  # strategies apply to the single reserved train of a journey
            li = reserved[0]
            main = base_legs[li]
            assert isinstance(main.leg, RideLeg)
            for tickets in self.strategy_variants(main.leg, main.tickets[0]):
                legs = list(base_legs)
                legs[li] = PricedLeg(main.leg, tickets)
                out.append(self.build_itinerary(legs, candidate))
        return out

    def build_itinerary(self, legs: list[PricedLeg], candidate: RouteCandidate) -> Itinerary:
        fresh = [PricedLeg(pl.leg, list(pl.tickets)) for pl in legs]
        for i in range(1, len(fresh)):
            prev, cur = fresh[i - 1].leg, fresh[i].leg
            fresh[i].buffer_before = int((cur.dep - prev.arr).total_seconds() // 60)
        p = self.params
        return Itinerary(
            legs=fresh,
            requested_date=p.travel_date,
            travel_date=candidate.travel_date,
            passengers=p.passengers,
            preferred_class=p.travel_class,
            origin_key=p.origin.key,
            destination_key=p.destination.key,
        )

    def _priced_leg(self, leg: RideLeg | RoadLeg) -> PricedLeg:
        if isinstance(leg, RoadLeg):
            return PricedLeg(leg, [])
        return PricedLeg(leg, [self.standard_ticket(leg)])

    # ----- tickets ------------------------------------------------------
    def class_order(self, train: Train) -> list[str]:
        preferred = self.params.travel_class
        if preferred == "ANY":
            return [c for c in ANY_CLASS_ORDER if c in train.classes][:3]
        if preferred in train.classes:
            return [preferred]
        for cls in CLASS_FALLBACKS.get(preferred, ()):
            if cls in train.classes:
                return [cls]
        return [train.classes[0]]

    def standard_ticket(self, ride: RideLeg) -> Ticket:
        train = ride.train
        if not train.classes:
            return Ticket(
                kind="unreserved",
                run=ride.run,
                from_idx=ride.board,
                to_idx=ride.alight,
                travel_class="UR",
                quota="UR",
                strategy="standard",
                class_mismatch=False,
                availability=None,
                fare_per_person=self.fares.estimate(train, "UR", ride.km),
            )
        best: Ticket | None = None
        for cls in self.class_order(train):
            ticket = self.reserved(ride.run, ride.board, ride.alight, cls, "standard")
            if best is None or _rank(ticket) > _rank(best):
                best = ticket
            if ticket.status is AvailabilityStatus.CONFIRMED:
                break
        assert best is not None
        return best

    def reserved(self, run: TrainRun, i: int, j: int, cls: str, strategy: str) -> Ticket:
        stops = run.train.stops
        query = TicketQuery(
            train_number=run.train.number,
            journey_date=run.dep_at(i).date(),
            from_code=stops[i].station,
            to_code=stops[j].station,
            travel_class=cls,
            quota="GN",
            passengers=self.params.passengers,
        )
        preferred = self.params.travel_class
        return Ticket(
            kind="reserved",
            run=run,
            from_idx=i,
            to_idx=j,
            travel_class=cls,
            quota="GN",
            strategy=strategy,
            class_mismatch=preferred not in ("ANY", cls),
            availability=self.session.check(query),
            fare_per_person=self.fares.estimate(run.train, cls, stops[j].km - stops[i].km),
        )

    # ----- smart-ticket strategies --------------------------------------
    def strategy_variants(self, ride: RideLeg, standard: Ticket) -> list[list[Ticket]]:
        if standard.kind != "reserved" or standard.status is AvailabilityStatus.CONFIRMED:
            return []
        run, cls = ride.run, standard.travel_class
        stops = run.train.stops
        i, j = ride.board, ride.alight
        variants: list[list[Ticket]] = []

        for k in range(j + 1, min(j + 4, len(stops))):
            if not stops[k].alightable:
                continue
            ticket = self.reserved(run, i, k, cls, "book_beyond")
            if ticket.status is AvailabilityStatus.CONFIRMED:
                variants.append([ticket])
                break

        for k in range(i - 1, max(-1, i - 4), -1):
            if not stops[k].boardable:
                continue
            ticket = self.reserved(run, k, j, cls, "upstream_boarding")
            if ticket.status is AvailabilityStatus.CONFIRMED:
                variants.append([ticket])
                break

        total = stops[j].km - stops[i].km

        def balance(m: int) -> float:
            first = stops[m].km - stops[i].km
            imbalance = abs(first - (total - first))
            station = self.directory.get(stops[m].station)
            return imbalance * (0.6 if station and station.junction else 1.0)

        middles = sorted(
            (m for m in range(i + 1, j) if stops[m].boardable and stops[m].alightable), key=balance
        )[: self.limits.max_split_points]
        for m in middles:
            first = self.reserved(run, i, m, cls, "split")
            if first.status is not AvailabilityStatus.CONFIRMED:
                continue
            second = self.reserved(run, m, j, cls, "split")
            if second.status is AvailabilityStatus.CONFIRMED:
                variants.append([first, second])
                break
        return variants


    # ----- ideas to check when availability is not live -------------------
    def ideas(self, ride: RideLeg, standard: Ticket, feeders: dict[str, RoadEstimate]) -> list[TicketIdea]:
        """Backup tickets on the same train, most promising first. Nothing here claims a seat."""
        if standard.kind != "reserved" or not self.params.smart_tickets:
            return []
        run, cls = ride.run, standard.travel_class
        stops = run.train.stops
        i, j = ride.board, ride.alight
        d = self.directory.name
        out: list[TicketIdea] = []

        if i > 0 and stops[0].boardable:
            t = self.reserved(run, 0, j, cls, "upstream_boarding")
            out.append(
                TicketIdea(
                    "upstream_boarding",
                    f"Book from {d(stops[0].station)}, board at {d(ride.from_code)}",
                    "The starting station usually holds the train's largest general quota. After booking, "
                    f"change your boarding point to {d(ride.from_code)} on IRCTC.",
                    [t],
                )
            )

        later = [k for k in range(j + 1, len(stops)) if stops[k].alightable]
        if later:
            junctions = [k for k in later if (s := self.directory.get(stops[k].station)) and s.junction]
            k = later[-1] if len(later) <= 4 else (junctions[0] if junctions else later[0])
            t = self.reserved(run, i, k, cls, "book_beyond")
            out.append(
                TicketIdea(
                    "book_beyond",
                    f"Book till {d(stops[k].station)}, get off at {d(ride.to_code)}",
                    "Longer tickets sometimes still show seats when shorter ones are waitlisted. You pay the "
                    "longer fare; getting off early is allowed.",
                    [t],
                )
            )

        total = stops[j].km - stops[i].km

        def balance(m: int) -> float:
            first = stops[m].km - stops[i].km
            station = self.directory.get(stops[m].station)
            return abs(first - (total - first)) * (0.5 if station and station.junction else 1.0)

        def central(m: int) -> bool:  # a split right next to either end does not help
            share = (stops[m].km - stops[i].km) / total if total else 0
            return 0.2 <= share <= 0.8

        middles = sorted(
            (m for m in range(i + 1, j) if stops[m].boardable and stops[m].alightable and central(m)), key=balance
        )
        if middles:
            m = middles[0]
            out.append(
                TicketIdea(
                    "split",
                    f"Two tickets, split at {d(stops[m].station)}",
                    f"Check {ride.from_code}→{stops[m].station} and {stops[m].station}→{ride.to_code} separately. "
                    f"If both have seats you stay on the same train, maybe changing seats at {d(stops[m].station)}.",
                    [self.reserved(run, i, m, cls, "split"), self.reserved(run, m, j, cls, "split")],
                )
            )

        for k in range(i + 1, j):
            code = stops[k].station
            est = feeders.get(code)
            if est is None or not stops[k].boardable:
                continue
            out.append(
                TicketIdea(
                    "later_boarding",
                    f"Board at {d(code)} instead",
                    f"Each boarding station has its own quota. {d(code)} is about {est.km} km away — roughly "
                    f"{est.minutes // 60}h {est.minutes % 60:02d}m by {est.mode.lower()} (estimate).",
                    [self.reserved(run, k, j, cls, "later_boarding")],
                    {"mode": est.mode, "minutes": est.minutes, "km": est.km, "cost_per_person": est.cost_per_person},
                )
            )
            break
        return out


def _rank(ticket: Ticket) -> int:
    return STATUS_RANK[ticket.status or AvailabilityStatus.UNKNOWN]
