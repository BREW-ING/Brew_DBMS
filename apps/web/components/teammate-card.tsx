import { Handshake } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { Teammate } from "@/lib/teammates";

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

/** Collaboration path that surfaced this match. */
function reason(teammate: Teammate): string {
  if (teammate.pastCollaborator) return "You've built a project together before";
  if (teammate.twoHop) return `Worked with ${teammate.mutualCollaborators.join(", ")}, who you've collaborated with`;
  return "Matched on complementary skills";
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
        <div className="min-w-0 flex-1 space-y-1">
          <CardTitle>{teammate.name}</CardTitle>
          {teammate.twoHop ? <Badge variant="outline">2-hop collaborator</Badge> : null}
        </div>
        <div className="text-right">
          <p className="text-lg font-semibold tabular-nums">{teammate.score.toFixed(1)}</p>
          <p className="text-xs text-muted-foreground">score</p>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <ChipRow label="Complementary skills" items={teammate.complementarySkills} variant="accent" />
        <ChipRow label="Shared interests" items={teammate.sharedInterests} variant="secondary" />
        <p className="flex items-start gap-2 border-t pt-3 text-sm text-muted-foreground">
          <Handshake className="mt-0.5 size-4 shrink-0" aria-hidden />
          {reason(teammate)}
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
