import type { Metadata } from "next";
import { Suspense } from "react";

import { StationBoardView } from "@/components/station/StationBoard";

export const metadata: Metadata = { title: "Live station board" };

export default function StationPage() {
  return (
    <Suspense fallback={null}>
      <StationBoardView />
    </Suspense>
  );
}
