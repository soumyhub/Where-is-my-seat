"use client";

import { ArrowLeftRight, ChevronDown, Flame, Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, useTransition, type FormEvent, type ReactNode } from "react";

import { CLASS_NAMES, addDays, formatDay } from "@/lib/format";
import { useMeta } from "@/lib/hooks";
import { DEFAULT_REQUEST, fromQuery, toQuery } from "@/lib/query";
import { rememberSearch } from "@/lib/storage";
import { SearchRequestSchema, TRAVEL_CLASSES, type Meta, type Place, type TravelClass } from "@/lib/types";

import { Card, Chip, Segmented, Spinner, Stepper, Toggle } from "../ui";
import { StationInput } from "./StationInput";

function placeFromKey(key: string, name?: string): Place {
  const isCity = key.startsWith("city:");
  return { kind: isCity ? "city" : "station", key, code: isCity ? null : key, name: name ?? key, subtitle: "", city: "", codes: [], served: true };
}

export function rushFor(meta: Meta | null, date: string) {
  return meta?.rush_periods.find((r) => r.from <= date && date <= r.to) ?? null;
}

function Field({ label, children, error }: { label: string; children: ReactNode; error?: string }) {
  return (
    <div className="min-w-0">
      <span className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-wims-muted">{label}</span>
      <div className={`rounded-md border bg-white px-3 ${error ? "border-wims-late" : "border-[#cfd8e3] focus-within:border-wims-badge"}`}>
        {children}
      </div>
      {error && <p className="mt-1 text-xs text-wims-late">{error}</p>}
    </div>
  );
}

const DURATIONS = ["", "6", "8", "12", "18", "24", "36"];

