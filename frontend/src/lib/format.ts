import type { OverallStatus } from "./types";

/* The API sends Indian Standard Time as naive "YYYY-MM-DDTHH:MM" strings. We format them
   by reading the parts directly so the browser's own time zone can never shift them. */

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function dateParts(isoDate: string): { y: number; m: number; d: number } {
  const [y, m, d] = isoDate.slice(0, 10).split("-").map(Number);
  return { y, m, d };
}

export function weekday(isoDate: string): string {
  const { y, m, d } = dateParts(isoDate);
  return WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
}

export function formatDay(isoDate: string): string {
  const { m, d } = dateParts(isoDate);
  return `${weekday(isoDate)} ${d} ${MONTHS[m - 1]}`;
}

export function formatTime(isoDateTime: string): string {
  return isoDateTime.slice(11, 16);
}

export function formatDuration(minutes: number): string {
  const m = Math.max(0, Math.round(minutes));
  const h = Math.floor(m / 60);
  const rest = m % 60;
  if (h && rest) return `${h}h ${String(rest).padStart(2, "0")}m`;
  if (h) return `${h}h`;
  return `${rest}m`;
}

const rupee = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

export function formatRupees(amount: number): string {
  return rupee.format(amount);
}

export function signedRupees(amount: number): string {
  if (amount === 0) return "same price";
  return `${amount > 0 ? "+" : "−"}${formatRupees(Math.abs(amount))}`;
}

export function signedDuration(minutes: number): string {
  if (Math.abs(minutes) < 5) return "same time";
  return `${minutes > 0 ? "+" : "−"}${formatDuration(Math.abs(minutes))}`;
}

export function dayDelta(fromIso: string, toIso: string): number {
  const a = dateParts(fromIso);
  const b = dateParts(toIso);
  return Math.round((Date.UTC(b.y, b.m - 1, b.d) - Date.UTC(a.y, a.m - 1, a.d)) / 86400000);
}

export function addDays(isoDate: string, days: number): string {
  const { y, m, d } = dateParts(isoDate);
  const date = new Date(Date.UTC(y, m - 1, d + days));
  return date.toISOString().slice(0, 10);
}

/** Absolute epoch ms for an IST wall-clock string. */
export function istToEpoch(isoDateTime: string): number {
  return new Date(`${isoDateTime.length === 16 ? `${isoDateTime}:00` : isoDateTime}+05:30`).getTime();
}

/** Today's date in India, independent of the browser's time zone. */
export function todayInIndia(now: number = Date.now()): string {
  return new Date(now + 330 * 60000).toISOString().slice(0, 10);
}

export function timeAgo(isoDateTime: string, now: number): string {
  const minutes = Math.round((now - istToEpoch(isoDateTime)) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

export const STALE_AFTER_MINUTES = 360;

export function isStale(isoDateTime: string, now: number): boolean {
  return now - istToEpoch(isoDateTime) > STALE_AFTER_MINUTES * 60000;
}

export const STATUS_META: Record<OverallStatus, { label: string; tone: string; dot: string }> = {
  CONFIRMED: { label: "Seats available", tone: "bg-[#e5f5e3] text-[#1e7b25] ring-[#9fd49b]", dot: "bg-[#2e9a35]" },
  RAC: { label: "RAC", tone: "bg-[#fff2dc] text-[#9a5a00] ring-[#f2c37a]", dot: "bg-[#e09100]" },
  WAITLISTED: { label: "Waitlisted", tone: "bg-[#fdebea] text-[#b3261e] ring-[#f1aca7]", dot: "bg-[#d23b30]" },
  UNAVAILABLE: { label: "Not available", tone: "bg-[#eeeeee] text-[#5f5f5f] ring-[#cfcfcf]", dot: "bg-[#8a8a8a]" },
  UNKNOWN: { label: "Check seats on IRCTC", tone: "bg-[#f2f2f2] text-[#5f5f5f] ring-[#d6d6d6]", dot: "bg-[#a0a0a0]" },
  UNRESERVED: { label: "Unreserved", tone: "bg-[#e3f0fb] text-[#155a99] ring-[#a9cdee]", dot: "bg-[#2887c7]" },
};

export const CATEGORY_LABELS: Record<string, string> = {
  direct: "Direct",
  alternative_boarding: "Different boarding station",
  connecting: "Connecting trains",
  alternative_destination: "Nearby destination",
  flexible_date: "Another date",
  smart_ticket: "Smart ticket",
};

export const STRATEGY_LABELS: Record<string, string> = {
  standard: "Standard ticket",
  book_beyond: "Book beyond",
  upstream_boarding: "Book from the start station",
  split: "Split ticket",
  later_boarding: "Board at a nearby station",
};

export const CLASS_ORDER = ["1A", "2A", "3A", "3E", "SL", "EC", "CC", "FC", "2S", "UR"];

const DAY_LETTERS: [string, string][] = [
  ["Sun", "S"], ["Mon", "M"], ["Tue", "T"], ["Wed", "W"], ["Thu", "T"], ["Fri", "F"], ["Sat", "S"],
];

/** WIMT-style running days: letters S M T W T F S with the running ones marked. */
export function runningDays(label: string): { letter: string; runs: boolean; name: string }[] {
  const all = label === "Daily";
  const days = new Set(label.split(",").map((d) => d.trim()));
  return DAY_LETTERS.map(([name, letter]) => ({ name, letter, runs: all || days.has(name) }));
}

/** "26 Nov 2026" for copying into IRCTC's date field. */
export function formatFullDate(isoDate: string): string {
  const [y, m, d] = isoDate.slice(0, 10).split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

export const CLASS_NAMES: Record<string, string> = {
  SL: "Sleeper",
  "3A": "AC 3 Tier",
  "2A": "AC 2 Tier",
  "1A": "AC First",
  CC: "AC Chair Car",
  EC: "Executive Chair Car",
  "3E": "AC 3 Economy",
  FC: "First Class",
  "2S": "Second Sitting",
  ANY: "Any class",
  UR: "Unreserved",
};

export function isBookable(status: OverallStatus): boolean {
  return status === "CONFIRMED" || status === "UNRESERVED";
}
