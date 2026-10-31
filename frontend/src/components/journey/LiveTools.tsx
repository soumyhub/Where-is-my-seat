"use client";

import { AlarmClock, IndianRupee, MapPin, TrainFront, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { api, ApiError } from "@/lib/api";
import { formatRupees } from "@/lib/format";
import type { Alerts, Coaches, Leg, LiveFare, LiveTrain, LiveUsage, Punctuality } from "@/lib/types";

import { Spinner, TrainBadge } from "../ui";

/* Live information from RailRadar's free plan (your own key). Nothing loads by itself:
   each button asks once, and answers are reused for a while, so the free requests last. */

type Tool = "where" | "fare" | "coaches" | "punctual" | "alerts";
type Envelope = { source: string; fetched_at: string; cached: boolean; requests_left: number };
type State = { loading: boolean; error: string | null; result: (Envelope & { data: unknown }) | null };

let usageOnce: Promise<LiveUsage | null> | null = null;

/** Whether live tools are set up on the server (asked once per page load). */
export function useLiveTools(): LiveUsage | null {
  const [usage, setUsage] = useState<LiveUsage | null>(null);
  useEffect(() => {
    let alive = true;
    usageOnce ??= api.liveUsage().catch(() => null);
    void usageOnce.then((u) => alive && setUsage(u));
    return () => {
      alive = false;
    };
  }, []);
  return usage;
}

const TOOLS: { id: Tool; label: string; icon: ReactNode }[] = [
  { id: "where", label: "Where is it now?", icon: <TrainFront className="h-3.5 w-3.5" /> },
  { id: "fare", label: "Exact fare", icon: <IndianRupee className="h-3.5 w-3.5" /> },
  { id: "coaches", label: "Coach position", icon: <MapPin className="h-3.5 w-3.5" /> },
  { id: "punctual", label: "Usually late?", icon: <AlarmClock className="h-3.5 w-3.5" /> },
  { id: "alerts", label: "Cancelled / diverted?", icon: <TriangleAlert className="h-3.5 w-3.5" /> },
];

function late(minutes: number | null | undefined): string {
  if (minutes == null) return "—";
  if (minutes <= 0) return "on time";
  return minutes >= 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60} min late` : `${minutes} min late`;
}

function WhereNow({ d }: { d: LiveTrain["data"] }) {
  const notStarted = /not.?started|yet|scheduled/i.test(d.status ?? "") || d.tracking_mode === "none";
  const first = d.halts[0];
  return (
    <div>
      <p className="text-sm font-medium text-wims-text">
        {notStarted
          ? `Not started yet${first?.scheduled_departure ? ` — leaves ${first.name ?? first.code} at ${first.scheduled_departure}` : ""}.`
          : d.status === "completed"
            ? "Reached its last station."
            : `${d.current?.status === "departed" ? "Left" : "At / near"} ${d.current?.name ?? d.previous_halt?.name ?? "—"}`}
        {d.delay_minutes != null && !notStarted && (
          <span className={d.delay_minutes > 15 ? "text-wims-late" : "text-wims-green-dark"}> · {late(d.delay_minutes)}</span>
        )}
      </p>
      {notStarted && (
        <p className="text-[13px] text-wims-muted">Times below are RailRadar&apos;s expected times, not actual.</p>
      )}
      {d.next_halt?.name && d.status !== "completed" && !notStarted && (
        <p className="text-[13px] text-wims-muted">
          Next halt: {d.next_halt.name}
          {d.current?.speed_kmh ? ` · ${d.current.speed_kmh} km/h` : ""}
        </p>
      )}
      {d.alerts.map((a) => (
        <p key={a} className="mt-1 text-[13px] text-[#9a5a00]">
          {a}
        </p>
      ))}
      {d.halts.length > 0 && (
        <div className="mt-2 max-h-64 overflow-auto rounded border border-wims-hairline">
          <table className="w-full text-[12.5px] tabular">
            <thead className="sticky top-0 bg-[#f6f8fb] text-left text-[11px] uppercase text-wims-muted">
              <tr>
                <th className="px-2 py-1">Station</th>
                <th className="px-2 py-1">Timetable</th>
                <th className="px-2 py-1">Actual / expected</th>
                <th className="px-2 py-1">PF</th>
              </tr>
            </thead>
            <tbody>
              {d.halts.map((h, i) => (
                <tr key={`${h.code}-${i}`} className="border-t border-wims-hairline">
                  <td className="px-2 py-1">{h.name ?? h.code}</td>
                  <td className="px-2 py-1">{h.scheduled_arrival ?? h.scheduled_departure ?? "—"}</td>
                  <td className={`px-2 py-1 ${(h.delay_minutes ?? 0) > 15 ? "text-wims-late" : ""}`}>
                    {h.actual_arrival ?? h.actual_departure ?? "—"}
                    {h.delay_minutes ? ` (+${h.delay_minutes})` : ""}
                    {(notStarted || /upcoming|scheduled|expected/i.test(h.status ?? "")) && (
                      <span className="ml-1 text-[10.5px] text-wims-muted">exp.</span>
                    )}
                  </td>
                  <td className="px-2 py-1">{h.platform ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function FareView({ d }: { d: LiveFare["data"] }) {
  return (
    <div>
      <p className="text-sm text-wims-text">
        <span className="text-lg font-medium">{d.total != null ? formatRupees(d.total) : "—"}</span> per person · {d.class} ·
        General quota{d.distance_km ? ` · ${d.distance_km} km` : ""}
      </p>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {Object.entries(d.parts).map(([k, v]) => (
          <span key={k} className="rounded-sm bg-[#f1f4f8] px-1.5 py-0.5 text-[11.5px] text-wims-text">
            {k} {formatRupees(v)}
          </span>
        ))}
      </div>
      <p className="mt-1 text-[11.5px] text-wims-muted">Dynamic-fare trains can change price — IRCTC shows the final fare.</p>
    </div>
  );
}

function CoachView({ d, cls }: { d: Coaches["data"]; cls?: string }) {
  return (
    <div>
      <p className="text-sm text-wims-text">
        At {d.station.name ?? d.station.code}
        {d.station.platform ? ` · platform ${d.station.platform}` : ""}
        {d.reversal ? " · the train reverses here" : ""}
      </p>
      <div className="mt-2 flex gap-1 overflow-x-auto pb-1" aria-label="Coach order from the engine">
        {d.coaches.map((c, i) => (
          <span
            key={`${c.code}-${i}`}
            title={c.name ?? undefined}
            className={`shrink-0 rounded-sm px-1.5 py-1 text-[11px] font-medium tabular ${
              cls && c.class === cls ? "bg-wims-blue text-white" : "bg-[#f1f4f8] text-wims-text"
            }`}
          >
            {c.code}
          </span>
        ))}
      </div>
      <p className="text-[11.5px] text-wims-muted">
        Engine first. {cls ? `Your class (${cls}) is highlighted. ` : ""}Coach order can change — check the station display.
      </p>
    </div>
  );
}

function PunctualView({ d, from, to }: { d: Punctuality["data"]; from: string; to: string }) {
  const at = (code: string) => d.halts.find((h) => h.code === code);
  const board = at(from);
  const alight = at(to);
  return (
    <div className="text-sm text-wims-text">
      {d.on_time_percent == null && d.halts.length === 0 ? (
        <p>No delay history for this train yet.</p>
      ) : (
        <>
          <p>
            On time about <strong>{d.on_time_percent ?? "—"}%</strong> of runs · usually{" "}
            {late(d.average_arrival_delay)} on arrival
          </p>
          {(board || alight) && (
            <p className="text-[13px] text-wims-muted">
              {board && `Usually leaves ${board.name ?? from} ${late(board.departure_delay)}. `}
              {alight && `Usually reaches ${alight.name ?? to} ${late(alight.arrival_delay)}.`}
            </p>
          )}
          {d.worst?.name && (
            <p className="text-[13px] text-wims-muted">
              Most delay at {d.worst.name} ({late(d.worst.delay)}).
            </p>
          )}
        </>
      )}
    </div>
  );
}

function AlertsView({ d }: { d: Alerts["data"] }) {
  if (!d.items.length) {
    return <p className="text-sm text-wims-green-dark">No cancellation, diversion or reschedule reported for this train now.</p>;
  }
  return (
    <ul className="space-y-1">
      {d.items.map((a, i) => (
        <li key={i} className="text-sm text-wims-late">
          <span className="font-medium capitalize">{a.type?.replace("_", " ") ?? "Alert"}</span>
          {a.start_date ? ` (train of ${a.start_date})` : ""}: {a.message}
        </li>
      ))}
    </ul>
  );
}

function LegTools({ leg, cls }: { leg: Leg; cls?: string }) {
  const train = leg.train!;
  const from = leg.from_station.code;
  const to = leg.to_station.code;
  const [open, setOpen] = useState<Tool | null>(null);
  const [states, setStates] = useState<Partial<Record<Tool, State>>>({});
  const ticket = leg.tickets.find((t) => t.kind === "reserved");

  async function run(tool: Tool) {
    setOpen((cur) => (cur === tool ? null : tool));
    if (states[tool]?.result || states[tool]?.loading) return;
    setStates((s) => ({ ...s, [tool]: { loading: true, error: null, result: null } }));
    try {
      const result =
        tool === "where"
          ? await api.live.train(train.number, train.start_date)
          : tool === "fare"
            ? await api.live.fare({
                train: train.number,
                from,
                to,
                date: ticket?.journey_date ?? leg.depart_at.slice(0, 10),
                cls: ticket?.travel_class ?? cls ?? "SL",
              })
            : tool === "coaches"
              ? await api.live.coaches(train.number, from)
              : tool === "punctual"
                ? await api.live.punctuality(train.number)
                : await api.live.alerts(train.number);
      setStates((s) => ({ ...s, [tool]: { loading: false, error: null, result } }));
    } catch (e) {
      const msg = e instanceof ApiError ? `${e.message} ${e.hint ?? ""}`.trim() : "Could not load this right now.";
      setStates((s) => ({ ...s, [tool]: { loading: false, error: msg, result: null } }));
    }
  }

  const state = open ? states[open] : undefined;
  const r = state?.result;
  return (
    <div className="rounded-md border border-wims-hairline bg-white p-3">
      <div className="flex flex-wrap items-center gap-2">
        <TrainBadge number={train.number} />
        <span className="text-sm font-medium text-wims-text">{train.name}</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {TOOLS.filter((t) => t.id !== "fare" || ticket).map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              void run(t.id);
            }}
            aria-expanded={open === t.id}
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium ${
              open === t.id ? "border-wims-blue bg-wims-blue text-white" : "border-[#cfd8e3] text-wims-text hover:bg-[#eef3f8]"
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>
      {open && (
        <div className="mt-3 rounded-md bg-[#f6f8fb] p-3" role="status">
          {state?.loading && <Spinner className="h-5 w-5" />}
          {state?.error && <p className="text-[13px] text-wims-late">{state.error}</p>}
          {r && open === "where" && <WhereNow d={r.data as LiveTrain["data"]} />}
          {r && open === "fare" && <FareView d={r.data as LiveFare["data"]} />}
          {r && open === "coaches" && <CoachView d={r.data as Coaches["data"]} cls={ticket?.travel_class} />}
          {r && open === "punctual" && <PunctualView d={r.data as Punctuality["data"]} from={from} to={to} />}
          {r && open === "alerts" && <AlertsView d={r.data as Alerts["data"]} />}
          {r && (
            <p className="mt-2 text-[11px] text-wims-muted">
              {r.source} · {r.fetched_at.slice(11, 16)}
              {r.cached ? " · saved answer, no request used" : ""} · {r.requests_left} free requests left (30 days)
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Live tools for every train leg of a journey, shown only when the server has a RailRadar key. */
export function LiveTools({ legs, travelClass }: { legs: Leg[]; travelClass?: string }) {
  const usage = useLiveTools();
  if (!usage?.tools) return null;
  const trains = legs.filter((l) => l.kind === "train" && l.train && !l.train.simulated);
  if (!trains.length) return null;
  return (
    <div className="space-y-2">
      <p className="text-[12.5px] text-wims-muted">
        From RailRadar, a third party (not IRCTC or NTES), with your free key — each new answer uses one of{" "}
        {usage.requests_left ?? "your"} requests left this 30-day period.{" "}
        <Link href={`/station?code=${legs[0].from_station.code}`} className="font-medium text-wims-blue underline">
          Live board at {legs[0].from_station.name}
        </Link>
      </p>
      {trains.map((leg, i) => (
        <LegTools key={`${leg.train!.number}-${i}`} leg={leg} cls={travelClass} />
      ))}
    </div>
  );
}
