"use client";

import { useSyncExternalStore } from "react";
import { z } from "zod";

import { ItinerarySchema, type SearchRequest } from "./types";

/* Saved journeys and recent searches live in this browser's localStorage only.
   Every read and write is guarded: private windows or blocked storage just mean
   nothing is remembered. Shape is versioned so a future backend store can migrate it. */

const SAVED_KEY = "wims.saved.v1";
const RECENT_KEY = "wims.recent.v1";
const WATCH_KEY = "wims.watch.v1";
const CHANGE_EVENT = "wims:storage";

const SavedTripSchema = z.object({
  id: z.string(),
  saved_at: z.string(), // epoch ms as string
  checked_at: z.string(), // IST "YYYY-MM-DDTHH:MM" from the API
  origin_name: z.string(),
  destination_name: z.string(),
  itinerary: ItinerarySchema,
  departed: z.boolean().optional(),
  invalid_reason: z.string().optional(),
});
export type SavedTrip = z.infer<typeof SavedTripSchema>;

const RecentSchema = z.object({
  request: z.record(z.string(), z.unknown()),
  fromName: z.string(),
  toName: z.string(),
  at: z.number(),
});
export type RecentSearch = { request: SearchRequest; fromName: string; toName: string; at: number };

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: unknown): boolean {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
    window.dispatchEvent(new Event(CHANGE_EVENT));
    return true;
  } catch {
    return false;
  }
}

function subscribe(callback: () => void): () => void {
  const onStorage = (event: Event) => {
    if (event instanceof StorageEvent && event.key && ![SAVED_KEY, RECENT_KEY, WATCH_KEY].includes(event.key)) return;
    callback();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(CHANGE_EVENT, callback);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(CHANGE_EVENT, callback);
  };
}

const cache = new Map<string, { raw: string | null; value: unknown }>();

function parseList<T>(key: string, schema: z.ZodType<T>): T[] {
  const raw = read(key);
  const hit = cache.get(key);
  if (hit && hit.raw === raw) return hit.value as T[];
  let value: T[] = [];
  try {
    const data: unknown = raw ? JSON.parse(raw) : [];
    if (Array.isArray(data)) {
      value = data.flatMap((row) => {
        const parsed = schema.safeParse(row);
        return parsed.success ? [parsed.data] : [];
      });
    }
  } catch {
    value = [];
  }
  cache.set(key, { raw, value });
  return value;
}

const EMPTY: never[] = [];

export function loadSaved(): SavedTrip[] {
  return parseList(SAVED_KEY, SavedTripSchema);
}

export function useSavedTrips(): SavedTrip[] {
  return useSyncExternalStore(subscribe, loadSaved, () => EMPTY);
}

export function isSaved(trips: SavedTrip[], id: string): boolean {
  return trips.some((t) => t.id === id);
}

export function saveTrip(trip: Omit<SavedTrip, "saved_at">): boolean {
  const rest = loadSaved().filter((t) => t.id !== trip.id);
  return write(SAVED_KEY, [{ ...trip, saved_at: String(Date.now()) }, ...rest].slice(0, 50));
}

export function updateTrip(id: string, patch: Partial<SavedTrip>): boolean {
  return write(
    SAVED_KEY,
    loadSaved().map((t) => (t.id === id ? { ...t, ...patch } : t)),
  );
}

export function removeTrip(id: string): boolean {
  return write(
    SAVED_KEY,
    loadSaved().filter((t) => t.id !== id),
  );
}

function loadRecent(): RecentSearch[] {
  return parseList(RECENT_KEY, RecentSchema) as unknown as RecentSearch[];
}

export function useRecentSearches(): RecentSearch[] {
  return useSyncExternalStore(subscribe, loadRecent, () => EMPTY);
}

export function rememberSearch(request: SearchRequest, fromName: string, toName: string): void {
  const key = (r: SearchRequest) => `${r.origin}|${r.destination}|${r.date}|${r.travel_class}`;
  const rest = loadRecent().filter((r) => key(r.request) !== key(request));
  write(RECENT_KEY, [{ request, fromName, toName, at: Date.now() }, ...rest].slice(0, 6));
}

export function clearRecent(): void {
  write(RECENT_KEY, []);
}

/* ----- Seat Watch: tickets the traveller follows, with every status they or a live source saw ----- */

const WatchCheckSchema = z.object({
  at: z.number(), // epoch ms
  status: z.enum(["CONFIRMED", "RAC", "WAITLISTED", "UNAVAILABLE"]),
  count: z.number().nullable(), // seats, RAC or WL number
  source: z.enum(["you", "live"]),
  note: z.string().optional(),
});
export type WatchCheck = z.infer<typeof WatchCheckSchema>;

const WatchSchema = z.object({
  id: z.string(),
  train_number: z.string(),
  train_name: z.string(),
  from_code: z.string(),
  from_name: z.string(),
  to_code: z.string(),
  to_name: z.string(),
  journey_date: z.string(), // YYYY-MM-DD the train leaves from_code
  travel_class: z.string(),
  added_at: z.number(),
  auto: z.boolean().default(false), // re-check live while the Seat Watch page is open
  history: z.array(WatchCheckSchema),
});
export type Watch = z.infer<typeof WatchSchema>;
export type WatchTicket = Omit<Watch, "id" | "added_at" | "auto" | "history">;

export function watchId(t: Pick<Watch, "train_number" | "from_code" | "to_code" | "journey_date" | "travel_class">): string {
  return [t.train_number, t.from_code, t.to_code, t.journey_date, t.travel_class].join("|");
}

export function loadWatches(): Watch[] {
  return parseList(WATCH_KEY, WatchSchema);
}

export function useWatches(): Watch[] {
  return useSyncExternalStore(subscribe, loadWatches, () => EMPTY);
}

export function addWatch(ticket: WatchTicket, first?: WatchCheck): boolean {
  const id = watchId(ticket);
  const rest = loadWatches().filter((w) => w.id !== id);
  const watch: Watch = { ...ticket, id, added_at: Date.now(), auto: false, history: first ? [first] : [] };
  return write(WATCH_KEY, [watch, ...rest].slice(0, 30));
}

export function removeWatch(id: string): boolean {
  return write(
    WATCH_KEY,
    loadWatches().filter((w) => w.id !== id),
  );
}

export function updateWatch(id: string, patch: Partial<Pick<Watch, "auto">>): boolean {
  return write(
    WATCH_KEY,
    loadWatches().map((w) => (w.id === id ? { ...w, ...patch } : w)),
  );
}

/** Add one observed status (newest last); identical back-to-back readings within 10 min are merged. */
export function recordWatchCheck(id: string, check: WatchCheck): boolean {
  return write(
    WATCH_KEY,
    loadWatches().map((w) => {
      if (w.id !== id) return w;
      const last = w.history[w.history.length - 1];
      const same = last && last.status === check.status && last.count === check.count && check.at - last.at < 600_000;
      const history = same ? [...w.history.slice(0, -1), check] : [...w.history, check];
      return { ...w, history: history.slice(-60) };
    }),
  );
}
