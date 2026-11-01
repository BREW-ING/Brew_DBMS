import type { Metadata } from "next";
import Link from "next/link";
import { ChevronLeft, ChevronRight, Inbox } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SignalReviewItem } from "@/components/signal-review-item";
import { sourceLabel } from "@/components/source-badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { LOW_CONFIDENCE } from "@/lib/curator-schema";
import { listSignalsForReview, listSkillNames, type ReviewFilters } from "@/lib/review";
import type { SignalSource } from "@/lib/suggestions";

export const metadata: Metadata = { title: "Review signals" };

const SOURCES: SignalSource[] = ["github", "arxiv", "hn"];
const SKILL_OPTIONS_ID = "skill-options";

type SearchParams = Record<string, string | string[] | undefined>;
type Props = { searchParams: Promise<SearchParams> };

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function parseFilters(params: SearchParams): { filters: ReviewFilters; page: number } {
  const source = first(params.source);
  const page = Number.parseInt(first(params.page) ?? "", 10);
  return {
    filters: {
      source: SOURCES.includes(source as SignalSource) ? (source as SignalSource) : null,
      lowConfidenceOnly: first(params.low) === "1",
      seedOnly: first(params.seed) === "1",
    },
    page: Number.isInteger(page) && page >= 1 ? page : 1,
  };
}

function pageHref(filters: ReviewFilters, page: number): string {
  const params = new URLSearchParams();
  if (filters.source) params.set("source", filters.source);
  if (filters.lowConfidenceOnly) params.set("low", "1");
  if (filters.seedOnly) params.set("seed", "1");
  if (page > 1) params.set("page", String(page));
  const query = params.toString();
  return query ? `/review?${query}` : "/review";
}

export default async function ReviewPage({ searchParams }: Props) {
  const { filters, page } = parseFilters(await searchParams);
  const [result, skillNames] = await Promise.all([listSignalsForReview(filters, page), listSkillNames()]);
  const filtered = filters.source !== null || filters.lowConfidenceOnly || filters.seedOnly;

  return (
    <>
      <PageHeader
        title="Review signals"
        description="Most recently fetched first. Retire low-quality signals and correct their skill tags."
      />

      {/* A plain GET form: filters live in the URL, so they survive refreshes and links. */}
      <form action="/review" className="mb-6 flex flex-wrap items-end gap-x-5 gap-y-3 rounded-xl border p-4">
        <div className="space-y-1.5">
          <Label htmlFor="source">Source</Label>
          <select
            id="source"
            name="source"
            defaultValue={filters.source ?? ""}
            className="h-9 w-40 rounded-md border border-input bg-background px-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            <option value="">All sources</option>
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {sourceLabel(s)}
              </option>
            ))}
          </select>
        </div>
        <label className="flex h-9 items-center gap-2 text-sm">
          <input type="checkbox" name="low" value="1" defaultChecked={filters.lowConfidenceOnly} className="size-4 accent-primary" />
          Low-confidence tags only
          <span className="text-muted-foreground">(avg &lt; {LOW_CONFIDENCE})</span>
        </label>
        <label className="flex h-9 items-center gap-2 text-sm">
          <input type="checkbox" name="seed" value="1" defaultChecked={filters.seedOnly} className="size-4 accent-primary" />
          Seed data only
        </label>
        <div className="flex gap-2">
          <Button type="submit" size="sm">
            Apply
          </Button>
          {filtered ? (
            <Button asChild variant="ghost" size="sm">
              <Link href="/review">Clear</Link>
            </Button>
          ) : null}
        </div>
      </form>

      <datalist id={SKILL_OPTIONS_ID}>
        {skillNames.map((name) => (
          <option key={name} value={name} />
        ))}
      </datalist>

      {result.signals.length > 0 ? (
        <>
          <p className="mb-3 text-sm text-muted-foreground">
            {result.total} signal{result.total === 1 ? "" : "s"} · page {result.page} of {result.pageCount}
          </p>
          <ul className="space-y-3">
            {result.signals.map((signal) => (
              <li key={signal.id}>
                <SignalReviewItem signal={signal} skillOptionsId={SKILL_OPTIONS_ID} />
              </li>
            ))}
          </ul>
          <nav aria-label="Pagination" className="mt-6 flex items-center justify-between gap-2">
            {result.page > 1 ? (
              <Button asChild variant="outline" size="sm">
                <Link href={pageHref(filters, result.page - 1)}>
                  <ChevronLeft aria-hidden />
                  Newer
                </Link>
              </Button>
            ) : (
              <span />
            )}
            {result.page < result.pageCount ? (
              <Button asChild variant="outline" size="sm">
                <Link href={pageHref(filters, result.page + 1)}>
                  Older
                  <ChevronRight aria-hidden />
                </Link>
              </Button>
            ) : null}
          </nav>
        </>
      ) : (
        <EmptyState
          icon={Inbox}
          title={result.total > 0 ? "Past the last page" : "No signals match"}
          description={
            result.total > 0
              ? `There are ${result.total} matching signals, but not this many pages.`
              : filtered
                ? "Try loosening the filters."
                : "Nothing has been ingested yet."
          }
        >
          {result.total > 0 || filtered ? (
            <Button asChild variant="outline" size="sm">
              <Link href={result.total > 0 ? pageHref(filters, 1) : "/review"}>
                {result.total > 0 ? "Go to page 1" : "Clear filters"}
              </Link>
            </Button>
          ) : null}
        </EmptyState>
      )}
    </>
  );
}