export function SearchForm() {
  const router = useRouter();
  const params = useSearchParams();
  const meta = useMeta().data;
  const initial = fromQuery(params);
  const init = initial?.request;

  const [origin, setOrigin] = useState<Place | null>(init ? placeFromKey(init.origin, initial?.labels.fromName) : null);
  const [destination, setDestination] = useState<Place | null>(init ? placeFromKey(init.destination, initial?.labels.toName) : null);
  const [chosenDate, setChosenDate] = useState<string | null>(init?.date ?? null);
  const [passengers, setPassengers] = useState(init?.passengers ?? DEFAULT_REQUEST.passengers);
  const [travelClass, setTravelClass] = useState<TravelClass>(init?.travel_class ?? DEFAULT_REQUEST.travel_class);
  const [transfers, setTransfers] = useState(init?.max_transfers ?? DEFAULT_REQUEST.max_transfers);
  const [flex, setFlex] = useState(init?.flexible_days ?? 0);
  const [budget, setBudget] = useState(init?.max_budget != null ? String(init.max_budget) : "");
  const [duration, setDuration] = useState(init?.max_duration_hours != null ? String(init.max_duration_hours) : "");
  const [nearby, setNearby] = useState(init?.include_nearby ?? true);
  const [smart, setSmart] = useState(init?.smart_tickets ?? true);
  const [showMore, setShowMore] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pending, startTransition] = useTransition();

  const today = meta?.today ?? "";
  const date = chosenDate ?? (today ? addDays(today, 1) : "");
  const maxDate = today && meta ? addDays(today, meta.max_advance_days) : undefined;
  const rush = date ? rushFor(meta ?? null, date) : null;

  function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = SearchRequestSchema.safeParse({
      ...DEFAULT_REQUEST,
      origin: origin?.key ?? "",
      destination: destination?.key ?? "",
      date,
      passengers,
      travel_class: travelClass,
      max_transfers: transfers,
      flexible_days: flex,
      max_budget: budget.trim() ? Number(budget) : null,
      max_duration_hours: duration ? Number(duration) : null,
      include_nearby: nearby,
      allow_unreserved: true,
      smart_tickets: smart,
    });
    if (!parsed.success) {
      const next: Record<string, string> = {};
      for (const issue of parsed.error.issues) next[String(issue.path[0] ?? "form")] ??= issue.message;
      if (next.max_budget) setShowMore(true);
      setErrors(next);
      return;
    }
    if (today && date < today) return setErrors({ date: "That date is in the past." });
    if (maxDate && date > maxDate) return setErrors({ date: `Bookings open up to ${formatDay(maxDate)}.` });
    setErrors({});
    const labels = { fromName: origin?.name, toName: destination?.name };
    rememberSearch(parsed.data, labels.fromName ?? parsed.data.origin, labels.toName ?? parsed.data.destination);
    startTransition(() => router.push(`/results?${toQuery(parsed.data, labels)}`));
  }

  const quickDates = today ? [0, 1, 2].map((n) => addDays(today, n)) : [];

  return (
    <form onSubmit={submit} noValidate aria-label="Search trains">
      <Card className="p-4 lg:p-5">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1.5fr)_auto_minmax(0,1.5fr)_minmax(0,0.9fr)_minmax(0,1fr)_auto_auto] lg:items-start">
          <Field label="From" error={errors.origin}>
            <StationInput label="From" value={origin} onChange={setOrigin} placeholder="Station or city, e.g. Delhi" />
          </Field>
          <button
            type="button"
            onClick={() => {
              setOrigin(destination);
              setDestination(origin);
            }}
            className="mx-auto grid h-9 w-9 place-items-center self-center rounded-full bg-wims-green text-white shadow hover:bg-wims-green-dark lg:mt-6"
            aria-label="Swap From and To"
          >
            <ArrowLeftRight className="h-4 w-4 rotate-90 lg:rotate-0" />
          </button>
          <Field label="To" error={errors.destination}>
            <StationInput label="To" value={destination} onChange={setDestination} placeholder="Station or city, e.g. Jaipur" />
          </Field>
          <Field label="Date" error={errors.date}>
            <input
              type="date"
              aria-label="Journey date"
              value={date}
              min={today || undefined}
              max={maxDate}
              onChange={(e) => setChosenDate(e.target.value)}
              className="h-12 w-full bg-transparent text-[15px] text-wims-text focus:outline-none"
            />
          </Field>
          <Field label="Class">
            <select
              value={travelClass}
              onChange={(e) => setTravelClass(e.target.value as TravelClass)}
              className="h-12 w-full bg-transparent text-[15px] text-wims-text focus:outline-none"
              aria-label="Class"
            >
              {TRAVEL_CLASSES.map((c) => (
                <option key={c} value={c}>
                  {c === "ANY" ? "Any class" : `${c} · ${CLASS_NAMES[c]}`}
                </option>
              ))}
            </select>
          </Field>
          <div>
            <span className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-wims-muted">Travellers</span>
            <div className="flex h-[50px] items-center">
              <Stepper value={passengers} min={1} max={6} onChange={setPassengers} label="Travellers" />
            </div>
          </div>
          <button
            type="submit"
            disabled={pending}
            className="flex h-[50px] items-center justify-center gap-2 rounded-md bg-wims-green px-7 text-[15px] font-medium uppercase tracking-wide text-white shadow-sm hover:bg-wims-green-dark disabled:opacity-80 lg:mt-[22px]"
          >
            {pending ? <Spinner className="h-5 w-5" /> : <Search className="h-5 w-5" aria-hidden />}
            {pending ? "Searching…" : "Search"}
          </button>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {quickDates.map((d, i) => (
            <Chip key={d} active={date === d} onClick={() => setChosenDate(d)}>
              {i === 0 ? "Today" : i === 1 ? "Tomorrow" : formatDay(d)}
            </Chip>
          ))}
          {rush && (
            <span className="inline-flex items-center gap-1 rounded-full bg-[#fff1e6] px-2.5 py-1 text-xs font-medium text-[#b34700]">
              <Flame className="h-3.5 w-3.5" aria-hidden /> {rush.name} rush — trains fill up fast
            </span>
          )}
          <button
            type="button"
            onClick={() => setShowMore((v) => !v)}
            aria-expanded={showMore}
            className="ml-auto inline-flex items-center gap-1 text-sm font-medium text-wims-blue"
          >
            More options <ChevronDown className={`h-4 w-4 transition-transform ${showMore ? "rotate-180" : ""}`} />
          </button>
        </div>

        {showMore && (
          <div className="mt-3 grid gap-4 rounded-md bg-[#f6f8fb] p-4 sm:grid-cols-2 xl:grid-cols-4">
            <div>
              <span className="mb-1 block text-xs font-medium text-wims-muted">Changes allowed</span>
              <Segmented
                label="Changes allowed"
                value={transfers}
                onChange={setTransfers}
                options={[
                  { value: 0, label: "None" },
                  { value: 1, label: "1" },
                  { value: 2, label: "2" },
                ]}
              />
            </div>
            <div>
              <span className="mb-1 block text-xs font-medium text-wims-muted">Also search nearby dates</span>
              <Segmented
                label="Flexible dates"
                value={flex}
                onChange={setFlex}
                options={[0, 1, 2, 3].map((n) => ({ value: n, label: n === 0 ? "Off" : `±${n}` }))}
              />
            </div>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-wims-muted">Max budget per person</span>
              <span className="flex h-9 items-center rounded-md border border-wims-hairline bg-white px-2">
                <span className="text-sm text-wims-muted">₹</span>
                <input
                  inputMode="numeric"
                  value={budget}
                  onChange={(e) => setBudget(e.target.value.replace(/[^0-9]/g, ""))}
                  placeholder="No limit"
                  className="w-full bg-transparent px-1 text-sm focus:outline-none"
                />
              </span>
              {errors.max_budget && <span className="mt-1 block text-xs text-wims-late">{errors.max_budget}</span>}
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-wims-muted">Max journey time</span>
              <select value={duration} onChange={(e) => setDuration(e.target.value)} className="h-9 w-full rounded-md border border-wims-hairline bg-white px-2 text-sm">
                {DURATIONS.map((d) => (
                  <option key={d} value={d}>
                    {d ? `${d} hours` : "Any"}
                  </option>
                ))}
              </select>
            </label>
            <div className="sm:col-span-2">
              <Toggle checked={nearby} onChange={setNearby} label="Include nearby stations" hint="Start or end at a station up to ~100 km away and travel there by road." />
            </div>
            <div className="sm:col-span-2">
              <Toggle checked={smart} onChange={setSmart} label="Show backup tickets" hint="Book to a later stop, from the start station, or split one train into two tickets." />
            </div>
          </div>
        )}
      </Card>
    </form>
  );
}

export function SearchFormFallback() {
  return <Card className="h-[140px] animate-pulse" />;
}
