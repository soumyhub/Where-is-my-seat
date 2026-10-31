"use client";

import { ArrowRight, BookmarkX, Clock3, RefreshCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import { formatDay, formatDuration, formatRupees, formatTime, isStale, timeAgo } from "@/lib/format";
import { useHydrated, useNow } from "@/lib/hooks";
import { removeTrip, updateTrip, useSavedTrips, type SavedTrip } from "@/lib/storage";

import { Card, Spinner, StatusPill, TrainBadge } from "../ui";

function SavedRow({ trip, now }: { trip: SavedTrip; now: number }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const it = trip.itinerary;
  const stale = now > 0 && isStale(trip.checked_at, now);
  const before = it.overall_status;

  async function recheck() {
    setBusy(true);
    setMessage(null);
    try {
      const fresh = await api.journey(trip.id);
      updateTrip(trip.id, { itinerary: fresh.itinerary, checked_at: fresh.checked_at, departed: false, invalid_reason: undefined });
      setMessage(
        fresh.itinerary.overall_status === before
          ? "Re-checked: no change."
          : `Re-checked: status changed from ${before.toLowerCase()} to ${fresh.itinerary.overall_status.toLowerCase()}.`,
      );
    } catch (error) {
      if (error instanceof ApiError && error.code === "JOURNEY_DEPARTED") {
        updateTrip(trip.id, { departed: true });
        setMessage("This journey has already departed.");
      } else if (error instanceof ApiError && error.code === "JOURNEY_NO_LONGER_VALID") {
        updateTrip(trip.id, { invalid_reason: error.message });
        setMessage(error.message);
      } else {
        setMessage(error instanceof ApiError ? `${error.message} ${error.hint ?? ""}` : "Could not re-check right now.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="overflow-hidden">
      <div className="px-4 pt-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-xs text-wims-muted">
              {trip.origin_name} → {trip.destination_name} · {formatDay(it.depart_at)}
            </p>
            <h3 className="mt-0.5 font-medium leading-snug text-wims-text">{it.headline}</h3>
          </div>
          <StatusPill status={it.overall_status} />
        </div>
        <p className="tabular mt-1.5 text-sm text-wims-text">
          {formatTime(it.depart_at)} → {formatTime(it.arrive_at)} · {formatDuration(it.total_minutes)} · {formatRupees(it.cost_per_person)} /person
        </p>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {it.legs
            .filter((l) => l.train)
            .map((l, i) => (
              <TrainBadge key={i} number={l.train!.number} simulated={l.train!.simulated} />
            ))}
        </div>
        <p className={`mt-2 flex items-center gap-1.5 text-xs ${stale ? "text-[#9a5a00]" : "text-wims-muted"}`}>
          <Clock3 className="h-3.5 w-3.5" />
          Last checked {now ? timeAgo(trip.checked_at, now) : formatTime(trip.checked_at)}
          {stale && " — re-check before you book"}
        </p>
        {trip.departed && <p className="mt-1 text-xs font-medium text-wims-late">Departed — you can remove it.</p>}
        {trip.invalid_reason && <p className="mt-1 text-xs font-medium text-wims-late">No longer valid: {trip.invalid_reason}</p>}
        {message && (
          <p role="status" className="mt-1 text-xs text-wims-ink">
            {message}
          </p>
        )}
      </div>
      <div className="mt-2 flex items-center border-t border-wims-hairline px-1.5">
        <button
          type="button"
          onClick={recheck}
          disabled={busy}
          className="inline-flex min-h-11 items-center gap-1.5 px-2.5 text-[13px] font-medium uppercase tracking-wide text-wims-green-dark disabled:opacity-60"
        >
          {busy ? <Spinner className="h-4 w-4" /> : <RefreshCw className="h-4 w-4" />} Re-check
        </button>
        <button
          type="button"
          onClick={() => removeTrip(trip.id)}
          className="inline-flex min-h-11 items-center gap-1.5 px-2.5 text-[13px] font-medium uppercase tracking-wide text-wims-muted hover:text-wims-late"
        >
          <Trash2 className="h-4 w-4" /> Remove
        </button>
        <Link
          href={`/journey?id=${encodeURIComponent(trip.id)}`}
          className="ml-auto inline-flex min-h-11 items-center gap-1 px-2.5 text-[13px] font-medium uppercase tracking-wide text-wims-blue"
        >
          Open <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </Card>
  );
}

export function SavedTrips() {
  const trips = useSavedTrips();
  const now = useNow();
  const hydrated = useHydrated();
  return (
    <main className="mx-auto max-w-3xl space-y-4 px-4 py-4">
      <div>
        <h1 className="text-lg font-medium text-wims-text">Saved journeys</h1>
        <p className="text-sm text-wims-muted">
          Stored only in this browser. Nothing is monitored in the background — tap Re-check to confirm the train
          still runs, then check seats on IRCTC.
        </p>
      </div>
      {!hydrated ? (
        <Card className="h-40 animate-pulse" aria-hidden>
          <span className="sr-only">Loading saved journeys</span>
        </Card>
      ) : trips.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-8 text-center">
          <BookmarkX className="h-8 w-8 text-[#bdbdbd]" aria-hidden />
          <p className="font-medium text-wims-text">No saved journeys yet</p>
          <p className="text-sm text-wims-muted">Save an option from your search results to compare or re-check it later.</p>
          <Link href="/" className="mt-2 rounded bg-wims-green px-4 py-2 text-sm font-medium uppercase tracking-wide text-white">
            Find seats
          </Link>
        </Card>
      ) : (
        trips.map((trip) => <SavedRow key={trip.id} trip={trip} now={now} />)
      )}
    </main>
  );
}
