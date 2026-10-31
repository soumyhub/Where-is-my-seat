import type { Metadata, Viewport } from "next";
import { Roboto, Roboto_Mono } from "next/font/google";
import { Suspense } from "react";

import { AppHeader, AppHeaderFallback } from "@/components/AppHeader";
import { NoticeBar } from "@/components/NoticeBar";
import { PAGE } from "@/lib/layout";

import "./globals.css";

const roboto = Roboto({
  variable: "--font-roboto",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
});

const robotoMono = Roboto_Mono({
  variable: "--font-roboto-mono",
  subsets: ["latin"],
  weight: ["500"],
});

export const metadata: Metadata = {
  title: {
    default: "Where is my Seat — every train, and a plan B when yours is full",
    template: "%s · Where is my Seat",
  },
  description:
    "Every direct train between two stations from the official Indian Railways timetable, plus backup tickets and other routes for when your train is waitlisted.",
  applicationName: "Where is my Seat",
};

export const viewport: Viewport = {
  themeColor: "#1b63a7",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-IN" className={`${roboto.variable} ${robotoMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <Suspense fallback={<AppHeaderFallback />}>
          <AppHeader />
        </Suspense>
        <NoticeBar />
        <div className="flex-1">{children}</div>
        <footer className={`no-print ${PAGE} py-6 text-center text-xs text-wims-muted`}>
          Where is my Seat is independent and not affiliated with Indian Railways, IRCTC or the Where is my Train
          app. Timetable: Trains at a Glance 2026 (Railway Board). We never book tickets or take payments.
        </footer>
      </body>
    </html>
  );
}
