"use client";

import "leaflet/dist/leaflet.css";

import type { Map as LeafletMap } from "leaflet";
import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { JourneyMap } from "@/lib/types";

import { Spinner } from "../ui";

/* Train path on an OpenStreetMap base map. Train legs follow the real track where the
   OpenStreetMap railway data allows (solid blue); gaps and road legs are dashed. */

const TRAIN = "#1b63a7"; // wims-blue
const GUESS = "#7f9cc0";
const ROAD = "#757575";
const BOARD = "#699535"; // wims-origin
const ALIGHT = "#e6430a"; // wims-dest

export function RouteMap({ journeyId }: { journeyId: string }) {
  const box = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<JourneyMap | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .journeyMap(journeyId, controller.signal)
      .then(setData)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e instanceof ApiError ? e.message : "Could not load the map.");
      });
    return () => controller.abort();
  }, [journeyId]);

  useEffect(() => {
    if (!data?.bounds || !box.current) return;
    let map: LeafletMap | null = null;
    let cancelled = false;
    void import("leaflet").then((L) => {
      if (cancelled || !box.current) return;
      map = L.map(box.current, { scrollWheelZoom: false, attributionControl: true });
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(map);
      for (const leg of data.legs) {
        for (const seg of leg.segments) {
          const road = leg.kind === "road";
          L.polyline(seg.points, {
            color: road ? ROAD : seg.matched ? TRAIN : GUESS,
            weight: road ? 3 : 4,
            opacity: 0.9,
            dashArray: road || !seg.matched ? "6 6" : undefined,
          })
            .bindTooltip(road ? "By road (estimate)" : `${leg.train_number} ${leg.train_name ?? ""}`, { sticky: true })
            .addTo(map);
        }
        for (const s of leg.stops) {
          const end = s.role === "board" || s.role === "alight";
          L.circleMarker([s.lat, s.lon], {
            radius: end ? 7 : 4,
            color: "#fff",
            weight: 2,
            fillColor: s.role === "board" ? BOARD : s.role === "alight" ? ALIGHT : s.role === "road" ? ROAD : TRAIN,
            fillOpacity: 1,
          })
            .bindTooltip(`${s.name} (${s.code})`, { direction: "top", permanent: end && data.legs.length <= 2 })
            .addTo(map);
        }
      }
      map.fitBounds(data.bounds!, { padding: [28, 28] });
      map.attributionControl.addAttribution("Railway lines: OpenStreetMap (ODbL)");
    });
    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [data]);

  if (error) return <p className="text-[13px] text-wims-late">{error}</p>;
  return (
    <div>
      <div className="relative h-72 overflow-hidden rounded-md border border-wims-hairline bg-[#e8eef5] md:h-80">
        {!data && (
          <div className="absolute inset-0 grid place-items-center">
            <Spinner />
          </div>
        )}
        <div ref={box} className="h-full w-full" aria-label="Map of the route" role="img" />
      </div>
      {data && (
        <p className="mt-1.5 text-[11.5px] text-wims-muted">
          {data.track_share >= 0.95
            ? "Drawn along the real railway line."
            : data.track_share > 0
              ? `About ${Math.round(data.track_share * 100)}% follows the real railway line; dashed parts are straight lines between stops.`
              : "Straight lines between stops — the track for this route isn't in our map data."}{" "}
          {data.legs.some((l) => l.kind === "road") && "Grey dashes: by road (estimate)."}
        </p>
      )}
    </div>
  );
}
