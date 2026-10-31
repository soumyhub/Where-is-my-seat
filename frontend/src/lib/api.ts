import type { ZodType } from "zod";

import {
  ApiErrorBodySchema,
  AvailabilityCheckResponseSchema,
  AlertsSchema,
  CoachesSchema,
  JourneyMapSchema,
  LiveFareSchema,
  LiveTrainSchema,
  PunctualitySchema,
  StationBoardSchema,
  LiveUsageSchema,
  JourneyResponseSchema,
  MetaSchema,
  PlaceSchema,
  SearchResponseSchema,
  type AvailabilityCheckResponse,
  type JourneyMap,
  type JourneyResponse,
  type LiveUsage,
  type Meta,
  type Place,
  type SearchRequest,
  type SearchResponse,
  type TicketCheckInput,
} from "./types";

/* All calls go through the Next.js rewrite at /api -> FastAPI, so the browser never
   needs CORS and the backend address lives in one place (WIMS_API_URL). */
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public hint?: string | null,
    public status?: number,
  ) {
    super(message);
  }
}

const BACKEND_DOWN = new ApiError(
  "BACKEND_UNREACHABLE",
  "Can't reach the Where Is My Seat server.",
  process.env.NODE_ENV === "development"
    ? "Start the backend (cd backend && .venv/bin/uvicorn app.main:app --port 8000) and try again."
    : "Please check your connection and try again in a moment.",
);

async function request<T>(path: string, schema: ZodType<T>, init?: RequestInit, timeoutMs = 15000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const signal = init?.signal ? AbortSignal.any([init.signal, controller.signal]) : controller.signal;
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (error) {
    if (init?.signal?.aborted) throw error; // the caller cancelled; not an error to show
    if (controller.signal.aborted) {
      throw new ApiError("TIMEOUT", "The server took too long to answer.", "Try again, or narrow the search.");
    }
    throw BACKEND_DOWN;
  } finally {
    clearTimeout(timer);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    if (response.status >= 500) throw BACKEND_DOWN;
    throw new ApiError("BAD_RESPONSE", `Unexpected response from the server (HTTP ${response.status}).`);
  }

  if (!response.ok) {
    const parsed = ApiErrorBodySchema.safeParse(body);
    if (parsed.success) {
      const { code, message, hint } = parsed.data.error;
      throw new ApiError(code, message, hint, response.status);
    }
    throw new ApiError(`HTTP_${response.status}`, "The server could not complete the request.", null, response.status);
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    console.error("API response did not match schema", path, parsed.error);
    throw new ApiError(
      "BAD_RESPONSE",
      "The server's answer didn't match what this app expects.",
      "Make sure the frontend and backend are from the same version.",
    );
  }
  return parsed.data;
}

const PlaceListSchema = PlaceSchema.array();

let metaPromise: Promise<Meta> | null = null;

export const api = {
  meta(): Promise<Meta> {
    metaPromise ??= request("/meta", MetaSchema).catch((error) => {
      metaPromise = null;
      throw error;
    });
    return metaPromise;
  },
  stations(query: string, signal?: AbortSignal): Promise<Place[]> {
    return request(`/stations?query=${encodeURIComponent(query)}&limit=8`, PlaceListSchema, { signal });
  },
  search(body: SearchRequest, signal?: AbortSignal): Promise<SearchResponse> {
    return request("/journeys/search", SearchResponseSchema, { method: "POST", body: JSON.stringify(body), signal }, 20000);
  },
  journey(id: string, signal?: AbortSignal): Promise<JourneyResponse> {
    return request(`/journeys/${encodeURIComponent(id)}`, JourneyResponseSchema, { signal });
  },
  journeyMap(id: string, signal?: AbortSignal): Promise<JourneyMap> {
    return request(`/journeys/${encodeURIComponent(id)}/map`, JourneyMapSchema, { signal });
  },
  /** Live seat check for up to 3 tickets (only when the server has a live source). */
  checkSeats(checks: TicketCheckInput[], passengers = 1): Promise<AvailabilityCheckResponse> {
    return request(
      "/availability/check",
      AvailabilityCheckResponseSchema,
      { method: "POST", body: JSON.stringify({ passengers, checks }) },
      20000,
    );
  },
  liveUsage(): Promise<LiveUsage> {
    return request("/availability/usage", LiveUsageSchema);
  },
  /* Live tools: each call may spend one of the free RailRadar requests (cached answers don't). */
  live: {
    train: (number: string, startDate?: string | null) =>
      request(`/live/trains/${number}${startDate ? `?date=${startDate}` : ""}`, LiveTrainSchema, undefined, 20000),
    station: (code: string, hours: number) =>
      request(`/live/stations/${encodeURIComponent(code)}?hours=${hours}`, StationBoardSchema, undefined, 20000),
    fare: (q: { train: string; from: string; to: string; date: string; cls: string }) =>
      request(
        `/live/fare?train=${q.train}&from_code=${q.from}&to_code=${q.to}&date=${q.date}&travel_class=${q.cls}`,
        LiveFareSchema,
        undefined,
        20000,
      ),
    coaches: (number: string, station: string) =>
      request(`/live/trains/${number}/coaches/${encodeURIComponent(station)}`, CoachesSchema, undefined, 20000),
    punctuality: (number: string) => request(`/live/trains/${number}/punctuality`, PunctualitySchema, undefined, 20000),
    alerts: (number: string) => request(`/live/trains/${number}/alerts`, AlertsSchema, undefined, 20000),
  },
};
