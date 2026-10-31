"use client";

import { ChevronDown, ChevronLeft, ChevronRight, Info, Pencil, SlidersHorizontal, TrainTrack } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Fragment, useEffect, useMemo, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { addDays, formatDay, formatDuration } from "@/lib/format";
import { useMeta } from "@/lib/hooks";
import { PAGE } from "@/lib/layout";
import { fromQuery, toQuery } from "@/lib/query";
import type { Itinerary, SearchRequest, SearchResponse } from "@/lib/types";

import { Details } from "../journey/Details";
import { Card, Chip, ErrorState, Spinner, Toggle } from "../ui";
import { DirectTrainCard, RouteCard } from "./TrainCard";

type Tab = "direct" | "other";
type Sort = "best" | "departure" | "fastest" | "cheapest";

const SORTS: { value: Sort; label: string }[] = [
  { value: "best", label: "Recommended" },
  { value: "departure", label: "Departs earliest" },
  { value: "fastest", label: "Fastest" },
  { value: "cheapest", label: "Lowest fare" },
];

const WINDOWS = [
  { value: "any", label: "Any time", from: 0, to: 24 },
  { value: "early", label: "12–6 am", from: 0, to: 6 },
  { value: "morning", label: "6 am–12 pm", from: 6, to: 12 },
  { value: "afternoon", label: "12–5 pm", from: 12, to: 17 },
  { value: "evening", label: "5–9 pm", from: 17, to: 21 },
  { value: "night", label: "9 pm–12 am", from: 21, to: 24 },
];

function sortItems(items: Itinerary[], mode: Sort): Itinerary[] {
  const key: Record<Sort, (it: Itinerary) => number | string> = {
    best: (it) => -it.score,
    departure: (it) => it.depart_at,
    fastest: (it) => it.total_minutes,
    cheapest: (it) => it.cost_per_person,
  };
  return [...items].sort((a, b) => {
    const ka = key[mode](a);
    const kb = key[mode](b);
    return ka < kb ? -1 : ka > kb ? 1 : b.score - a.score;
  });
}

function trainType(it: Itinerary): string {
  return it.legs.find((l) => l.train)?.train?.category ?? "Express";
}

type Result = { key: string; data?: SearchResponse; error?: ApiError };

