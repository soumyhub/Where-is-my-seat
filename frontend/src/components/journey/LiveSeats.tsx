"use client";

import { BellPlus, BellRing, Radio } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import { formatTime } from "@/lib/format";
import { useMeta } from "@/lib/hooks";
import {
  addWatch,
  recordWatchCheck,
  removeWatch,
  useWatches,
  watchId,
  type WatchCheck,
  type WatchTicket,
} from "@/lib/storage";
import type { Availability, LiveUsage, Ticket } from "@/lib/types";

import { Spinner, StatusPill } from "../ui";

/** True when the server has a live seat source for single-ticket checks. */
export function useLiveChecks(): boolean {
  return useMeta().data?.data_notice.live_checks ?? false;
}

export function watchTicketFrom(ticket: Ticket, trainName: string): WatchTicket {
  return {
    train_number: ticket.train_number,
    train_name: trainName,
    from_code: ticket.from_station.code,
    from_name: ticket.from_station.name,
    to_code: ticket.to_station.code,
    to_name: ticket.to_station.name,
    journey_date: ticket.journey_date,
    travel_class: ticket.travel_class,
  };
}

/** A live answer as a Seat Watch reading; null when it carries no seat state. */
export function checkFromAvailability(a: Availability): WatchCheck | null {
  if (!a.is_live || a.status === "UNKNOWN") return null;
  return { at: Date.now(), status: a.status, count: a.count, source: "live", note: a.source };
}

export type LiveResult = { availability: Availability | null; error: string | null; usage: LiveUsage | null };

/** Ask the server for one ticket's live status; also saves it to Seat Watch if followed. */
export async function checkLive(t: WatchTicket): Promise<LiveResult> {
  try {
    const res = await api.checkSeats([
      {
        train_number: t.train_number,
        journey_date: t.journey_date,
        from_code: t.from_code,
        to_code: t.to_code,
        travel_class: t.travel_class,
      },
    ]);
    const row = res.results[0];
    if (!row?.ok || !row.availability) {
      return { availability: null, error: row?.error ?? "No answer for this ticket.", usage: res.live_usage };
    }
    const check = checkFromAvailability(row.availability);
    if (check) recordWatchCheck(watchId(t), check);
    return { availability: row.availability, error: null, usage: res.live_usage };
  } catch (error) {
    return {
      availability: null,
      error: error instanceof ApiError ? `${error.message} ${error.hint ?? ""}`.trim() : "Could not check right now.",
      usage: null,
    };
  }
}

export function LiveAnswer({ result }: { result: LiveResult }) {
  const a = result.availability;
  return (
    <div role="status" className="mt-2 rounded-md bg-[#f6f8fb] px-3 py-2 text-[13px] text-wims-text">
      {a ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {a.status !== "UNKNOWN" ? (
              <StatusPill status={a.status} availability={a} size="sm" />
            ) : (
              <span className="font-medium">Status unknown</span>
            )}
            <span className="text-xs text-wims-muted">
              {a.source} · {formatTime(a.observed_at)}
            </span>
          </div>
          {a.note && <p className="mt-1 text-xs text-wims-muted">{a.note}</p>}
        </>
      ) : (
        <p className="text-wims-late">{result.error}</p>
      )}
      {result.usage?.remaining_this_month != null && (
        <p className="mt-1 text-[11px] text-wims-muted">
          {result.usage.remaining_this_month} of {result.usage.monthly_limit} free live checks left (last 30 days).
        </p>
      )}
    </div>
  );
}

/** "Check live seats" (when available) and "Track seats" for one ticket. */
export function TicketLiveActions({ ticket, trainName }: { ticket: Ticket; trainName: string }) {
  const live = useLiveChecks();
  const watches = useWatches();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<LiveResult | null>(null);
  if (ticket.kind !== "reserved") return null;
  const t = watchTicketFrom(ticket, trainName);
  const id = watchId(t);
  const watching = watches.some((w) => w.id === id);

  return (
    <>
      {live && (
        <button
          type="button"
          disabled={busy}
          onClick={async (e) => {
            e.stopPropagation();
            setBusy(true);
            setResult(await checkLive(t));
            setBusy(false);
          }}
          className="inline-flex items-center gap-1.5 rounded border border-wims-blue px-3 py-1.5 text-xs font-medium text-wims-blue hover:bg-[#eaf3fb] disabled:opacity-60"
        >
          {busy ? <Spinner className="h-3.5 w-3.5" /> : <Radio className="h-3.5 w-3.5" />}
          Check live seats
        </button>
      )}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          if (watching) {
            removeWatch(id);
          } else {
            const first = result?.availability ? checkFromAvailability(result.availability) : null;
            addWatch(t, first ?? undefined);
          }
        }}
        aria-pressed={watching}
        className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium ${
          watching ? "bg-[#e5f5e3] text-wims-green-dark" : "text-wims-blue hover:bg-[#eaf3fb]"
        }`}
      >
        {watching ? <BellRing className="h-3.5 w-3.5" /> : <BellPlus className="h-3.5 w-3.5" />}
        {watching ? "Tracking" : "Track seats"}
      </button>
      {watching && (
        <Link href="/watch" onClick={(e) => e.stopPropagation()} className="text-xs font-medium text-wims-blue underline">
          Seat Watch
        </Link>
      )}
      {result && (
        <div className="basis-full">
          <LiveAnswer result={result} />
        </div>
      )}
    </>
  );
}
