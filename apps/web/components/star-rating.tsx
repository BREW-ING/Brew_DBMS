"use client";

import { useState } from "react";
import { Star } from "lucide-react";

import { cn } from "@/lib/utils";

const labels = ["Not useful", "Meh", "Okay", "Good", "Great idea"] as const;

/** 1-5 star feedback (feedback.rating). Local state only until /api/feedback is wired up. */
export function StarRating({ suggestionTitle }: { suggestionTitle: string }) {
  const [rating, setRating] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const shown = hovered ?? rating ?? 0;

  return (
    <div className="space-y-2">
      <div
        role="group"
        aria-label={`Rate "${suggestionTitle}"`}
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
              onClick={() => setRating(value)}
              onMouseEnter={() => setHovered(value)}
              className="rounded-md p-1.5 outline-none transition-colors hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50"
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
      <p className="h-5 text-sm text-muted-foreground" aria-live="polite">
        {rating ? `Thanks! You rated this ${rating}/5 (${labels[rating - 1]}).` : "How useful is this suggestion?"}
      </p>
    </div>
  );
}
