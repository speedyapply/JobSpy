import type { Job, Salary } from "./api";

const DAY = 24 * 60 * 60 * 1000;

function parse(value: string | null): Date | null {
  if (!value) return null;
  // "2026-11-13" is a day; "2026-11-15 20:39:19" or ISO is a moment in local time
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T12:00:00` : value.replace(" ", "T"));
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "hoy", "ayer", "hace 3 días", "hace 2 semanas", "hace más de un mes" */
export function ago(value: string | null, now = new Date()): string | null {
  const date = parse(value);
  if (!date) return null;
  const start = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((start(now) - start(date)) / DAY);
  if (days <= 0) return "hoy";
  if (days === 1) return "ayer";
  if (days < 7) return `hace ${days} días`;
  if (days < 30) {
    const weeks = Math.floor(days / 7);
    return `hace ${weeks} semana${weeks > 1 ? "s" : ""}`;
  }
  return "hace más de un mes";
}

/** "15/11 21:30", for run times */
export function when(value: string | null): string {
  const date = parse(value);
  if (!date) return "—";
  const two = (n: number) => String(n).padStart(2, "0");
  return `${two(date.getDate())}/${two(date.getMonth() + 1)} ${two(date.getHours())}:${two(date.getMinutes())}`;
}

export function shortDate(value: string | null): string | null {
  const date = parse(value);
  if (!date) return null;
  return `${String(date.getDate()).padStart(2, "0")}/${String(date.getMonth() + 1).padStart(2, "0")}`;
}

const PERIODS: Record<string, string> = {
  yearly: "/año",
  monthly: "/mes",
  weekly: "/semana",
  daily: "/día",
  hourly: "/hora",
};

function amount(n: number): string {
  return n.toLocaleString("es-ES", { maximumFractionDigits: Number.isInteger(n) ? 0 : 2, minimumFractionDigits: Number.isInteger(n) ? 0 : 2 });
}

/** "36.000 - 40.000 €/año" */
export function salary(s: Salary | null): string | null {
  if (!s) return null;
  const low = s.min ?? s.max;
  const high = s.max ?? s.min;
  if (low == null || high == null) return null;
  const range = low === high ? amount(low) : `${amount(low)} - ${amount(high)}`;
  const currency = !s.currency || s.currency === "EUR" ? "€" : ` ${s.currency}`;
  return `${range} ${currency}${PERIODS[s.interval ?? ""] ?? ""}`.replace("  ", " ");
}

export function scoreClass(score: number | null): string {
  if (score == null) return "score none";
  return score >= 70 ? "score good" : score >= 45 ? "score fair" : "score poor";
}

export function place(job: Job): string {
  const modality = job.work_from_home_type ?? (job.is_remote ? "Remoto" : null);
  return [job.location, modality].filter(Boolean).join(" · ");
}
