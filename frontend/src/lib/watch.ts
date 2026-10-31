import { addDays, formatFullDate, istToEpoch, todayInIndia } from "./format";
import type { Watch, WatchCheck } from "./storage";

/* Seat Watch helpers: how a waitlist is moving, worked out only from the checks saved in
   this browser. Nothing here is a prediction from Indian Railways. */

const DAY = 86_400_000;

export type Trend = { text: string; tone: "good" | "bad" | "flat" | "none" };

export function statusLabel(check: Pick<WatchCheck, "status" | "count">): string {
  const n = check.count;
  switch (check.status) {
    case "CONFIRMED":
      return n != null ? `AVL ${n}` : "Available";
    case "RAC":
      return n != null ? `RAC ${n}` : "RAC";
    case "WAITLISTED":
      return n != null ? `WL ${n}` : "Waitlist";
    default:
      return "Regret / not available";
  }
}

/** Departure as epoch ms (start of the journey date in India), for "days left". */
export function departureEpoch(watch: Pick<Watch, "journey_date">): number {
  return istToEpoch(`${watch.journey_date}T00:00`);
}

export function watchTrend(watch: Watch, now: number): Trend {
  const history = watch.history;
  const last = history[history.length - 1];
  if (!last) return { text: "No checks yet. Check on IRCTC and note what you see, or check live.", tone: "none" };
  if (last.status === "CONFIRMED") return { text: "Seats are showing — book on IRCTC soon, they can go fast.", tone: "good" };
  if (last.status === "UNAVAILABLE") {
    return { text: "Regret / not available. Try the backup tickets or another train.", tone: "bad" };
  }
  if (last.status === "RAC") return { text: "RAC: you can travel on a shared berth, and it may still confirm.", tone: "flat" };

  // Waitlist: compare the earliest and latest WL readings of the last 10 days.
  const wl = history.filter((c) => c.status === "WAITLISTED" && c.count != null && c.at >= last.at - 10 * DAY);
  const first = wl[0];
  if (!first || wl.length < 2 || last.at - first.at < 3_600_000 || last.count == null || first.count == null) {
    return { text: "Check again in a few hours to see how the waitlist moves.", tone: "none" };
  }
  const days = (last.at - first.at) / DAY;
  const moved = first.count - last.count;
  const span = days < 1 ? `${Math.max(1, Math.round(days * 24))} h` : `${Math.round(days)} day${Math.round(days) === 1 ? "" : "s"}`;
  if (moved <= 0) {
    return {
      text:
        moved === 0
          ? `WL ${last.count} has not moved in ${span}. Keep a backup ticket ready.`
          : `The waitlist went up from WL ${first.count} to WL ${last.count} in ${span}. Keep a backup ticket ready.`,
      tone: "bad",
    };
  }
  const perDay = moved / days;
  const clearsAt = last.at + (last.count / perDay) * DAY;
  const departs = departureEpoch(watch);
  const pace = `WL ${first.count} → WL ${last.count} in ${span} (about ${perDay >= 1 ? Math.round(perDay) : perDay.toFixed(1)} a day).`;
  if (clearsAt <= departs) {
    return { text: `${pace} At this pace it would clear around ${formatFullDate(todayInIndia(clearsAt))}.`, tone: "good" };
  }
  if (now > departs) return { text: pace, tone: "flat" };
  return { text: `${pace} At this pace it may not clear before the train leaves — keep a backup.`, tone: "flat" };
}

/** An .ics file with a daily 9 am reminder to re-check, until the day before the journey. */
export function reminderCalendar(watch: Watch, now: number, appUrl: string): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const stamp = (ms: number) => {
    const d = new Date(ms);
    return `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}00Z`;
  };
  const departs = departureEpoch(watch);
  const events: string[] = [];
  let day = istToEpoch(`${addDays(todayInIndia(now), 1)}T09:00`);
  const summary = `Check seats: ${watch.train_number} ${watch.from_code}→${watch.to_code} ${watch.travel_class}`;
  while (day < departs && events.length < 14) {
    events.push(
      [
        "BEGIN:VEVENT",
        `UID:${watch.id.replace(/\|/g, "-")}-${day}@whereismyseat`,
        `DTSTAMP:${stamp(now)}`,
        `DTSTART:${stamp(day)}`,
        `DTEND:${stamp(day + 15 * 60_000)}`,
        `SUMMARY:${summary}`,
        `DESCRIPTION:${watch.train_name}\\, ${formatFullDate(watch.journey_date)}. Open Seat Watch: ${appUrl}`,
        "BEGIN:VALARM",
        "TRIGGER:PT0M",
        "ACTION:DISPLAY",
        `DESCRIPTION:${summary}`,
        "END:VALARM",
        "END:VEVENT",
      ].join("\r\n"),
    );
    day += DAY;
  }
  return ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Where is my Seat//Seat Watch//EN", ...events, "END:VCALENDAR", ""].join(
    "\r\n",
  );
}
