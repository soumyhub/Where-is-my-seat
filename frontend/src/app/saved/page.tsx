import type { Metadata } from "next";

import { SavedTrips } from "@/components/journey/SavedTrips";

export const metadata: Metadata = { title: "Saved journeys" };

export default function SavedPage() {
  return <SavedTrips />;
}
