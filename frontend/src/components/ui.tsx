"use client";

import { CircleAlert, LoaderCircle, Minus, Plus, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

import { STATUS_META } from "@/lib/format";
import type { Availability, OverallStatus } from "@/lib/types";

/* ----- WIMT-style badges ------------------------------------------------ */

export function CodeBadge({ code, tone = "badge" }: { code: string; tone?: "badge" | "muted" | "city" }) {
  const cls =
    tone === "muted" ? "bg-[#b1b1b1]" : tone === "city" ? "bg-wims-navy" : "bg-wims-badge";
  return (
    <span className={`inline-flex min-w-9 justify-center rounded-[3px] px-1.5 py-px font-mono text-[11px] font-medium leading-4 text-white ${cls}`}>
      {code}
    </span>
  );
}

export function TrainBadge({ number, simulated }: { number: string; simulated?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="rounded-[3px] bg-wims-sky px-1.5 py-px font-mono text-[12px] font-medium leading-[18px] text-white">
        {number}
      </span>
      {simulated && <SimTag />}
    </span>
  );
}

export function SimTag({ title = "Simulated demo data — not live" }: { title?: string }) {
  return (
    <span
      title={title}
      className="rounded-[3px] border border-[#d9a400] bg-wims-sim px-1 text-[9.5px] font-bold leading-[14px] tracking-wider text-wims-sim-ink"
    >
      SIM
    </span>
  );
}

export function StatusPill({
  status,
  availability,
  size = "md",
}: {
  status: OverallStatus;
  availability?: Availability | null;
  size?: "sm" | "md";
}) {
  const meta = STATUS_META[status];
  const label = availability?.label ?? (status === "UNRESERVED" ? "UR · no seat guarantee" : meta.label);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ring-1 ring-inset ${meta.tone} ${
        size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs"
      }`}
      title={availability ? `${availability.display} · ${availability.source}` : meta.label}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} aria-hidden />
      <span className="tabular">{label}</span>
      {availability?.is_simulated && <span className="text-[9.5px] font-bold tracking-wider opacity-80">SIM</span>}
    </span>
  );
}

/* ----- form controls ----------------------------------------------------- */

export function Chip({
  active,
  onClick,
  children,
  title,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      title={title}
      className={`inline-flex min-h-9 items-center gap-1 rounded-full border px-3 text-[13px] font-medium transition-colors ${
        active
          ? "border-wims-blue bg-wims-blue text-white"
          : "border-wims-hairline bg-white text-wims-text hover:border-wims-badge"
      }`}
    >
      {children}
    </button>
  );
}

export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex overflow-hidden rounded-md border border-wims-hairline bg-white">
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={`min-h-9 min-w-11 border-r border-wims-hairline px-3 text-[13px] font-medium last:border-r-0 ${
            o.value === value ? "bg-wims-blue text-white" : "text-wims-text hover:bg-[#f5f8fc]"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 py-1.5">
      <span className="relative mt-0.5 inline-flex shrink-0">
        <input type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span className="h-5 w-9 rounded-full bg-[#bdbdbd] transition-colors peer-checked:bg-wims-green" />
        <span className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform peer-checked:translate-x-4" />
      </span>
      <span>
        <span className="block text-sm font-medium text-wims-text">{label}</span>
        {hint && <span className="block text-xs text-wims-muted">{hint}</span>}
      </span>
    </label>
  );
}

export function Stepper({
  value,
  min,
  max,
  onChange,
  label,
}: {
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
  label: string;
}) {
  return (
    <div className="inline-flex items-center rounded-md border border-wims-hairline bg-white" role="group" aria-label={label}>
      <button
        type="button"
        className="grid h-9 w-9 place-items-center text-wims-blue disabled:text-[#bdbdbd]"
        onClick={() => onChange(Math.max(min, value - 1))}
        disabled={value <= min}
        aria-label={`Fewer ${label.toLowerCase()}`}
      >
        <Minus className="h-4 w-4" />
      </button>
      <span className="tabular w-8 text-center text-sm font-medium" aria-live="polite">
        {value}
      </span>
      <button
        type="button"
        className="grid h-9 w-9 place-items-center text-wims-blue disabled:text-[#bdbdbd]"
        onClick={() => onChange(Math.min(max, value + 1))}
        disabled={value >= max}
        aria-label={`More ${label.toLowerCase()}`}
      >
        <Plus className="h-4 w-4" />
      </button>
    </div>
  );
}

/* ----- states ------------------------------------------------------------ */

export function Spinner({ className = "h-5 w-5" }: { className?: string }) {
  return <LoaderCircle className={`animate-spin ${className}`} aria-hidden />;
}

export function ErrorState({
  title,
  message,
  hint,
  onRetry,
  action,
}: {
  title: string;
  message: string;
  hint?: string | null;
  onRetry?: () => void;
  action?: ReactNode;
}) {
  return (
    <div role="alert" className="rounded-md border border-[#f1aca7] bg-white p-5 shadow-sm">
      <div className="flex items-start gap-3">
        <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-wims-late" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="font-medium text-wims-text">{title}</h2>
          <p className="mt-1 text-sm text-wims-text">{message}</p>
          {hint && <p className="mt-1 text-sm text-wims-muted">{hint}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1.5 rounded bg-wims-green px-3 py-2 text-sm font-medium text-white hover:bg-wims-green-dark"
              >
                <RefreshCw className="h-4 w-4" /> Try again
              </button>
            )}
            {action}
          </div>
        </div>
      </div>
    </div>
  );
}

export function Card({ children, className = "" }: { children?: ReactNode; className?: string }) {
  return (
    <div className={`rounded-[3px] bg-white text-wims-text shadow-[0_1px_2px_rgba(0,0,0,0.12)] ${className}`}>{children}</div>
  );
}
