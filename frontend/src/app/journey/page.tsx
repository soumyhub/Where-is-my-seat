import type { Metadata } from "next";
import { Suspense } from "react";

import { JourneyDetail, JourneyFallback } from "@/components/journey/JourneyDetail";

export const metadata: Metadata = { title: "Journey" };

export default function JourneyPage() {
  return (
    <Suspense fallback={<JourneyFallback />}>
      <JourneyDetail />
    </Suspense>
  );
}
