"use client";

import { ArrowRight, Bus, ChevronRight, ExternalLink } from "lucide-react";

import { CATEGORY_LABELS, CLASS_ORDER, dayDelta, formatDuration, formatRupees, formatTime, runningDays } from "@/lib/format";
import type { Itinerary } from "@/lib/types";

import { hasSeatStatus } from "../journey/CheckOnIrctc";
import { SimTag, StatusPill, TrainBadge } from "../ui";

function Days({ label }: { label: string }) {
  if (label === "Daily") return <span className="text-xs font-medium text-wims-green-dark">Runs daily</span>;
  return (
    <span className="flex gap-[3px] font-mono text-[11px] font-medium" aria-label={`Runs on ${label}`}>
      {runningDays(label).map((d) => (
        <span key={d.name} className={d.runs ? "text-wims-green-dark" : "text-[#c4c4c4]"}>
          {d.letter}
        </span>
      ))}
    </span>
  );
}

function selectedBorder(selected: boolean) {
  return selected ? "ring-2 ring-wims-badge" : "hover:shadow-[0_2px_6px_rgba(0,0,0,0.16)]";
}

/** A direct train, laid out like a row in Where is my Train's "trains between stations". */
export function DirectTrainCard({
  it,
  travelClass,
  selected,
  onSelect,
}: {
  it: Itinerary;
  travelClass: string;
  selected: boolean;
  onSelect: () => void;
}) {
  const leg = it.legs[0];
  const train = leg.train!;
  const ticket = leg.tickets[0];
  const days = dayDelta(it.depart_at, it.arrive_at);
  const fares = Object.entries(leg.class_fares).sort((a, b) => CLASS_ORDER.indexOf(a[0]) - CLASS_ORDER.indexOf(b[0]));
  const seatStatus = ticket && hasSeatStatus(ticket) ? ticket.availability : null;

  return (
    <article
      onClick={onSelect}
      className={`cursor-pointer rounded-[3px] bg-white shadow-[0_1px_2px_rgba(0,0,0,0.14)] transition-shadow ${selectedBorder(selected)}`}
      aria-current={selected ? "true" : undefined}
    >
      <div className="flex items-center gap-2 px-4 pt-3">
        <TrainBadge number={train.number} simulated={train.simulated} />
        <h3 className="min-w-0 flex-1 truncate text-[15px] font-medium text-wims-text" title={train.name}>
          {train.name}
        </h3>
        <Days label={train.runs_on} />
      </div>
      <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-4 pt-2">
        <div>
          <div className="tabular text-[22px] font-medium leading-none text-wims-text">{formatTime(it.depart_at)}</div>
          <div className="mt-1 max-w-[11rem] truncate text-xs text-wims-muted">
            {leg.from_station.name} ({leg.from_station.code})
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs text-wims-muted">
          <span className="h-px flex-1 bg-[#cfd8e3]" />
          <span className="whitespace-nowrap">{formatDuration(it.total_minutes)}</span>
          <span className="h-px flex-1 bg-[#cfd8e3]" />
        </div>
        <div className="text-right">
          <div className="tabular text-[22px] font-medium leading-none text-wims-text">
            {formatTime(it.arrive_at)}
            {days > 0 && <sup className="ml-0.5 text-[11px] text-wims-late">+{days}</sup>}
          </div>
          <div className="mt-1 max-w-[11rem] truncate text-xs text-wims-muted">
            {leg.to_station.name} ({leg.to_station.code})
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 px-4 py-3">
        {fares.map(([cls, fare]) => {
          const mine = cls === travelClass || (travelClass === "ANY" && cls === ticket?.travel_class);
          return (
            <span
              key={cls}
              className={`inline-flex overflow-hidden rounded-[3px] border text-[12px] font-medium ${
                mine ? "border-wims-green" : "border-[#d5dde6]"
              }`}
            >
              <span className={`px-1.5 py-0.5 ${mine ? "bg-wims-green text-white" : "bg-[#f2f5f8] text-wims-text"}`}>
                {cls === "UR" ? "GEN" : cls}
              </span>
              <span className={`px-1.5 py-0.5 ${mine ? "text-wims-green-dark" : "text-wims-muted"}`}>≈{formatRupees(fare)}</span>
            </span>
          );
        })}
        {train.category !== "Express" && (
          <span className="rounded-sm bg-[#eef1f5] px-1.5 py-0.5 text-[11px] font-medium text-wims-muted">{train.category}</span>
        )}
        <span className="ml-auto flex items-center gap-2">
          {seatStatus && <StatusPill status={seatStatus.status} availability={seatStatus} size="sm" />}
          {!seatStatus && ticket?.kind === "reserved" && ticket.booking.bookable && (
            <a
              href={ticket.booking.url ?? "https://www.irctc.co.in/nget/train-search"}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1 rounded border border-wims-green px-2.5 py-1 text-xs font-medium text-wims-green-dark hover:bg-wims-green-tint"
            >
              Check seats <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </span>
      </div>
      {it.ideas.length > 0 && (
        <div className="flex items-center gap-1 border-t border-wims-hairline px-4 py-2 text-[12.5px] text-wims-blue">
          If it&apos;s full: {it.ideas.length} backup ticket{it.ideas.length > 1 ? "s" : ""} to try
          <ChevronRight className="h-4 w-4" />
        </div>
      )}
    </article>
  );
}

/** Any option that is not a plain direct train: a change, another station or another date. */
export function RouteCard({
  it,
  selected,
  onSelect,
  similar = 0,
  onShowSimilar,
}: {
  it: Itinerary;
  selected: boolean;
  onSelect: () => void;
  similar?: number;
  onShowSimilar?: () => void;
}) {
  const days = dayDelta(it.depart_at, it.arrive_at);
  const tickets = it.legs.flatMap((l) => l.tickets);
  const status = tickets.find((t) => hasSeatStatus(t))?.availability ? it.overall_status : null;
  return (
    <article
      onClick={onSelect}
      className={`cursor-pointer rounded-[3px] bg-white shadow-[0_1px_2px_rgba(0,0,0,0.14)] transition-shadow ${selectedBorder(selected)}`}
      aria-current={selected ? "true" : undefined}
    >
      <div className="px-4 pt-3">
        <div className="flex items-start gap-2">
          <span className="mt-0.5 shrink-0 rounded-sm bg-[#eaf3fb] px-1.5 py-0.5 text-[11px] font-medium text-wims-blue">
            {CATEGORY_LABELS[it.primary_category] ?? it.primary_category}
          </span>
          <h3 className="min-w-0 flex-1 text-[15px] font-medium leading-snug text-wims-text">{it.headline}</h3>
          {status && <StatusPill status={status} size="sm" />}
          {it.contains_simulated && <SimTag />}
        </div>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-2">
          <span className="tabular text-[19px] font-medium text-wims-text">{formatTime(it.depart_at)}</span>
          <ArrowRight className="h-4 w-4 self-center text-wims-sky" aria-label="to" />
          <span className="tabular text-[19px] font-medium text-wims-text">{formatTime(it.arrive_at)}</span>
          {days > 0 && <span className="text-xs font-medium text-wims-late">+{days} day</span>}
          <span className="text-sm text-wims-muted">
            {formatDuration(it.total_minutes)} · {it.transfers} change{it.transfers === 1 ? "" : "s"}
          </span>
          <span className="ml-auto text-sm font-medium text-wims-text">≈ {formatRupees(it.cost_per_person)}</span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-1.5 gap-y-1 pb-3 text-[12.5px] text-wims-muted">
          {it.legs.map((leg, i) => (
            <span key={i} className="inline-flex items-center gap-1.5">
              {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-[#b0b8c2]" aria-hidden />}
              {leg.train ? (
                <>
                  <TrainBadge number={leg.train.number} />
                  <span>
                    {leg.from_station.code}→{leg.to_station.code}
                  </span>
                </>
              ) : (
                <span className="inline-flex items-center gap-1">
                  <Bus className="h-3.5 w-3.5" aria-hidden /> {leg.from_station.code}→{leg.to_station.code} by road
                </span>
              )}
            </span>
          ))}
        </div>
      </div>
      {similar > 0 && onShowSimilar && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onShowSimilar();
          }}
          className="flex w-full items-center gap-1 border-t border-wims-hairline px-4 py-2 text-left text-[12.5px] text-wims-blue"
        >
          {similar} more like this <ChevronRight className="h-4 w-4" />
        </button>
      )}
    </article>
  );
}
