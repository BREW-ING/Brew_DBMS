import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

const relativeTime = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

/** "3 days ago", "2 weeks ago" — coarse age for a timestamp. */
export function formatAge(iso: string, now: Date = new Date()): string {
  const days = Math.round((now.getTime() - new Date(iso).getTime()) / 86_400_000);
  if (days < 1) return "today";
  if (days < 14) return relativeTime.format(-days, "day");
  if (days < 60) return relativeTime.format(-Math.round(days / 7), "week");
  return relativeTime.format(-Math.round(days / 30), "month");
}
