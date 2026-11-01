import { Handshake } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { Teammate } from "@/lib/mock-data";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((part) => part[0] ?? "")
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function ChipRow({
  label,
  items,
  variant,
}: {
  label: string;
  items: string[];
  variant: "accent" | "secondary";
}) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      {items.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {items.map((item) => (
            <Badge key={item} variant={variant}>
              {item}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">None</p>
      )}
    </div>
  );
}

export function TeammateCard({ teammate }: { teammate: Teammate }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center gap-3">
        <div
          className="flex size-10 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-medium"
          aria-hidden
        >
          {initials(teammate.name)}
        </div>
        <CardTitle>{teammate.name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <ChipRow label="Complementary skills" items={teammate.complementarySkills} variant="accent" />
        <ChipRow label="Shared interests" items={teammate.sharedInterests} variant="secondary" />
        <p className="flex items-start gap-2 border-t pt-3 text-sm text-muted-foreground">
          <Handshake className="mt-0.5 size-4 shrink-0" aria-hidden />
          {teammate.reason}
        </p>
      </CardContent>
    </Card>
  );
}

export function TeammateCardSkeleton() {
  return (
    <Card aria-hidden>
      <CardHeader className="flex-row items-center gap-3">
        <Skeleton className="size-10 rounded-full" />
        <Skeleton className="h-5 w-32" />
      </CardHeader>
      <CardContent className="space-y-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-5 w-3/4" />
      </CardContent>
    </Card>
  );
}
