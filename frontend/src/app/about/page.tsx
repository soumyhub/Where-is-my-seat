import { CircleCheck, CircleX, Network, Radio, ShieldCheck } from "lucide-react";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { PAGE } from "@/lib/layout";

export const metadata: Metadata = { title: "How it works" };

function Block({ id, icon, title, children }: { id?: string; icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-28 rounded-[3px] bg-white p-5 shadow-[0_1px_2px_rgba(0,0,0,0.12)]">
      <h2 className="flex items-center gap-2 text-[17px] font-medium text-wims-text">
        {icon}
        {title}
      </h2>
      <div className="mt-2 space-y-2 text-[14px] leading-relaxed text-wims-text">{children}</div>
    </section>
  );
}

function List({ items, ok }: { items: string[]; ok: boolean }) {
  return (
    <ul className="space-y-1.5">
      {items.map((r) => (
        <li key={r} className="flex gap-2 text-[13.5px]">
          {ok ? (
            <CircleCheck className="mt-0.5 h-4 w-4 shrink-0 text-wims-green-dark" />
          ) : (
            <CircleX className="mt-0.5 h-4 w-4 shrink-0 text-wims-late" />
          )}
          {r}
        </li>
      ))}
    </ul>
  );
}

const REAL = [
  "3,202 trains with their real numbers, names, running days and classes — from Indian Railways' official 'Trains at a Glance 2026' timetable (Railway Board).",
  "Published arrival and departure times at each main halt, including overnight and multi-day journeys.",
  "8,718 stations you can search, with map coordinates. 804 of them have trains in the timetable, including 329 of the junctions on Wikipedia's list. From any other station we start at the nearest station with trains.",
  "Changes between trains always leave at least 30 minutes and never double back.",
];
const NOT_LIVE = [
  "Seat availability (Available / RAC / Waitlist) — check it on IRCTC with the details we show, or switch on free live checks (below).",
  "Running status and delays — check NTES or the IRCTC app on the day.",
  "Fares — estimates from a simple distance model; IRCTC shows the exact fare.",
  "Retimings after the timetable was published, smaller halts the timetable book does not list, and passenger / MEMU / DEMU trains (not in Trains at a Glance).",
  "Road, metro and bus legs — rough time and cost estimates.",
];

