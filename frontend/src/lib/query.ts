import { SORT_MODES, TRAVEL_CLASSES, type SearchRequest, type SortMode, type TravelClass } from "./types";

/* A search lives in the results URL so it can be shared, bookmarked and reloaded. */

export const DEFAULT_REQUEST: Omit<SearchRequest, "origin" | "destination" | "date"> = {
  passengers: 1,
  travel_class: "3A",
  max_budget: null,
  max_duration_hours: null,
  max_transfers: 2,
  flexible_days: 0,
  include_nearby: true,
  allow_unreserved: true,
  smart_tickets: true,
  sort: "best",
};

export interface SearchLabels {
  fromName?: string;
  toName?: string;
}

export function toQuery(req: SearchRequest, labels: SearchLabels = {}): string {
  const q = new URLSearchParams({
    from: req.origin,
    to: req.destination,
    date: req.date,
    pax: String(req.passengers),
    cls: req.travel_class,
    tx: String(req.max_transfers),
  });
  if (req.flexible_days) q.set("flex", String(req.flexible_days));
  if (req.max_budget != null) q.set("budget", String(req.max_budget));
  if (req.max_duration_hours != null) q.set("hrs", String(req.max_duration_hours));
  if (!req.include_nearby) q.set("near", "0");
  if (!req.allow_unreserved) q.set("ur", "0");
  if (!req.smart_tickets) q.set("smart", "0");
  if (req.sort !== "best") q.set("sort", req.sort);
  if (labels.fromName) q.set("fromName", labels.fromName);
  if (labels.toName) q.set("toName", labels.toName);
  return q.toString();
}

function int(value: string | null, fallback: number, min: number, max: number): number {
  const n = value == null ? NaN : Number.parseInt(value, 10);
  return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
}

function optionalNumber(value: string | null): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function fromQuery(params: URLSearchParams): { request: SearchRequest; labels: SearchLabels } | null {
  const origin = params.get("from");
  const destination = params.get("to");
  const date = params.get("date");
  if (!origin || !destination || !date) return null;
  const cls = params.get("cls");
  const sort = params.get("sort");
  return {
    request: {
      ...DEFAULT_REQUEST,
      origin,
      destination,
      date,
      passengers: int(params.get("pax"), 1, 1, 6),
      travel_class: (TRAVEL_CLASSES as readonly string[]).includes(cls ?? "") ? (cls as TravelClass) : "3A",
      max_transfers: int(params.get("tx"), 2, 0, 3),
      flexible_days: int(params.get("flex"), 0, 0, 3),
      max_budget: optionalNumber(params.get("budget")),
      max_duration_hours: optionalNumber(params.get("hrs")),
      include_nearby: params.get("near") !== "0",
      allow_unreserved: params.get("ur") !== "0",
      smart_tickets: params.get("smart") !== "0",
      sort: (SORT_MODES as readonly string[]).includes(sort ?? "") ? (sort as SortMode) : "best",
    },
    labels: { fromName: params.get("fromName") ?? undefined, toName: params.get("toName") ?? undefined },
  };
}
