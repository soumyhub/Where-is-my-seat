"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import { api } from "./api";
import type { Meta } from "./types";

/* A shared, minute-resolution clock. Reading Date.now() during render is impure, so
   components subscribe to this store instead. */
let nowValue = 0;
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;

function subscribeClock(callback: () => void) {
  listeners.add(callback);
  if (!timer) {
    nowValue = Date.now();
    timer = setInterval(() => {
      nowValue = Date.now();
      listeners.forEach((l) => l());
    }, 30000);
  }
  return () => {
    listeners.delete(callback);
    if (!listeners.size && timer) {
      clearInterval(timer);
      timer = null;
    }
  };
}

export function useNow(): number {
  return useSyncExternalStore(
    subscribeClock,
    () => nowValue || (nowValue = Date.now()),
    () => 0,
  );
}

const noopSubscribe = () => () => {};

/** False during server render and hydration, true once running in the browser. */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
}

export type Loadable<T> = { data: T | null; error: Error | null };

export function useMeta(): Loadable<Meta> {
  const [state, setState] = useState<Loadable<Meta>>({ data: null, error: null });
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = (attempt: number) => {
      api
        .meta()
        .then((data) => alive && setState({ data, error: null }))
        .catch((error: Error) => {
          if (!alive) return;
          if (attempt < 4) timer = setTimeout(() => load(attempt + 1), 1500 * attempt);  // backend may be starting
          else setState({ data: null, error });
        });
    };
    load(1);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);
  return state;
}
