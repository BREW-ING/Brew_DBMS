import { SuggestionCardSkeleton } from "@/components/suggestion-card";
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div role="status" aria-label="Loading suggestions">
      <div className="mb-6 space-y-3 sm:mb-8">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-4 w-72 max-w-full" />
        <div className="flex flex-wrap gap-1.5">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-5 w-20" />
          ))}
        </div>
      </div>
      <div className="space-y-4">
        {Array.from({ length: 3 }, (_, i) => (
          <SuggestionCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}
