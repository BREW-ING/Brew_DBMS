"use client";

import { useState } from "react";
import { Star } from "lucide-react";

import { cn } from "@/lib/utils";

const labels = ["Not useful", "Meh", "Okay", "Good", "Great idea"] as const;

/** 1-5 star feedback (feedback.rating), saved through POST /api/feedback. */
export function StarRating({
  suggestionId,
  suggestionTitle,
  initialRating,
}: {
  suggestionId: string;
  suggestionTitle: string;
  initialRating: number | null;
}) {
  const [rating, setRating] = useState<number | null>(initialRating);
  const [hovered, setHovered] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shown = hovered ?? rating ?? 0;

  async function rate(value: number) {
    const previous = rating;
    setRating(value);
    setError(null);
    setSaving(true);
    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ suggestionId, rating: value }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch {
      setRating(previous);
      setError("Couldn't save your rating. Try again in a moment.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-2">
      <div
        role="group"
        aria-label={`Rate "${suggestionTitle}"`}
        aria-busy={saving}
        className="flex items-center gap-1"
        onMouseLeave={() => setHovered(null)}
      >
        {labels.map((label, i) => {
          const value = i + 1;
          return (
            <button
              key={value}
              type="button"
              aria-label={`${value} star${value > 1 ? "s" : ""}: ${label}`}
              aria-pressed={rating === value}
              disabled={saving}
              onClick={() => rate(value)}
              onMouseEnter={() => setHovered(value)}
              className="rounded-md p-1.5 outline-none transition-colors hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-70"
            >
              <Star
                className={cn(
                  "size-6 transition-colors",
                  value <= shown ? "fill-primary text-primary" : "text-muted-foreground/50",
                )}
                aria-hidden
              />
            </button>
          );
        })}
      </div>
      <p
        className={cn("h-5 text-sm", error ? "text-destructive" : "text-muted-foreground")}
        aria-live="polite"
      >
        {error ??
          (rating ? `Thanks! You rated this ${rating}/5 (${labels[rating - 1]}).` : "How useful is this suggestion?")}
      </p>
    </div>
  );
}
