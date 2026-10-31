import type { Metadata } from "next";

import { SeatWatch } from "@/components/watch/SeatWatch";

export const metadata: Metadata = { title: "Seat Watch" };

export default function WatchPage() {
  return <SeatWatch />;
}
