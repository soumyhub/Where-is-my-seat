import { Suspense } from "react";

import { HowItWorks, PopularRoutes, RecentSearches } from "@/components/search/HomeExtras";
import { SearchForm, SearchFormFallback } from "@/components/search/SearchForm";
import { PAGE } from "@/lib/layout";

export default function HomePage() {
  return (
    <main>
      <section className="bg-wims-blue pb-8 pt-8 text-white md:pt-10">
        <div className={PAGE}>
          <h1 className="text-[26px] font-medium leading-tight md:text-[34px]">
            Your train is full. Your journey isn&apos;t over.
          </h1>
          <p className="mt-2 max-w-3xl text-[15px] text-white/80 md:text-base">
            See every direct train for your route from the official Indian Railways timetable — and when yours is
            waitlisted, the backup tickets and other routes worth checking on IRCTC.
          </p>
          <div className="mt-6">
            <Suspense fallback={<SearchFormFallback />}>
              <SearchForm />
            </Suspense>
          </div>
          <div className="mt-4">
            <PopularRoutes />
          </div>
        </div>
      </section>

      <div className={`${PAGE} space-y-8 py-8`}>
        <RecentSearches />
        <HowItWorks />
      </div>
    </main>
  );
}
