import Link from "next/link";

import { ScoreBar } from "@/components/score-bar";
import { SourceBadge } from "@/components/source-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { Suggestion } from "@/lib/mock-data";
import { formatAge } from "@/lib/utils";

export function SuggestionCard({ suggestion }: { suggestion: Suggestion }) {
  return (
    <Card className="relative transition-colors hover:border-foreground/20 focus-within:ring-[3px] focus-within:ring-ring/50">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground">
          <SourceBadge source={suggestion.source} />
          <span className="text-xs" aria-hidden>
            ·
          </span>
          <time className="text-xs" dateTime={suggestion.publishedAt}>
            {formatAge(suggestion.publishedAt)}
          </time>
          <Badge variant="secondary" className="ml-auto">
            {suggestion.topic}
          </Badge>
        </div>
        <CardTitle className="text-base">
          {/* Stretched link: the whole card is clickable, only the title is announced. */}
          <Link
            href={`/suggestions/${suggestion.id}`}
            className="outline-none after:absolute after:inset-0"
          >
            {suggestion.title}
          </Link>
        </CardTitle>
        <p className="text-sm text-muted-foreground">{suggestion.idea}</p>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2 sm:gap-6">
        <ScoreBar label="Relevance" value={suggestion.relevance} />
        <ScoreBar label="Feasibility" value={suggestion.feasibility} />
      </CardContent>
    </Card>
  );
}

export function SuggestionCardSkeleton() {
  return (
    <Card aria-hidden>
      <CardHeader className="gap-3">
        <div className="flex items-center gap-3">
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-4 w-16" />
          <Skeleton className="ml-auto h-5 w-16" />
        </div>
        <Skeleton className="h-5 w-4/5" />
        <Skeleton className="h-4 w-full" />
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2 sm:gap-6">
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-full" />
      </CardContent>
    </Card>
  );
}