export function ResultsView() {
  const params = useSearchParams();
  const router = useRouter();
  const today = useMeta().data?.today;
  const parsed = useMemo(() => fromQuery(new URLSearchParams(params.toString())), [params]);
  const fetchKey = parsed ? JSON.stringify({ ...parsed.request, sort: "best" }) : "";
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result>({ key: "" });
  const [tab, setTab] = useState<Tab | null>(null);
  const [sort, setSort] = useState<Sort>("best");
  const [timeWindow, setTimeWindow] = useState("any");
  const [types, setTypes] = useState<string[]>([]);
  const [onlyMyClass, setOnlyMyClass] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [openGroups, setOpenGroups] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState(false);
  const requestKey = `${fetchKey}#${attempt}`;

  useEffect(() => {
    if (!fetchKey) return;
    const controller = new AbortController();
    api
      .search(JSON.parse(fetchKey) as SearchRequest, controller.signal)
      .then((data) => setResult({ key: requestKey, data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setResult({ key: requestKey, error: error instanceof ApiError ? error : new ApiError("UNKNOWN", "Something went wrong while searching.") });
      });
    return () => controller.abort();
  }, [fetchKey, requestKey]);

  if (!parsed) {
    return (
      <div className={`${PAGE} py-6`}>
        <ErrorState
          title="This search link is incomplete"
          message="It needs a From station, a To station and a date."
          action={
            <Link href="/" className="rounded bg-wims-blue px-3 py-2 text-sm font-medium text-white">
              New search
            </Link>
          }
        />
      </div>
    );
  }

  const { request, labels } = parsed;
  const loading = result.key !== requestKey;
  const data = loading ? undefined : result.data;
  const error = loading ? undefined : result.error;
  const short = (name: string) => name.replace(/ \(all stations\)$/, "");
  const fromName = short(data?.query.origin.name ?? labels.fromName ?? request.origin);
  const toName = short(data?.query.destination.name ?? labels.toName ?? request.destination);
  const go = (patch: Partial<SearchRequest>) => router.push(`/results?${toQuery({ ...request, ...patch }, labels)}`);

  const all = data?.itineraries ?? [];
  const direct = all.filter((it) => it.primary_category === "direct");
  const other = all.filter((it) => it.primary_category !== "direct");
  const activeTab: Tab = tab ?? (direct.length ? "direct" : "other");
  const win = WINDOWS.find((w) => w.value === timeWindow) ?? WINDOWS[0];
  const pool = activeTab === "direct" ? direct : other;
  const typeOptions = Array.from(new Set(pool.map(trainType))).sort();
  const filtered = pool.filter((it) => {
    const hour = Number(it.depart_at.slice(11, 13));
    if (hour < win.from || hour >= win.to) return false;
    if (types.length && !types.includes(trainType(it))) return false;
    if (onlyMyClass && request.travel_class !== "ANY") {
      return it.legs.every((l) => !l.train || request.travel_class in l.class_fares);
    }
    return true;
  });
  const sorted = sortItems(filtered, sort);
  const selected = all.find((it) => it.id === selectedId) ?? sorted[0] ?? null;
  const filtersOn = (timeWindow !== "any" ? 1 : 0) + types.length + (onlyMyClass ? 1 : 0);

  // Group "other ways" that read the same (e.g. four trains to the same nearby station).
  const groups: { key: string; items: Itinerary[] }[] = [];
  if (activeTab === "other") {
    const byKey = new Map<string, Itinerary[]>();
    for (const it of sorted) {
      const k = it.headline;
      if (!byKey.has(k)) {
        byKey.set(k, []);
        groups.push({ key: k, items: byKey.get(k)! });
      }
      byKey.get(k)!.push(it);
    }
  }

  const prevDay = addDays(request.date, -1);
  const nextDay = addDays(request.date, 1);

  const details = selected && (
    <Details it={selected} originName={fromName} destinationName={toName} />
  );

  const renderCard = (it: Itinerary, similar = 0, onShowSimilar?: () => void) => {
    const isSelected = selected?.id === it.id;
    // Tapping toggles: on small screens the details open inline under the card.
    const toggle = () => setSelectedId((cur) => (cur === it.id ? null : it.id));
    const card =
      it.primary_category === "direct" ? (
        <DirectTrainCard it={it} travelClass={request.travel_class} selected={isSelected} onSelect={toggle} />
      ) : (
        <RouteCard it={it} selected={isSelected} onSelect={toggle} similar={similar} onShowSimilar={onShowSimilar} />
      );
    return (
      <Fragment key={it.id}>
        {card}
        {selectedId === it.id && (
          <Card className="overflow-hidden xl:hidden">
            {details}
          </Card>
        )}
      </Fragment>
    );
  };

  return (
    <main>
      <section className="bg-wims-navy text-white">
        <div className={`${PAGE} flex flex-wrap items-center gap-x-6 gap-y-3 py-3`}>
          <div className="flex min-w-0 items-center gap-3">
            <span className="truncate text-[19px] font-medium md:text-[22px]">{fromName}</span>
            <TrainTrack className="h-5 w-5 shrink-0 text-white/80" aria-label="to" />
            <span className="truncate text-[19px] font-medium md:text-[22px]">{toName}</span>
          </div>
          <div className="flex items-center rounded-full bg-black/20 text-[13px]">
            <button
              type="button"
              onClick={() => go({ date: prevDay })}
              disabled={!!today && prevDay < today}
              className="grid h-9 w-9 place-items-center rounded-full hover:bg-white/10 disabled:opacity-30"
              aria-label={`Search ${formatDay(prevDay)}`}
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="px-1 font-medium">{formatDay(request.date)}</span>
            <button
              type="button"
              onClick={() => go({ date: nextDay })}
              className="grid h-9 w-9 place-items-center rounded-full hover:bg-white/10"
              aria-label={`Search ${formatDay(nextDay)}`}
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
          <span className="text-[13px] text-white/80">
            {request.travel_class === "ANY" ? "Any class" : request.travel_class} · {request.passengers} traveller
            {request.passengers > 1 ? "s" : ""}
          </span>
          <Link href={`/?${toQuery(request, labels)}`} className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-white px-3.5 py-1.5 text-[13px] font-medium text-wims-navy">
            <Pencil className="h-3.5 w-3.5" /> Change search
          </Link>
        </div>
      </section>

      <div className={`${PAGE} py-4`}>
        {loading && (
          <Card className="p-5">
            <div className="flex items-center gap-3 text-wims-text">
              <Spinner className="h-5 w-5 text-wims-badge" /> Finding every train and backup option…
            </div>
            <div className="mt-4 grid gap-3 lg:grid-cols-2" aria-hidden>
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-32 animate-pulse rounded bg-[#f1f1f1]" />
              ))}
            </div>
          </Card>
        )}

        {error && (
          <ErrorState
            title={error.code === "BACKEND_UNREACHABLE" ? "The search server is offline" : "We couldn't run this search"}
            message={error.message}
            hint={error.hint}
            onRetry={() => setAttempt((n) => n + 1)}
            action={
              <Link href={`/?${toQuery(request, labels)}`} className="rounded border border-wims-hairline px-3 py-2 text-sm font-medium text-wims-blue">
                Change search
              </Link>
            }
          />
        )}

        {data && (
          <div className="space-y-4">
            <div className="flex items-start gap-3 rounded-[3px] border border-[#cfe0f1] bg-[#f2f8fe] px-4 py-3">
              <Info className="mt-0.5 h-5 w-5 shrink-0 text-wims-badge" aria-hidden />
              <div>
                <h1 className="font-medium text-wims-text">{data.summary.headline}</h1>
                <p className="text-sm text-wims-text/80">{data.summary.subline}</p>
                {data.rush && <p className="mt-1 text-[13px] text-[#8a3a00]">{data.rush.message}</p>}
              </div>
            </div>

            {all.length === 0 ? (
              <Card className="p-5">
                <h2 className="font-medium text-wims-text">No trains found for these settings</h2>
                <p className="mt-1 text-sm text-wims-muted">{data.no_results_message}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Chip active={false} onClick={() => go({ date: nextDay })}>
                    Try {formatDay(nextDay)}
                  </Chip>
                  {request.max_transfers < 2 && (
                    <Chip active={false} onClick={() => go({ max_transfers: 2 })}>
                      Allow changes
                    </Chip>
                  )}
                  {!request.include_nearby && (
                    <Chip active={false} onClick={() => go({ include_nearby: true })}>
                      Include nearby stations
                    </Chip>
                  )}
                  {(request.max_budget != null || request.max_duration_hours != null) && (
                    <Chip active={false} onClick={() => go({ max_budget: null, max_duration_hours: null })}>
                      Remove budget & time limits
                    </Chip>
                  )}
                </div>
              </Card>
            ) : (
              <div className="grid items-start gap-4 lg:grid-cols-[230px_minmax(0,1fr)] xl:grid-cols-[230px_minmax(0,1fr)_minmax(400px,0.85fr)]">
                <aside className={`${showFilters ? "block" : "hidden"} lg:sticky lg:top-24 lg:block`} aria-label="Filters">
                  <Card className="space-y-5 p-4 text-sm">
                    <div>
                      <h2 className="mb-2 text-[11px] font-medium uppercase tracking-wider text-wims-muted">Departure time</h2>
                      <div className="flex flex-wrap gap-1.5">
                        {WINDOWS.map((w) => (
                          <Chip key={w.value} active={timeWindow === w.value} onClick={() => setTimeWindow(w.value)}>
                            {w.label}
                          </Chip>
                        ))}
                      </div>
                    </div>
                    {typeOptions.length > 1 && (
                      <div>
                        <h2 className="mb-2 text-[11px] font-medium uppercase tracking-wider text-wims-muted">Train type</h2>
                        <div className="flex flex-wrap gap-1.5">
                          {typeOptions.map((t) => (
                            <Chip
                              key={t}
                              active={types.includes(t)}
                              onClick={() => setTypes((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]))}
                            >
                              {t}
                            </Chip>
                          ))}
                        </div>
                      </div>
                    )}
                    {request.travel_class !== "ANY" && (
                      <Toggle checked={onlyMyClass} onChange={setOnlyMyClass} label={`Only trains with ${request.travel_class}`} />
                    )}
                    {filtersOn > 0 && (
                      <button
                        type="button"
                        onClick={() => {
                          setTimeWindow("any");
                          setTypes([]);
                          setOnlyMyClass(false);
                        }}
                        className="font-medium text-wims-blue"
                      >
                        Clear filters
                      </button>
                    )}
                  </Card>
                </aside>

                <section aria-label="Results" className="min-w-0 space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="flex rounded-full bg-white p-1 shadow-[0_1px_2px_rgba(0,0,0,0.12)]" role="tablist">
                      {(
                        [
                          ["direct", `Direct trains (${direct.length})`],
                          ["other", `Other ways (${other.length})`],
                        ] as [Tab, string][]
                      ).map(([value, label]) => (
                        <button
                          key={value}
                          type="button"
                          role="tab"
                          aria-selected={activeTab === value}
                          onClick={() => {
                            setTab(value);
                            setSelectedId(null);
                            setTypes([]);
                          }}
                          className={`rounded-full px-4 py-1.5 text-[13px] font-medium ${
                            activeTab === value ? "bg-wims-blue text-white" : "text-wims-text hover:bg-[#eef3f8]"
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <label className="ml-auto flex items-center gap-2 text-[13px] text-wims-muted">
                      Sort
                      <select
                        value={sort}
                        onChange={(e) => setSort(e.target.value as Sort)}
                        className="h-9 rounded-md border border-wims-hairline bg-white px-2 text-[13px] text-wims-text"
                      >
                        {SORTS.map((s) => (
                          <option key={s.value} value={s.value}>
                            {s.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      type="button"
                      onClick={() => setShowFilters((v) => !v)}
                      aria-expanded={showFilters}
                      className="inline-flex h-9 items-center gap-1.5 rounded-md bg-white px-3 text-[13px] font-medium text-wims-blue shadow-[0_1px_2px_rgba(0,0,0,0.12)] lg:hidden"
                    >
                      <SlidersHorizontal className="h-4 w-4" /> Filters{filtersOn ? ` (${filtersOn})` : ""}
                    </button>
                  </div>

                  {activeTab === "other" && other.length > 0 && (
                    <p className="text-[13px] text-wims-muted">
                      Use these if the direct trains are full: start from another station, change trains once, or end
                      near your destination.
                    </p>
                  )}

                  {sorted.length === 0 && (
                    <Card className="p-5 text-sm text-wims-muted">
                      {pool.length === 0
                        ? activeTab === "direct"
                          ? "No direct train on this date — see Other ways."
                          : "No other routes needed or found for this search."
                        : "No trains match these filters."}
                    </Card>
                  )}

                  {activeTab === "direct"
                    ? sorted.map((it) => renderCard(it))
                    : groups.map((g) => {
                        const open = openGroups.includes(g.key);
                        const [first, ...rest] = g.items;
                        return (
                          <Fragment key={g.key}>
                            {renderCard(first, open ? 0 : rest.length, () => setOpenGroups((cur) => [...cur, g.key]))}
                            {open && rest.map((it) => renderCard(it))}
                          </Fragment>
                        );
                      })}

                  <SearchNotes data={data} />
                </section>

                <aside className="sticky top-24 hidden max-h-[calc(100vh-7rem)] overflow-auto xl:block" aria-label="Details">
                  <Card className="overflow-hidden">{details}</Card>
                </aside>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}

function SearchNotes({ data }: { data: SearchResponse }) {
  const [open, setOpen] = useState(false);
  const s = data.search_stats as Record<string, unknown>;
  const n = (k: string) => (typeof s[k] === "number" ? (s[k] as number) : 0);
  return (
    <div className="pt-2 text-[13px] text-wims-muted">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="inline-flex items-center gap-1 font-medium text-wims-blue">
        About these results <ChevronDown className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="mt-2 space-y-1 rounded-[3px] bg-white p-3 shadow-[0_1px_2px_rgba(0,0,0,0.12)]">
          <p>
            Timetable: {data.data_notice.timetable_source}. Fares are estimates ({data.data_notice.fare_basis.toLowerCase()}).
          </p>
          <p>
            We checked {n("routes_found")} possible routes in {n("elapsed_ms")} ms, kept at least{" "}
            {formatDuration(Number((s.limits as Record<string, number> | undefined)?.min_transfer_minutes ?? 30))} for every
            change of train, rejected {n("rejected_short_connections")} connections that were too tight and{" "}
            {n("loops_prevented")} routes that doubled back.
          </p>
          {data.data_notice.details.map((d) => (
            <p key={d}>{d}</p>
          ))}
        </div>
      )}
    </div>
  );
}

export function ResultsFallback() {
  return (
    <div className={`${PAGE} flex items-center gap-3 py-8 text-wims-muted`}>
      <Spinner /> Loading search…
    </div>
  );
}
