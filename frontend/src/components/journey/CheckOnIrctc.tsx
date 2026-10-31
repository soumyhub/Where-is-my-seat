"use client";

import { Check, Copy, ExternalLink } from "lucide-react";
import { useState } from "react";

import { CLASS_NAMES, formatFullDate, formatRupees } from "@/lib/format";
import type { Ticket } from "@/lib/types";

import { StatusPill, TrainBadge } from "../ui";
import { TicketLiveActions } from "./LiveSeats";

const IRCTC = "https://www.irctc.co.in/nget/train-search";

/** Is there a real seat status to show? (Simulated demo or a live provider.) */
export function hasSeatStatus(t: Ticket): boolean {
  return !!t.availability && t.availability.status !== "UNKNOWN";
}

export function irctcText(t: Ticket): string {
  return `${t.train_number} · ${t.from_station.code} → ${t.to_station.code} · ${formatFullDate(t.journey_date)} · ${t.travel_class}`;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async (e) => {
        e.stopPropagation();
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        } catch {
          window.prompt("Copy these details", text);
        }
      }}
      className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-wims-blue hover:bg-[#eaf3fb]"
      aria-label="Copy ticket details"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-wims-green-dark" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

/** What to type into IRCTC for one ticket, plus the official link. */
export function TicketCheck({
  ticket,
  simulatedTrain,
  trainName,
}: {
  ticket: Ticket;
  simulatedTrain?: boolean;
  trainName?: string;
}) {
  const unreserved = ticket.kind === "unreserved";
  return (
    <div className="rounded-md border border-wims-hairline bg-white p-3">
      <div className="flex flex-wrap items-center gap-2">
        <TrainBadge number={ticket.train_number} simulated={simulatedTrain} />
        <span className="text-sm font-medium text-wims-text">
          {ticket.from_station.name} <span className="text-wims-muted">({ticket.from_station.code})</span> →{" "}
          {ticket.to_station.name} <span className="text-wims-muted">({ticket.to_station.code})</span>
        </span>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[13px] sm:grid-cols-4">
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-wims-muted">Date</dt>
          <dd className="font-medium text-wims-text">{formatFullDate(ticket.journey_date)}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-wims-muted">Class</dt>
          <dd className="font-medium text-wims-text">
            {unreserved ? "General (UR)" : `${ticket.travel_class} · ${CLASS_NAMES[ticket.travel_class] ?? ticket.class_label}`}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-wims-muted">Fare (est.)</dt>
          <dd className="font-medium text-wims-text">≈ {formatRupees(ticket.fare.per_person)}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-wims-muted">Seats</dt>
          <dd>
            {hasSeatStatus(ticket) ? (
              <StatusPill status={ticket.availability!.status} availability={ticket.availability} size="sm" />
            ) : (
              <span className="text-[13px] text-wims-muted">{unreserved ? "No reservation needed" : "Check on IRCTC"}</span>
            )}
          </dd>
        </div>
      </dl>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {unreserved ? (
          <a
            href={ticket.booking.url ?? "https://www.utsonmobile.indianrail.gov.in/"}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1.5 rounded bg-wims-blue px-3 py-1.5 text-xs font-medium text-white hover:bg-wims-blue-hover"
          >
            Buy on UTS app <ExternalLink className="h-3.5 w-3.5" />
          </a>
        ) : ticket.booking.bookable ? (
          <a
            href={ticket.booking.url ?? IRCTC}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1.5 rounded bg-wims-green px-3 py-1.5 text-xs font-medium text-white hover:bg-wims-green-dark"
          >
            Check seats on IRCTC <ExternalLink className="h-3.5 w-3.5" />
          </a>
        ) : (
          <span className="text-xs text-wims-muted">{ticket.booking.channel}</span>
        )}
        <CopyButton text={irctcText(ticket)} />
        {!simulatedTrain && <TicketLiveActions ticket={ticket} trainName={trainName ?? `Train ${ticket.train_number}`} />}
      </div>
    </div>
  );
}
