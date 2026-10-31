"use client";

import { Bookmark, BookmarkCheck, Check, MessageCircle, Printer, Share2 } from "lucide-react";
import { useState } from "react";

import { formatDay, formatDuration, formatTime } from "@/lib/format";
import { isSaved, removeTrip, saveTrip, useSavedTrips } from "@/lib/storage";
import type { Itinerary } from "@/lib/types";

export function journeyUrl(id: string): string {
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  return `${origin}/journey?id=${encodeURIComponent(id)}`;
}

export function shareText(it: Itinerary): string {
  const first = it.legs[0];
  const last = it.legs[it.legs.length - 1];
  const trains = it.legs
    .filter((l) => l.train)
    .map((l) => `${l.train!.number} ${l.from_station.code}→${l.to_station.code}`)
    .join(", ");
  return [
    it.headline,
    `${formatDay(it.depart_at)} ${formatTime(it.depart_at)} ${first.from_station.name} → ${formatTime(it.arrive_at)} ${last.to_station.name} (${formatDuration(it.total_minutes)})`,
    `Trains: ${trains}`,
    `Status: ${it.overall_status.toLowerCase()}${it.contains_simulated ? " — SIMULATED demo data, not live" : ""}`,
  ].join("\n");
}

const button =
  "inline-flex min-h-10 items-center gap-1.5 rounded px-2.5 text-[13px] font-medium text-wims-blue hover:bg-[#eaf3fb]";

export function SaveButton({ it, originName, destinationName }: { it: Itinerary; originName: string; destinationName: string }) {
  const trips = useSavedTrips();
  const saved = isSaved(trips, it.id);
  const [failed, setFailed] = useState(false);
  return (
    <button
      type="button"
      className={button}
      aria-pressed={saved}
      onClick={() => {
        const ok = saved
          ? removeTrip(it.id)
          : saveTrip({
              id: it.id,
              itinerary: it,
              checked_at: firstObservation(it) ?? it.depart_at,
              origin_name: originName,
              destination_name: destinationName,
            });
        setFailed(!ok);
      }}
    >
      {saved ? <BookmarkCheck className="h-4 w-4 text-wims-green-dark" /> : <Bookmark className="h-4 w-4" />}
      {failed ? "Storage blocked" : saved ? "Saved" : "Save"}
    </button>
  );
}

export function firstObservation(it: Itinerary): string | null {
  for (const leg of it.legs) for (const t of leg.tickets) if (t.availability) return t.availability.observed_at;
  return null;
}

export function ShareButton({ it }: { it: Itinerary }) {
  const [copied, setCopied] = useState(false);
  async function share() {
    const url = journeyUrl(it.id);
    const text = shareText(it);
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ title: "Where is my Seat", text, url });
        return;
      } catch {
        /* cancelled or unsupported: fall back to copying */
      }
    }
    try {
      await navigator.clipboard.writeText(`${text}\n${url}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("Copy this link", url);
    }
  }
  return (
    <button type="button" className={button} onClick={share}>
      {copied ? <Check className="h-4 w-4 text-wims-green-dark" /> : <Share2 className="h-4 w-4" />}
      {copied ? "Copied" : "Share"}
    </button>
  );
}

export function WhatsAppLink({ it }: { it: Itinerary }) {
  return (
    <a
      className={button}
      href={`https://wa.me/?text=${encodeURIComponent(`${shareText(it)}\n${journeyUrl(it.id)}`)}`}
      target="_blank"
      rel="noopener noreferrer"
    >
      <MessageCircle className="h-4 w-4" /> WhatsApp
    </a>
  );
}

export function PrintButton() {
  return (
    <button type="button" className={button} onClick={() => window.print()}>
      <Printer className="h-4 w-4" /> Print
    </button>
  );
}
