"use client";

import { Bus, ChevronDown, ExternalLink, Lightbulb, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { CATEGORY_LABELS, dayDelta, formatDay, formatDuration, formatRupees, formatTime } from "@/lib/format";
import type { Itinerary } from "@/lib/types";

import { SaveButton, ShareButton } from "./Actions";
import { TicketCheck } from "./CheckOnIrctc";
import { LiveTools, useLiveTools } from "./LiveTools";
import { RouteMap } from "./RouteMap";
import { Timeline } from "./Timeline";

function Section({
  title,
  children,
  defaultOpen = true,
  count,
}: {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  count?: number;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="border-t border-wims-hairline">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-3 text-left text-[13px] font-medium uppercase tracking-wide text-wims-text"
      >
        {title}
        {count != null && <span className="rounded-full bg-[#eaf3fb] px-2 text-[11px] text-wims-blue">{count}</span>}
        <ChevronDown className={`ml-auto h-4 w-4 text-wims-muted transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </section>
  );
}

function LiveSection({ it }: { it: Itinerary }) {
  const usage = useLiveTools();
  if (!usage?.tools || !it.legs.some((l) => l.kind === "train" && !l.train?.simulated)) return null;
  return (
    <Section title="Live info (RailRadar)">
      <LiveTools legs={it.legs} />
    </Section>
  );
}

/** Everything about one option: what to check on IRCTC, plan B tickets, route and caveats. */
export function Details({
  it,
  originName,
  destinationName,
  showOpenLink = true,
  routeOpen = false,
  mapOpen = false,
}: {
  it: Itinerary;
  originName: string;
  destinationName: string;
  showOpenLink?: boolean;
  routeOpen?: boolean;
  mapOpen?: boolean;
}) {
  const days = dayDelta(it.depart_at, it.arrive_at);
  const tickets = it.legs.flatMap((leg) => leg.tickets.map((t) => ({ t, leg })));
  const roads = it.legs.filter((l) => l.kind === "road");
  const notes = [...it.warnings, ...it.tips];
  const trainNames = new Map(it.legs.flatMap((l) => (l.train ? [[l.train.number, l.train.name] as const] : [])));

  return (
    <div>
      <div className="px-4 py-4">
        <div className="flex flex-wrap gap-1">
          {it.categories.map((c) => (
            <span key={c} className="rounded-sm bg-[#eaf3fb] px-1.5 py-0.5 text-[11px] font-medium text-wims-blue">
              {CATEGORY_LABELS[c] ?? c}
            </span>
          ))}
        </div>
        <h2 className="mt-1.5 text-[17px] font-medium leading-snug text-wims-text">{it.headline}</h2>
        <p className="tabular mt-1 text-sm text-wims-text">
          {formatDay(it.depart_at)} · {formatTime(it.depart_at)} → {formatTime(it.arrive_at)}
          {days > 0 && <span className="text-wims-late"> (+{days})</span>} · {formatDuration(it.total_minutes)} ·{" "}
          {it.transfers === 0 ? "no change" : `${it.transfers} change${it.transfers > 1 ? "s" : ""}`} · ≈{" "}
          {formatRupees(it.cost_per_person)}/person
        </p>
        {it.why[0] && <p className="mt-1 text-[13px] text-wims-muted">{it.why[0]}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-1">
          <SaveButton it={it} originName={originName} destinationName={destinationName} />
          <ShareButton it={it} />
          {showOpenLink && (
            <Link
              href={`/journey?id=${encodeURIComponent(it.id)}`}
              className="inline-flex min-h-10 items-center gap-1 rounded px-2.5 text-[13px] font-medium text-wims-blue hover:bg-[#eaf3fb]"
            >
              Full page <ExternalLink className="h-3.5 w-3.5" />
            </Link>
          )}
        </div>
      </div>

      <Section title={tickets.length > 1 ? "Tickets to check on IRCTC" : "Check this ticket on IRCTC"} count={tickets.length}>
        <div className="space-y-2">
          {tickets.map(({ t, leg }, i) => (
            <TicketCheck
              key={`${t.train_number}-${t.from_station.code}-${i}`}
              ticket={t}
              simulatedTrain={leg.train?.simulated}
              trainName={leg.train?.name}
            />
          ))}
          {roads.map((leg, i) => (
            <p key={`road-${i}`} className="flex items-start gap-2 rounded-md bg-[#f6f8fb] px-3 py-2 text-[13px] text-wims-text">
              <Bus className="mt-0.5 h-4 w-4 shrink-0 text-wims-muted" aria-hidden />
              {leg.from_station.name} → {leg.to_station.name} by {leg.road?.mode.toLowerCase()}, about{" "}
              {formatDuration(leg.duration_minutes)} (≈ {formatRupees(leg.cost_per_person)}). Arrange it yourself.
            </p>
          ))}
          {it.booking_tip && <p className="text-[13px] text-wims-muted">{it.booking_tip}</p>}
        </div>
      </Section>

      {it.ideas.length > 0 && (
        <Section title="If this train is full, also check" count={it.ideas.length}>
          <ol className="space-y-3">
            {it.ideas.map((idea, i) => (
              <li key={idea.strategy} className="rounded-md border border-dashed border-[#b7cbe0] bg-[#f8fbff] p-3">
                <p className="text-sm font-medium text-wims-text">
                  {i + 1}. {idea.title}
                </p>
                <p className="mt-0.5 text-[13px] text-wims-muted">{idea.detail}</p>
                <div className="mt-2 space-y-2">
                  {idea.tickets.map((t, k) => (
                    <TicketCheck key={k} ticket={t} trainName={trainNames.get(t.train_number)} />
                  ))}
                </div>
              </li>
            ))}
          </ol>
        </Section>
      )}

      <LiveSection it={it} />

      {it.id && (
        <Section title="Map" defaultOpen={mapOpen}>
          <RouteMap journeyId={it.id} />
        </Section>
      )}

      <Section title="Route & stops" defaultOpen={routeOpen}>
        <Timeline it={it} />
        {it.fits.length > 0 && (
          <ul className="mt-3 space-y-1 text-[13px] text-wims-muted">
            {it.fits.map((f) => (
              <li key={f}>• {f}</li>
            ))}
          </ul>
        )}
      </Section>

      {notes.length > 0 && (
        <Section title="Good to know" count={notes.length} defaultOpen={false}>
          <ul className="space-y-1.5">
            {it.warnings.map((w) => (
              <li key={w} className="flex gap-2 text-[13px] text-[#5c3d00]">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-[#d48a00]" aria-hidden /> {w}
              </li>
            ))}
            {it.tips.map((w) => (
              <li key={w} className="flex gap-2 text-[13px] text-wims-text">
                <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-[#d4a000]" aria-hidden /> {w}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
