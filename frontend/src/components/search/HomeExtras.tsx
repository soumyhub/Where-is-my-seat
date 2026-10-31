"use client";

import { ArrowRight, History, X } from "lucide-react";
import Link from "next/link";

import { addDays, formatDay } from "@/lib/format";
import { useMeta } from "@/lib/hooks";
import { DEFAULT_REQUEST, toQuery } from "@/lib/query";
import { clearRecent, useRecentSearches } from "@/lib/storage";
import { SearchRequestSchema } from "@/lib/types";

import { Card } from "../ui";

export function PopularRoutes() {
  const { data } = useMeta();
  if (!data?.samples.length) return null;
  const day = addDays(data.today, 1);
  return (
    <section aria-labelledby="popular-heading" className="flex flex-wrap items-center gap-2">
      <h2 id="popular-heading" className="mr-1 text-sm font-medium text-white/85">
        Popular:
      </h2>
      {data.samples.map((sample) => {
        const parsed = SearchRequestSchema.safeParse({ ...DEFAULT_REQUEST, ...sample.request, date: day });
        if (!parsed.success) return null;
        return (
          <Link
            key={sample.id}
            href={`/results?${toQuery(parsed.data, { fromName: sample.from_name, toName: sample.to_name })}`}
            className="rounded-full border border-white/40 bg-white/10 px-3 py-1.5 text-[13px] font-medium text-white hover:bg-white/20"
            title={sample.description}
          >
            {sample.title}
          </Link>
        );
      })}
    </section>
  );
}

export function RecentSearches() {
  const recent = useRecentSearches();
  if (!recent.length) return null;
  return (
    <section aria-labelledby="recent-heading">
      <div className="mb-2 flex items-center justify-between">
        <h2 id="recent-heading" className="flex items-center gap-1.5 text-sm font-medium text-wims-text">
          <History className="h-4 w-4 text-wims-badge" aria-hidden /> Recent searches
        </h2>
        <button type="button" onClick={clearRecent} className="inline-flex items-center gap-1 text-xs text-wims-muted hover:text-wims-text">
          <X className="h-3.5 w-3.5" /> Clear
        </button>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {recent.map((r) => {
          const parsed = SearchRequestSchema.safeParse({ ...DEFAULT_REQUEST, ...r.request });
          if (!parsed.success) return null;
          return (
            <Link
              key={r.at}
              href={`/results?${toQuery(parsed.data, { fromName: r.fromName, toName: r.toName })}`}
              className="group flex items-center gap-3 rounded-[3px] bg-white px-4 py-3 shadow-[0_1px_2px_rgba(0,0,0,0.12)] hover:bg-[#f5f9fd]"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-wims-text">
                  {r.fromName} → {r.toName}
                </span>
                <span className="block text-xs text-wims-muted">
                  {formatDay(parsed.data.date)} · {parsed.data.travel_class} · {parsed.data.passengers} traveller
                  {parsed.data.passengers > 1 ? "s" : ""}
                </span>
              </span>
              <ArrowRight className="h-4 w-4 text-wims-badge transition-transform group-hover:translate-x-0.5" />
            </Link>
          );
        })}
      </div>
    </section>
  );
}

const STEPS = [
  { n: 1, title: "Search your route", text: "Pick where you start, where you're going and the date. City names cover every station there." },
  { n: 2, title: "See every train, plus a plan B", text: "All direct trains from the official timetable — and if yours is full, backup tickets and other routes." },
  { n: 3, title: "Check seats & book on IRCTC", text: "We show exactly what to enter on IRCTC. Seats there are live; we never book or take payments." },
];

export function HowItWorks() {
  return (
    <section aria-labelledby="how-heading">
      <h2 id="how-heading" className="mb-3 text-sm font-medium text-wims-text">
        How it works
      </h2>
      <div className="grid gap-3 md:grid-cols-3">
        {STEPS.map((s) => (
          <Card key={s.n} className="flex gap-3 p-4">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-wims-blue text-sm font-bold text-white">{s.n}</span>
            <div>
              <h3 className="text-[15px] font-medium text-wims-text">{s.title}</h3>
              <p className="mt-0.5 text-[13px] leading-snug text-wims-muted">{s.text}</p>
            </div>
          </Card>
        ))}
      </div>
    </section>
  );
}
