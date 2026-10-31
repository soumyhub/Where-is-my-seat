"use client";

import { BellRing } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { PAGE } from "@/lib/layout";
import { useSavedTrips, useWatches } from "@/lib/storage";

import { LogoMark, Wordmark } from "./Logo";

const TABS = [
  { href: "/", label: "Find trains", short: "Trains", match: (p: string) => p === "/" || p.startsWith("/results") || p.startsWith("/journey") },
  { href: "/station", label: "Live station", short: "Live", match: (p: string) => p.startsWith("/station") },
  { href: "/watch", label: "Seat Watch", short: "Watch", match: (p: string) => p.startsWith("/watch") },
  { href: "/saved", label: "Saved", short: "Saved", match: (p: string) => p.startsWith("/saved") },
  { href: "/about", label: "How it works", short: "About", match: (p: string) => p.startsWith("/about") },
];

function Tabs({ pathname, counts }: { pathname: string; counts: Record<string, number> }) {
  return (
    <>
      {TABS.map((tab) => {
        const active = tab.match(pathname);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? "page" : undefined}
            className={`relative flex h-full flex-1 items-center justify-center border-b-[3px] px-1 text-[13px] font-medium uppercase tracking-wide md:flex-none md:px-5 ${
              active ? "border-white text-white" : "border-transparent text-white/70 hover:text-white"
            }`}
          >
            <span className="md:hidden">{tab.short}</span>
            <span className="hidden md:inline">{tab.label}</span>
            {(counts[tab.href] ?? 0) > 0 && (
              <span className="ml-1.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-wims-green px-1 text-[10px] font-bold text-white">
                {counts[tab.href]}
              </span>
            )}
          </Link>
        );
      })}
    </>
  );
}

export function AppHeader() {
  const pathname = usePathname();
  const saved = useSavedTrips().length;
  const watching = useWatches().length;
  const counts = { "/saved": saved, "/watch": watching };
  return (
    <header className="no-print sticky top-0 z-40 bg-wims-blue text-white shadow-[0_2px_4px_rgba(0,0,0,0.25)]">
      <div className={`${PAGE} flex h-14 items-center gap-6 md:h-16`}>
        <Link href="/" className="flex shrink-0 items-center gap-2.5 rounded-md" aria-label="Where is my Seat home">
          <LogoMark className="h-9 w-9" />
          <Wordmark />
        </Link>
        <nav className="hidden h-full md:flex" aria-label="Main">
          <Tabs pathname={pathname} counts={counts} />
        </nav>
        <Link
          href="/watch"
          className="ml-auto grid h-10 w-10 place-items-center rounded-full hover:bg-white/10 md:hidden"
          aria-label={`Seat Watch (${watching})`}
        >
          <BellRing className="h-5 w-5" />
        </Link>
      </div>
      <nav className="flex h-11 md:hidden" aria-label="Main">
        <Tabs pathname={pathname} counts={counts} />
      </nav>
    </header>
  );
}

export function AppHeaderFallback() {
  return (
    <header className="no-print sticky top-0 z-40 bg-wims-blue text-white">
      <div className={`${PAGE} flex h-14 items-center gap-2.5 md:h-16`}>
        <LogoMark className="h-9 w-9" />
        <Wordmark />
      </div>
      <div className="h-11 md:hidden" />
    </header>
  );
}
