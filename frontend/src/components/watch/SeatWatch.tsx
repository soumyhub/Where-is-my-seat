"use client";

import { BellRing, CalendarPlus, ExternalLink, Radio, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { CLASS_NAMES, formatFullDate, todayInIndia } from "@/lib/format";
import { useHydrated, useNow } from "@/lib/hooks";
import { PAGE } from "@/lib/layout";
import {
  loadWatches,
  recordWatchCheck,
  removeWatch,
  updateWatch,
  useWatches,
  type Watch,
  type WatchCheck,
} from "@/lib/storage";
import type { LiveUsage } from "@/lib/types";
import { reminderCalendar, statusLabel, watchTrend } from "@/lib/watch";

import { checkLive, LiveAnswer, useLiveChecks, type LiveResult } from "../journey/LiveSeats";
import { Card, Spinner, StatusPill, Toggle, TrainBadge } from "../ui";

const IRCTC = "https://www.irctc.co.in/nget/train-search";
const AUTO_EVERY_MS = 6 * 3_600_000; // auto-check a followed ticket at most every 6 hours
const AUTO_PER_VISIT = 3;

const MANUAL: { value: WatchCheck["status"]; label: string; needsNumber: boolean }[] = [
  { value: "CONFIRMED", label: "Available", needsNumber: true },
  { value: "RAC", label: "RAC", needsNumber: true },
  { value: "WAITLISTED", label: "Waitlist", needsNumber: true },
  { value: "UNAVAILABLE", label: "Regret", needsNumber: false },
];

function ago(at: number, now: number): string {
  const minutes = Math.round((now - at) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function lastLiveAt(w: Watch): number {
  return [...w.history].reverse().find((c) => c.source === "live")?.at ?? 0;
}

function NoteStatus({ watch }: { watch: Watch }) {
  const [status, setStatus] = useState<WatchCheck["status"]>("WAITLISTED");
  const [count, setCount] = useState("");
  const option = MANUAL.find((m) => m.value === status)!;
  const n = Number.parseInt(count, 10);
  const valid = !option.needsNumber || (Number.isFinite(n) && n >= 0 && n < 1000);
  return (
    <form
      className="mt-3 rounded-md border border-wims-hairline p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!valid) return;
        recordWatchCheck(watch.id, {
          at: Date.now(),
          status,
          count: option.needsNumber ? n : null,
          source: "you",
        });
        setCount("");
      }}
    >
      <p className="text-[13px] font-medium text-wims-text">What does IRCTC show now?</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <div className="flex overflow-hidden rounded border border-[#cfd8e3]" role="radiogroup" aria-label="Status on IRCTC">
          {MANUAL.map((m) => (
            <button
              key={m.value}
              type="button"
              role="radio"
              aria-checked={status === m.value}
              onClick={() => setStatus(m.value)}
              className={`px-2.5 py-1.5 text-xs font-medium ${
                status === m.value ? "bg-wims-blue text-white" : "bg-white text-wims-text hover:bg-[#eef3f8]"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
        {option.needsNumber && (
          <label className="flex items-center gap-1.5 text-xs text-wims-muted">
            {status === "CONFIRMED" ? "Seats" : "Number"}
            <input
              inputMode="numeric"
              pattern="[0-9]*"
              value={count}
              onChange={(e) => setCount(e.target.value.replace(/\D/g, "").slice(0, 3))}
              placeholder={status === "WAITLISTED" ? "e.g. 23" : "e.g. 12"}
              className="w-16 rounded border border-[#cfd8e3] px-2 py-1.5 text-sm text-wims-text"
              aria-label={status === "CONFIRMED" ? "Seats available" : `${option.label} number`}
            />
          </label>
        )}
        <button
          type="submit"
          disabled={!valid || (option.needsNumber && count === "")}
          className="rounded bg-wims-green px-3 py-1.5 text-xs font-medium text-white hover:bg-wims-green-dark disabled:opacity-50"
        >
          Save
        </button>
      </div>
    </form>
  );
}

function WatchCard({ watch, now, live }: { watch: Watch; now: number; live: boolean }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<LiveResult | null>(null);
  const last = watch.history[watch.history.length - 1];
  const past = now > 0 && watch.journey_date < todayInIndia(now);
  const trend = watchTrend(watch, now);
  const tone = { good: "text-wims-green-dark", bad: "text-wims-late", flat: "text-wims-text", none: "text-wims-muted" }[trend.tone];
  const details = `${watch.train_number} · ${watch.from_code} → ${watch.to_code} · ${formatFullDate(watch.journey_date)} · ${watch.travel_class}`;

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <TrainBadge number={watch.train_number} />
            <h3 className="font-medium text-wims-text">{watch.train_name}</h3>
          </div>
          <p className="mt-1 text-sm text-wims-text">
            {watch.from_name} <span className="text-wims-muted">({watch.from_code})</span> → {watch.to_name}{" "}
            <span className="text-wims-muted">({watch.to_code})</span>
          </p>
          <p className="text-[13px] text-wims-muted">
            {formatFullDate(watch.journey_date)} · {watch.travel_class} · {CLASS_NAMES[watch.travel_class] ?? ""}
          </p>
        </div>
        <div className="text-right">
          {last ? (
            <>
              <StatusPill status={last.status} availability={null} />
              <p className="mt-1 text-[11px] text-wims-muted">
                {statusLabel(last)} · {last.source === "live" ? "live" : "you noted"} · {now ? ago(last.at, now) : ""}
              </p>
            </>
          ) : (
            <span className="text-[13px] text-wims-muted">Not checked yet</span>
          )}
        </div>
      </div>

      {past ? (
        <p className="mt-3 text-[13px] font-medium text-wims-late">This journey date has passed — you can remove it.</p>
      ) : (
        <p className={`mt-3 text-[13px] ${tone}`}>{trend.text}</p>
      )}

      {watch.history.length > 1 && (
        <ol className="mt-2 flex flex-wrap gap-1.5" aria-label="Earlier checks">
          {watch.history.slice(-8).map((c) => (
            <li key={c.at} className="rounded-sm bg-[#f1f4f8] px-1.5 py-0.5 text-[11px] text-wims-text tabular" title={new Date(c.at).toLocaleString("en-IN")}>
              {statusLabel(c)} <span className="text-wims-muted">· {now ? ago(c.at, now) : ""}</span>
            </li>
          ))}
        </ol>
      )}

      {!past && (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <a
              href={IRCTC}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => navigator.clipboard?.writeText(details).catch(() => {})}
              className="inline-flex items-center gap-1.5 rounded bg-wims-green px-3 py-1.5 text-xs font-medium text-white hover:bg-wims-green-dark"
              title={`Copies “${details}” and opens IRCTC`}
            >
              Check on IRCTC <ExternalLink className="h-3.5 w-3.5" />
            </a>
            {live && (
              <button
                type="button"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  setResult(await checkLive(watch));
                  setBusy(false);
                }}
                className="inline-flex items-center gap-1.5 rounded border border-wims-blue px-3 py-1.5 text-xs font-medium text-wims-blue hover:bg-[#eaf3fb] disabled:opacity-60"
              >
                {busy ? <Spinner className="h-3.5 w-3.5" /> : <Radio className="h-3.5 w-3.5" />}
                Check live now
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                const ics = reminderCalendar(watch, Date.now(), `${window.location.origin}/watch`);
                const url = URL.createObjectURL(new Blob([ics], { type: "text/calendar" }));
                const a = document.createElement("a");
                a.href = url;
                a.download = `seat-watch-${watch.train_number}-${watch.journey_date}.ics`;
                a.click();
                setTimeout(() => URL.revokeObjectURL(url), 1000);
              }}
              className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium text-wims-blue hover:bg-[#eaf3fb]"
            >
              <CalendarPlus className="h-3.5 w-3.5" /> Daily reminder
            </button>
            <button
              type="button"
              onClick={() => removeWatch(watch.id)}
              className="ml-auto inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium text-wims-muted hover:bg-[#fdecea] hover:text-wims-late"
            >
              <Trash2 className="h-3.5 w-3.5" /> Stop tracking
            </button>
          </div>
          {live && (
            <div className="mt-2">
              <Toggle
                checked={watch.auto}
                onChange={(auto) => updateWatch(watch.id, { auto })}
                label="Auto-check every 6 hours while this page is open"
              />
            </div>
          )}
          {result && <LiveAnswer result={result} />}
          <NoteStatus watch={watch} />
        </>
      )}
      {past && (
        <button
          type="button"
          onClick={() => removeWatch(watch.id)}
          className="mt-2 inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium text-wims-late hover:bg-[#fdecea]"
        >
          <Trash2 className="h-3.5 w-3.5" /> Remove
        </button>
      )}
    </Card>
  );
}

/** While the page is open, re-check followed tickets that asked for it (spends live checks). */
function useAutoCheck(live: boolean) {
  const spent = useRef(0);
  useEffect(() => {
    if (!live) return;
    let alive = true;
    const run = async () => {
      const today = todayInIndia();
      const due = loadWatches().filter(
        (w) => w.auto && w.journey_date >= today && Date.now() - lastLiveAt(w) > AUTO_EVERY_MS,
      );
      for (const w of due) {
        if (!alive || spent.current >= AUTO_PER_VISIT) break;
        spent.current += 1;
        await checkLive(w);
      }
    };
    void run();
    const timer = setInterval(run, 30 * 60_000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [live]);
}

export function SeatWatch() {
  const hydrated = useHydrated();
  const watches = useWatches();
  const now = useNow();
  const live = useLiveChecks();
  const [usage, setUsage] = useState<LiveUsage | null>(null);
  useAutoCheck(live);
  useEffect(() => {
    let alive = true;
    api
      .liveUsage()
      .then((u) => alive && setUsage(u))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [live, watches]);

  const upcoming = [...watches].sort((a, b) => a.journey_date.localeCompare(b.journey_date));

  return (
    <main className={`${PAGE} py-6`}>
      <div className="mx-auto max-w-4xl">
        <h1 className="flex items-center gap-2 text-2xl font-medium text-wims-text">
          <BellRing className="h-6 w-6 text-wims-blue" /> Seat Watch
        </h1>
        <p className="mt-1 text-[15px] text-wims-muted">
          Follow the tickets you care about. Every check is saved here, so you can see whether the waitlist is moving
          and when to switch to a backup.
        </p>
        <div className="mt-3 rounded-md border border-wims-hairline bg-white px-4 py-3 text-[13px] text-wims-text">
          {live ? (
            <>
              <span className="font-medium text-wims-green-dark">Live checks are on</span> via{" "}
              {usage?.source ?? "a third-party source"} — not IRCTC, so always confirm on IRCTC before you pay.
              {usage?.remaining_this_month != null && (
                <> {usage.remaining_this_month} of {usage.monthly_limit} free checks left (last 30 days).</>
              )}
            </>
          ) : (
            <>
              <span className="font-medium">Live checks are off.</span>{" "}
              {usage?.blocked_reason ? `${usage.blocked_reason} ` : ""}
              Tap <em>Check on IRCTC</em> (it copies the ticket details), then note what you see — Seat Watch shows how
              the waitlist moves.{" "}
              {!usage?.blocked_reason && (
                <>
                  Set up live checks:{" "}
                  <Link href="/about#live" className="font-medium text-wims-blue underline">
                    how
                  </Link>
                  .
                </>
              )}
            </>
          )}
        </div>

        <div className="mt-4 space-y-3">
          {!hydrated ? (
            <Card className="h-32 animate-pulse" />
          ) : upcoming.length === 0 ? (
            <Card className="p-6 text-center">
              <p className="font-medium text-wims-text">No tickets tracked yet</p>
              <p className="mt-1 text-sm text-wims-muted">
                Search a route, open a train&apos;s details and tap <strong>Track seats</strong>.
              </p>
              <Link
                href="/"
                className="mt-3 inline-flex items-center gap-1.5 rounded bg-wims-green px-4 py-2 text-sm font-medium text-white hover:bg-wims-green-dark"
              >
                <Search className="h-4 w-4" /> Find trains
              </Link>
            </Card>
          ) : (
            upcoming.map((w) => <WatchCard key={w.id} watch={w} now={now} live={live} />)
          )}
        </div>
        <p className="mt-4 text-xs text-wims-muted">
          Seat Watch lives in this browser only. Trends are worked out from the checks saved here — they are not a
          prediction from Indian Railways.
        </p>
      </div>
    </main>
  );
}