export default function AboutPage() {
  return (
    <main className={`${PAGE} py-6`}>
      <div className="mx-auto max-w-5xl space-y-4">
        <div>
          <h1 className="text-2xl font-medium text-wims-text">How Where is my Seat works</h1>
          <p className="mt-1 text-[15px] text-wims-muted">
            Search a route and you see every direct train from the official timetable. When your train is waitlisted, we
            show the backup tickets and other routes experienced travellers try — and exactly what to check on IRCTC.
          </p>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Block id="data" icon={<CircleCheck className="h-5 w-5 text-wims-green-dark" />} title="What is real">
            <List items={REAL} ok />
          </Block>
          <Block icon={<CircleX className="h-5 w-5 text-wims-late" />} title="What is not live (yet)">
            <List items={NOT_LIVE} ok={false} />
          </Block>
        </div>

        <Block icon={<Radio className="h-5 w-5 text-wims-badge" />} title="Why seats are not live here">
          <p>
            Indian Railways does not offer a free public API for seat availability. IRCTC and NTES data may only be used
            through authorised channels, and their terms forbid scraping or building a database from their sites — so this
            app does neither. Instead, every option tells you exactly which ticket to look up on IRCTC (train, from, to,
            date, class), with a copy button and a direct link.
          </p>
          <p className="text-[13.5px] text-wims-muted">
            For a large public service, the proper route is an IRCTC authorised partnership or a licensed data provider
            (both paid). The app labels every seat status with its source and time.
          </p>
        </Block>

        <Block id="live" icon={<Radio className="h-5 w-5 text-wims-green-dark" />} title="Live seat checks (optional, RailRadar)">
          <p>
            You can switch on live checks with your own key from RailRadar, an independent third party (not IRCTC).
            Their free Sandbox key does <strong>not</strong> include seat availability (checked 30 Oct 2026: RailRadar
            answers &ldquo;plan upgrade required&rdquo;); seats need their paid Developer plan (from ₹499/month). The app
            never uses more than 90 requests per 30 days, reuses every answer for 30 minutes and never spends checks while
            you search. RailRadar calls its seat data an availability forecast, so always confirm on IRCTC.
          </p>
          <ol className="list-decimal space-y-1 pl-5 text-[13.5px]">
            <li>
              Sign up yourself at{" "}
              <a href="https://railradar.in/developers" target="_blank" rel="noopener noreferrer" className="text-wims-blue underline">
                railradar.in/developers
              </a>{" "}
              and read their terms. Seats need a paid plan; with a free key the app tells you so and keeps using IRCTC
              links.
            </li>
            <li>
              Put the key in <code className="rounded bg-[#f1f4f8] px-1">backend/.env</code> as{" "}
              <code className="rounded bg-[#f1f4f8] px-1">WIMS_RAILRADAR_KEY=your-key</code> and restart the backend.
            </li>
            <li>
              Tickets then show <strong>Check live seats</strong>, and Seat Watch can re-check followed tickets every 6
              hours while it is open.
            </li>
          </ol>
          <p>
            What the free key <strong>does</strong> give you (journey details → &ldquo;Live info&rdquo;, and the Live station
            tab): where the train is now and how late, the exact fare with its breakdown, coach position on the
            platform, how late the train usually runs, cancellations / diversions / reschedules, and live
            arrival-departure boards for any station. Each new answer uses one free request; answers are reused for a
            while (2 minutes for running status and boards, a day for fares and coaches, a week for punctuality).
          </p>
          <p className="text-[13px] text-wims-muted">
            Without a paid key, Seat Watch still works at ₹0: check on IRCTC, note the status, and it shows how the
            waitlist moves.
          </p>
        </Block>

        <Block icon={<Network className="h-5 w-5 text-wims-badge" />} title="How we find your options">
          <ol className="list-decimal space-y-1 pl-5 text-[13.5px]">
            <li>All direct trains between every station of your two cities (e.g. all Delhi and all Mumbai stations).</li>
            <li>
              For each direct train, backup tickets to try if it is full: book further, book from the starting station,
              split into two tickets, or board at a nearby station.
            </li>
            <li>Other ways: one or two changes at a junction, starting from a nearby station, or ending near your destination.</li>
            <li>Only trains that really halt at a station are used, on the days they actually run.</li>
            <li>Results are ranked by journey time, changes, fare and how comfortable each connection is.</li>
          </ol>
        </Block>

        <Block icon={<ShieldCheck className="h-5 w-5 text-wims-green-dark" />} title="Rules we follow">
          <ul className="list-disc space-y-1 pl-5 text-[13.5px]">
            <li>No scraping of IRCTC or NTES, no CAPTCHA bypass, no automated booking, no payment details — ever.</li>
            <li>Separately booked tickets are not one protected journey; every such option says so.</li>
            <li>Unreserved tickets are only for General coaches — never for reserved coaches or berths.</li>
            <li>
              Saved journeys and Seat Watch stay in your browser. Seat Watch only checks while its page is open, and
              only for tickets you switched auto-check on.
            </li>
          </ul>
          <p className="text-[13px] text-wims-muted">
            Sources: Railway Board &ldquo;Trains at a Glance 2026&rdquo; (parsed by the open-source railways-mcp project,
            Apache-2.0), Wikipedia list of railway junction stations in India (CC BY-SA), Wikidata (CC0), the
            Indian-Railway-Data station directory (MIT), and railway lines and map tiles from © OpenStreetMap
            contributors (ODbL).
          </p>
        </Block>
      </div>
    </main>
  );
}
