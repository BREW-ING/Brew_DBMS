import { TeammateCardSkeleton } from "@/components/teammate-card";
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div role="status" aria-label="Loading teammates">
      <div className="mb-6 space-y-3 sm:mb-8">
        <Skeleton className="h-8 w-36" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <TeammateCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}
