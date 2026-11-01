import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div role="status" aria-label="Loading profile" className="max-w-2xl">
      <div className="mb-6 space-y-3 sm:mb-8">
        <Skeleton className="h-8 w-28" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <Card aria-hidden>
        <CardContent className="space-y-8">
          <div className="space-y-3">
            <Skeleton className="h-5 w-16" />
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="flex gap-2">
                <Skeleton className="h-9 flex-1" />
                <Skeleton className="h-9 w-32 sm:w-40" />
                <Skeleton className="size-9" />
              </div>
            ))}
          </div>
          <div className="space-y-3">
            <Skeleton className="h-5 w-20" />
            <Skeleton className="h-9 w-full" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
