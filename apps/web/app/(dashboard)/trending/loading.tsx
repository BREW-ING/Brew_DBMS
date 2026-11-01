import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const widths = ["w-full", "w-11/12", "w-4/5", "w-3/5", "w-1/2", "w-2/5", "w-1/3", "w-1/5"];

export default function Loading() {
  return (
    <div role="status" aria-label="Loading trending topics">
      <div className="mb-6 space-y-3 sm:mb-8">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
      <Card aria-hidden>
        <CardHeader>
          <Skeleton className="h-4 w-44" />
        </CardHeader>
        <CardContent className="space-y-4">
          {widths.map((w) => (
            <div key={w} className="flex items-center gap-3">
              <Skeleton className="h-4 w-24 shrink-0" />
              <Skeleton className={`h-4 ${w}`} />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
