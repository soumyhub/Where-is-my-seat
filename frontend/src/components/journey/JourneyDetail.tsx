"use client";

import { ArrowLeft, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { formatTime, timeAgo } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { PAGE } from "@/lib/layout";
import { isSaved, updateTrip, useSavedTrips } from "@/lib/storage";
import type { JourneyResponse } from "@/lib/types";

import { Card, ErrorState, Spinner } from "../ui";
import { PrintButton, WhatsAppLink } from "./Actions";
import { Details } from "./Details";

type State = { key: string; data?: JourneyResponse; error?: ApiError };

export function JourneyDetail() {
  const id = useSearchParams().get("id") ?? "";
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<State>({ key: "" });
  const trips = useSavedTrips();
  const now = useNow();
  const key = `${id}#${attempt}`;

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    api
      .journey(id, controller.signal)
      .then((data) => {
        setState({ key, data });
        // A saved trip gets the refreshed details too, so the Saved list stays honest.
        if (isSaved(trips, id)) updateTrip(id, { itinerary: data.itinerary, checked_at: data.checked_at });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ key, error: error instanceof ApiError ? error : new ApiError("UNKNOWN", "Could not load this journey.") });
      });
    return () => controller.abort();
    // `trips` is read for the save check only; re-fetching on every storage change is not wanted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, key]);

  const loading = !!id && state.key !== key;
  const data = loading ? undefined : state.data;
  const it = data?.itinerary;

  return (
    <main className={`${PAGE} py-4`}>
      <div className="mx-auto max-w-4xl space-y-4">
        <button
          type="button"
          onClick={() => (window.history.length > 1 ? router.back() : router.push("/"))}
          className="no-print inline-flex items-center gap-1 text-sm font-medium text-wims-blue"
        >
          <ArrowLeft className="h-4 w-4" /> Back
        </button>

        {!id && <ErrorState title="No journey selected" message="This link has no journey in it." />}

        {loading && (
          <Card className="flex items-center gap-3 p-5 text-wims-text">
            <Spinner className="h-5 w-5 text-wims-badge" /> Re-checking this journey against the timetable…
          </Card>
        )}

        {!loading && state.error && (
          <ErrorState
            title={
              state.error.code === "JOURNEY_DEPARTED"
                ? "This journey has already left"
                : state.error.code === "JOURNEY_NO_LONGER_VALID"
                  ? "This journey no longer works"
                  : "We couldn't open this journey"
            }
            message={state.error.message}
            hint={state.error.hint}
            onRetry={state.error.code === "BACKEND_UNREACHABLE" || state.error.code === "TIMEOUT" ? () => setAttempt((n) => n + 1) : undefined}
            action={
              <Link href="/" className="rounded border border-wims-hairline px-3 py-2 text-sm font-medium text-wims-blue">
                New search
              </Link>
            }
          />
        )}

        {data && it && (
          <>
            <Card className="overflow-hidden">
              <Details
                it={it}
                originName={data.origin.name}
                destinationName={data.destination.name}
                showOpenLink={false}
                routeOpen
                mapOpen
              />
            </Card>
            <div className="no-print flex flex-wrap items-center justify-center gap-1">
              <WhatsAppLink it={it} />
              <PrintButton />
            </div>
            <p className="text-center text-xs text-wims-muted">
              Checked {now ? timeAgo(data.checked_at, now) : formatTime(data.checked_at)} against{" "}
              {data.data_notice.timetable_source}. {data.data_notice.label}. Nothing is monitored in the background.
            </p>
          </>
        )}
      </div>

      {data && (
        <button
          type="button"
          onClick={() => setAttempt((n) => n + 1)}
          className="no-print fixed bottom-6 right-6 z-30 grid h-14 w-14 place-items-center rounded-full bg-[#d3543c] text-white shadow-lg hover:bg-[#bf4630]"
          aria-label="Re-check this journey"
          title="Re-check this journey"
        >
          <RefreshCw className="h-6 w-6" />
        </button>
      )}
    </main>
  );
}

export function JourneyFallback() {
  return (
    <div className={`${PAGE} flex items-center gap-3 py-8 text-wims-muted`}>
      <Spinner /> Loading journey…
    </div>
  );
}
