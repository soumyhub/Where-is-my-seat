"use client";

import { RadioTower } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { PAGE } from "@/lib/layout";
import type { Place, StationBoard } from "@/lib/types";

import { useLiveTools } from "../journey/LiveTools";
import { StationInput } from "../search/StationInput";
import { Card, Spinner, TrainBadge } from "../ui";

/* Trains due at a station in the next few hours, from RailRadar's free plan (own key). */

const STATE: Record<string, { label: string; tone: string }> = {
  "at-station": { label: "At platform", tone: "bg-[#e5f5e3] text-[#1e7b25]" },
  upcoming: { label: "Coming", tone: "bg-[#eaf3fb] text-wims-blue" },
  departed: { label: "Left", tone: "bg-[#f1f1f1] text-wims-muted" },
  scheduled: { label: "Scheduled", tone: "bg-[#f1f4f8] text-wims-text" },
};

export function StationBoardView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const code = (params.get("code") ?? "").toUpperCase();
  const hours = Number(params.get("hours") ?? 2) || 2;
  const usage = useLiveTools();
  const [place, setPlace] = useState<Place | null>(null);
  const [state, setState] = useState<{ key: string; board: StationBoard | null; error: string | null } | null>(null);
  const key = `${code}|${hours}`;

  useEffect(() => {
    if (!code || !usage?.tools) return;
    let alive = true;
    api.live
      .station(code, hours)
      .then((board) => alive && setState({ key, board, error: null }))
      .catch((e) => alive && setState({ key, board: null, error: e instanceof ApiError ? `${e.message} ${e.hint ?? ""}` : "Could not load the board." }));
    return () => {
      alive = false;
    };
  }, [code, hours, key, usage?.tools]);

  const show = (c: string, h: number) => router.push(`${pathname}?code=${encodeURIComponent(c)}&hours=${h}`);
  const current = state?.key === key ? state : null;
  const board = current?.board;

  return (
    <main className={`${PAGE} py-6`}>
      <div className="mx-auto max-w-4xl">
        <h1 className="flex items-center gap-2 text-2xl font-medium text-wims-text">
          <RadioTower className="h-6 w-6 text-wims-blue" /> Live station board
        </h1>
        <p className="mt-1 text-[15px] text-wims-muted">Trains due at a station in the next few hours, with platform and delay.</p>

        {usage && !usage.tools ? (
          <Card className="mt-4 p-4 text-sm text-wims-text">
            Live boards need your own free RailRadar key.{" "}
            <Link href="/about#live" className="font-medium text-wims-blue underline">
              How to set it up
            </Link>
          </Card>
        ) : (
          <Card className="mt-4 p-4">
            <form
              className="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end"
              onSubmit={(e) => {
                e.preventDefault();
                const c = place?.kind === "station" ? place.code : place?.codes[0];
                if (c) show(c, hours);
              }}
            >
              <div className="min-w-0 rounded-md border border-[#cfd8e3] px-3">
                <StationInput label="Station" value={place} onChange={setPlace} placeholder={code || "Station, e.g. New Delhi"} />
              </div>
              <label className="text-[11px] font-medium uppercase tracking-wider text-wims-muted">
                Next
                <select
                  value={hours}
                  onChange={(e) => code && show(code, Number(e.target.value))}
                  className="mt-1 block h-11 rounded-md border border-[#cfd8e3] bg-white px-2 text-sm text-wims-text"
                >
                  {[2, 4, 8].map((h) => (
                    <option key={h} value={h}>
                      {h} hours
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="submit"
                disabled={!place}
                className="h-11 rounded-md bg-wims-green px-5 text-sm font-medium text-white hover:bg-wims-green-dark disabled:opacity-50"
              >
                Show board
              </button>
            </form>
            <p className="mt-2 text-[11.5px] text-wims-muted">
              Each new board uses one of your free RailRadar requests
              {(board?.requests_left ?? usage?.requests_left) != null
                ? ` (${board?.requests_left ?? usage?.requests_left} left this 30-day period)`
                : ""}
              ; the same board is reused
              for 2 minutes.
            </p>
          </Card>
        )}

        {code && usage?.tools && (
          <div className="mt-4">
            {!current && <Spinner />}
            {current?.error && <p className="text-sm text-wims-late">{current.error}</p>}
            {board && (
              <Card className="overflow-hidden">
                <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-wims-hairline px-4 py-3">
                  <h2 className="font-medium text-wims-text">
                    {board.data.station.name} ({board.data.station.code})
                  </h2>
                  <span className="text-xs text-wims-muted">
                    {board.data.trains.length} trains · {board.source} · {board.fetched_at.slice(11, 16)}
                    {board.cached ? " (saved)" : ""}
                  </span>
                </div>
                {board.data.trains.length === 0 ? (
                  <p className="px-4 py-6 text-sm text-wims-muted">No trains due in this window.</p>
                ) : (
                  <ul className="divide-y divide-wims-hairline">
                    {board.data.trains.map((t, i) => {
                      const st = STATE[t.state ?? ""] ?? STATE.scheduled;
                      const due = t.expected_departure ?? t.expected_arrival ?? t.departure ?? t.arrival;
                      return (
                        <li key={`${t.number}-${i}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5">
                          <span className="w-12 text-sm font-medium tabular text-wims-text">{due ?? "—"}</span>
                          {t.number && <TrainBadge number={t.number} />}
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm text-wims-text">{t.name}</span>
                            <span className="block text-xs text-wims-muted">
                              {t.from} → {t.to}
                              {t.type ? ` · ${t.type}` : ""}
                            </span>
                          </span>
                          <span className="text-xs text-wims-text">PF {t.platform ?? "—"}</span>
                          <span className={`text-xs ${(t.delay_minutes ?? 0) > 15 ? "text-wims-late" : "text-wims-green-dark"}`}>
                            {t.delay_minutes ? `+${t.delay_minutes} min` : "on time"}
                          </span>
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${st.tone}`}>{st.label}</span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </Card>
            )}
          </div>
        )}
        <p className="mt-4 text-xs text-wims-muted">
          From RailRadar, an independent third party (not NTES or IRCTC). Always check the station display before boarding.
        </p>
      </div>
    </main>
  );
}
