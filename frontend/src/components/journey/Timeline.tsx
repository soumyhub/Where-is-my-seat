import { Bus, Repeat, TrainFront } from "lucide-react";
import { Fragment } from "react";

import { CLASS_NAMES, dayDelta, formatDay, formatDuration, formatTime } from "@/lib/format";
import type { Itinerary, Leg } from "@/lib/types";

import { StatusPill, TrainBadge } from "../ui";

/* Vertical stop list in the style of the WIMT live-status screen: arrival times on the
   left, the blue line with station dots in the middle, departures on the right. */

function DayRow({ date, day }: { date: string; day: number }) {
  return (
    <div className="grid grid-cols-[64px_28px_1fr_64px] bg-[#2b2b2b] text-[12px] text-white">
      <span className="py-1.5 pl-3">Arrival</span>
      <span />
      <span className="py-1.5 font-medium">
        Day {day} · {formatDay(date)}
      </span>
      <span className="py-1.5 pr-3 text-right">Departure</span>
    </div>
  );
}

function StopRow({
  time,
  depart,
  name,
  code,
  sub,
  marker,
  emphasize,
  road = false,
}: {
  time: string | null;
  depart: string | null;
  name: string;
  code: string;
  sub?: string;
  marker: "board" | "alight" | "halt";
  emphasize?: boolean;
  road?: boolean;
}) {
  const dot =
    marker === "board"
      ? "h-3.5 w-3.5 bg-wims-origin ring-2 ring-white"
      : marker === "alight"
        ? "h-3.5 w-3.5 bg-wims-dest ring-2 ring-white"
        : "h-2 w-2 bg-[#9cc0f0]";
  return (
    <div className="grid min-h-[52px] grid-cols-[64px_28px_1fr_64px] items-start">
      <span className="tabular pt-2 pr-1 text-right text-[13px] text-wims-text">{time ? formatTime(time) : ""}</span>
      <span className="relative flex h-full justify-center">
        <span className={`absolute inset-y-0 ${road ? "w-0 border-l-[3px] border-dashed border-[#9e9e9e]" : "w-[5px] bg-wims-line"}`} />
        <span className={`relative mt-3 rounded-full ${dot}`} />
      </span>
      <span className="min-w-0 py-2 pl-1">
        <span className={`block truncate text-[14px] ${emphasize ? "font-medium" : ""} text-wims-text`}>{name}</span>
        <span className="block text-[11.5px] text-wims-muted">
          {code}
          {sub ? ` · ${sub}` : ""}
        </span>
      </span>
      <span className="tabular pt-2 pr-3 text-right text-[13px] text-wims-text">{depart ? formatTime(depart) : ""}</span>
    </div>
  );
}

function TrainHeader({ leg }: { leg: Leg }) {
  const t = leg.tickets[0];
  const cls = t?.travel_class;
  return (
    <div className="flex flex-wrap items-center gap-2 bg-wims-blue px-3 py-2 text-white">
      <TrainFront className="h-4 w-4" aria-hidden />
      <TrainBadge number={leg.train!.number} simulated={leg.train!.simulated} />
      <span className="text-sm font-medium">{leg.train!.name}</span>
      <span className="text-xs text-white/75">
        {leg.train!.category} · runs {leg.train!.runs_on.toLowerCase()} · {cls === "UR" ? "Unreserved" : `${cls} ${CLASS_NAMES[cls ?? ""] ?? ""}`}
      </span>
      <span className="ml-auto flex flex-wrap gap-1">
        {leg.tickets.map((tk, i) => (
          <StatusPill key={i} status={tk.kind === "unreserved" ? "UNRESERVED" : (tk.availability?.status ?? "UNKNOWN")} availability={tk.availability} size="sm" />
        ))}
      </span>
    </div>
  );
}

function Connection({ minutes, tight, text }: { minutes: number; tight: boolean; text: string }) {
  return (
    <div className="grid grid-cols-[64px_28px_1fr_64px]">
      <span />
      <span className="flex justify-center">
        <span className="w-[5px] bg-[repeating-linear-gradient(to_bottom,#325fbc_0_6px,transparent_6px_10px)]" />
      </span>
      <div className="py-2 pr-3">
        <div className={`inline-flex items-center gap-2 rounded px-2.5 py-1.5 text-[13px] text-white ${tight ? "bg-[#d48a00]" : "bg-wims-green"}`}>
          <Repeat className="h-4 w-4" aria-hidden />
          <span>
            {text} · {formatDuration(minutes)}
          </span>
        </div>
      </div>
      <span />
    </div>
  );
}

