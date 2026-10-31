"use client";

import { MapPin, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { Place } from "@/lib/types";

import { CodeBadge, Spinner } from "../ui";

type Lookup = { query: string; places: Place[]; error: string | null };

export function StationInput({
  label,
  value,
  onChange,
  placeholder,
  error,
}: {
  label: string;
  value: Place | null;
  onChange: (place: Place | null) => void;
  placeholder: string;
  error?: string;
}) {
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState(value?.name ?? "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [lookup, setLookup] = useState<Lookup>({ query: "", places: [], error: null });
  const [shownValue, setShownValue] = useState<Place | null>(value);

  // Keep the visible text in sync when the parent swaps or resets the value.
  if (value !== shownValue) {
    setShownValue(value);
    setText(value?.name ?? "");
  }

  const query = text.trim();
  const searching = open && query.length >= 2 && lookup.query !== query;

  useEffect(() => {
    if (!open || query.length < 2 || (value && value.name === text)) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api
        .stations(query, controller.signal)
        .then((places) => setLookup({ query, places, error: null }))
        .catch((err: unknown) => {
          if (controller.signal.aborted) return;
          const message = err instanceof ApiError ? err.message : "Couldn't load stations.";
          setLookup({ query, places: [], error: message });
        });
    }, 160);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [open, query, text, value]);

  const places = lookup.query === query ? lookup.places : [];
  const noMatch = open && !value && query.length >= 2 && lookup.query === query && !lookup.error && places.length === 0;
  const listId = `${id}-list`;

  function choose(place: Place) {
    onChange(place);
    setOpen(false);
  }

  return (
    <div className="relative">
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <div className="flex min-h-12 items-center gap-2">
        {value ? (
          <CodeBadge code={value.code ?? "ALL"} tone={value.kind === "city" ? "city" : "badge"} />
        ) : (
          <MapPin className="h-4 w-4 shrink-0 text-[#9e9e9e]" aria-hidden />
        )}
        <input
          ref={inputRef}
          id={id}
          role="combobox"
          aria-expanded={open && (places.length > 0 || !!lookup.error)}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-invalid={!!error}
          aria-activedescendant={open && places[active] ? `${listId}-${active}` : undefined}
          autoComplete="off"
          spellCheck={false}
          value={text}
          placeholder={placeholder}
          onChange={(e) => {
            setText(e.target.value);
            setOpen(true);
            setActive(0);
            if (value) onChange(null);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setActive((a) => Math.min(a + 1, Math.max(places.length - 1, 0)));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter" && open && places[active]) {
              e.preventDefault();
              choose(places[active]);
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
          className="min-w-0 flex-1 bg-transparent py-2 text-[16px] text-wims-text placeholder:text-[#9e9e9e] focus:outline-none"
        />
        {searching && <Spinner className="h-4 w-4 text-wims-badge" />}
        {text && (
          <button
            type="button"
            onClick={() => {
              setText("");
              onChange(null);
              inputRef.current?.focus();
            }}
            className="grid h-8 w-8 place-items-center rounded-full text-[#424242] hover:bg-black/5"
            aria-label={`Clear ${label}`}
          >
            <X className="h-[18px] w-[18px]" />
          </button>
        )}
      </div>
      {error && <p className="pb-1 text-xs text-wims-late">{error}</p>}
      {noMatch && (
        <div
          role="status"
          className="absolute left-0 right-0 top-full z-30 mt-1 rounded-md border border-wims-hairline bg-white px-3 py-2.5 text-sm shadow-lg"
        >
          <p className="font-medium text-wims-text">No station called &ldquo;{query}&rdquo;</p>
          <p className="mt-0.5 text-xs text-wims-muted">
            Try the city name (Delhi, Mumbai, Patna), the station code (NDLS, CSMT) or an old name like Mughalsarai. We
            cover the main halts in the official timetable, so some small stations are missing.
          </p>
        </div>
      )}
      {open && (places.length > 0 || lookup.error) && (
        <ul
          id={listId}
          role="listbox"
          className="absolute left-0 right-0 top-full z-30 mt-1 max-h-80 overflow-auto rounded-md border border-wims-hairline bg-white py-1 shadow-lg"
        >
          {lookup.error && <li className="px-3 py-2 text-sm text-wims-late">{lookup.error}</li>}
          {places.map((place, i) => (
            <li
              key={place.key}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              aria-label={`${place.name}, ${place.subtitle}`}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(place);
              }}
              onMouseEnter={() => setActive(i)}
              className={`flex cursor-pointer items-center gap-3 px-3 py-2 ${i === active ? "bg-[#eaf3fb]" : ""}`}
            >
              <CodeBadge code={place.code ?? "ALL"} tone={place.kind === "city" ? "city" : "badge"} />
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-wims-text">{place.name}</span>
                <span className={`block truncate text-xs ${place.served ? "text-wims-muted" : "text-[#9a5a00]"}`}>
                  {place.subtitle}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
