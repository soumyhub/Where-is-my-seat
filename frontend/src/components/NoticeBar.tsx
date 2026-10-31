"use client";

import { FlaskConical, Info } from "lucide-react";
import Link from "next/link";

import { useMeta } from "@/lib/hooks";
import { PAGE } from "@/lib/layout";

/* One calm line that says what the data is. Until the API answers, assume the most
   cautious message: seats are not live. */
export function NoticeBar() {
  const notice = useMeta().data?.data_notice;
  if (notice?.mode === "live") return null;
  const demo = notice?.mode === "demo";
  return (
    <div role="status" className="no-print border-b border-[#e5c45a] bg-[#fff6d6] text-[#4a3500]">
      <div className={`${PAGE} flex flex-wrap items-center gap-x-3 gap-y-0.5 py-1.5 text-[12.5px]`}>
        <span className="flex items-center gap-1.5 font-medium">
          {demo ? <FlaskConical className="h-4 w-4" aria-hidden /> : <Info className="h-4 w-4" aria-hidden />}
          {demo
            ? notice?.label
            : notice?.live_checks
              ? "Search results don't show seats — tap Check live seats on a ticket, and confirm on IRCTC before you book."
              : "Seat availability isn't live here — always check seats on IRCTC before you book."}
        </span>
        {!demo && (
          <span className="hidden text-[#4a3500]/80 lg:inline">
            Trains & timings: Indian Railways &ldquo;Trains at a Glance 2026&rdquo; (main halts).
          </span>
        )}
        <Link href="/about#data" className="ml-auto font-medium underline underline-offset-2">
          About the data
        </Link>
      </div>
    </div>
  );
}