function RoadLeg({ leg }: { leg: Leg }) {
  const label =
    leg.purpose === "feeder" ? "Get to the boarding station" : leg.purpose === "onward" ? "Continue to your destination" : "Change stations";
  return (
    <>
      <StopRow time={null} depart={leg.depart_at} name={leg.from_station.name} code={leg.from_station.code} marker="halt" emphasize road />
      <div className="grid grid-cols-[64px_28px_1fr_64px]">
        <span />
        <span className="flex justify-center">
          <span className="w-0 border-l-[3px] border-dashed border-[#9e9e9e]" />
        </span>
        <div className="py-2 pr-3">
          <div className="inline-flex items-start gap-2 rounded border border-dashed border-[#bdbdbd] bg-white px-2.5 py-1.5 text-[13px] text-wims-text">
            <Bus className="mt-0.5 h-4 w-4 shrink-0 text-wims-muted" aria-hidden />
            <span>
              {label}: {leg.road?.mode.toLowerCase()} · about {formatDuration(leg.duration_minutes)} · {leg.distance_km} km
              <span className="block text-[11.5px] text-wims-muted">Estimate — arrange it yourself; not booked here.</span>
            </span>
          </div>
        </div>
        <span />
      </div>
      <StopRow time={leg.arrive_at} depart={null} name={leg.to_station.name} code={leg.to_station.code} marker="halt" emphasize road />
    </>
  );
}

type Stop = Leg["stops"][number];
type Row =
  | { type: "day"; date: string; day: number }
  | { type: "connection"; minutes: number; station: string }
  | { type: "road"; leg: Leg }
  | { type: "train"; leg: Leg }
  | { type: "stop"; leg: Leg; stop: Stop };

/* Flatten the itinerary into display rows, inserting a day header whenever the date changes. */
function buildRows(it: Itinerary): Row[] {
  const rows: Row[] = [];
  const start = it.depart_at.slice(0, 10);
  let current = "";
  const markDay = (iso: string | null) => {
    if (!iso) return;
    const date = iso.slice(0, 10);
    if (date !== current) {
      current = date;
      rows.push({ type: "day", date, day: dayDelta(start, date) + 1 });
    }
  };
  it.legs.forEach((leg, i) => {
    const prev = i > 0 ? it.legs[i - 1] : null;
    if (prev && prev.kind === "train" && leg.kind === "train") {
      rows.push({ type: "connection", minutes: leg.buffer_before_minutes ?? 0, station: leg.from_station.name });
    }
    markDay(leg.depart_at);
    if (leg.kind === "road") {
      rows.push({ type: "road", leg });
      return;
    }
    rows.push({ type: "train", leg });
    for (const stop of leg.stops) {
      markDay(stop.arr ?? stop.dep);
      rows.push({ type: "stop", leg, stop });
    }
  });
  return rows;
}

function TrainStop({ leg, stop }: { leg: Leg; stop: Stop }) {
  const marker = stop.role;
  const splitAt = leg.tickets.length === 2 && leg.tickets[0].to_station.code === stop.code;
  const role = marker === "board" ? " · board here" : marker === "alight" ? " · get off here" : "";
  return (
    <StopRow
      time={marker === "board" ? null : stop.arr}
      depart={marker === "alight" ? null : stop.dep}
      name={stop.name}
      code={stop.code}
      sub={`${stop.km} km${splitAt ? " · switch to your 2nd ticket here" : ""}${role}`}
      marker={splitAt ? "board" : marker}
      emphasize={marker !== "halt" || splitAt}
    />
  );
}

export function Timeline({ it }: { it: Itinerary }) {
  const rows = buildRows(it);
  return (
    <div className="overflow-hidden rounded-[3px] bg-[#eeeeee] shadow-[0_1px_2px_rgba(0,0,0,0.14)]">
      {rows.map((row, i) => (
        <Fragment key={i}>
          {row.type === "day" && <DayRow date={row.date} day={row.day} />}
          {row.type === "connection" && (
            <Connection
              minutes={row.minutes}
              tight={row.minutes < 45}
              text={row.minutes < 45 ? `Tight change at ${row.station}` : `Change trains at ${row.station}`}
            />
          )}
          {row.type === "road" && <RoadLeg leg={row.leg} />}
          {row.type === "train" && <TrainHeader leg={row.leg} />}
          {row.type === "stop" && <TrainStop leg={row.leg} stop={row.stop} />}
        </Fragment>
      ))}
    </div>
  );
}
