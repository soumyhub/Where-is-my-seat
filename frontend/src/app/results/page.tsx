import type { Metadata } from "next";
import { Suspense } from "react";

import { ResultsFallback, ResultsView } from "@/components/results/ResultsView";

export const metadata: Metadata = { title: "Journey options" };

export default function ResultsPage() {
  return (
    <Suspense fallback={<ResultsFallback />}>
      <ResultsView />
    </Suspense>
  );
}
