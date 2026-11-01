import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Check, ExternalLink, X } from "lucide-react";

import { ScoreBar } from "@/components/score-bar";
import { SourceBadge, sourceLabel } from "@/components/source-badge";
import { StarRating } from "@/components/star-rating";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getProfile, getSuggestion, getSuggestions, matchSkills } from "@/lib/mock-data";
import { formatAge } from "@/lib/utils";

type Props = { params: Promise<{ id: string }> };

export async function generateStaticParams(): Promise<{ id: string }[]> {
  const suggestions = await getSuggestions();
  return suggestions.map((s) => ({ id: s.id }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const suggestion = await getSuggestion((await params).id);
  return { title: suggestion?.title ?? "Suggestion not found" };
}

export default async function SuggestionDetailPage({ params }: Props) {
  const { id } = await params;
  const [suggestion, profile] = await Promise.all([getSuggestion(id), getProfile()]);
  if (!suggestion) notFound();

  const { have, missing } = matchSkills(suggestion.requiredSkills, profile.skills);

  return (
    <article className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-3 text-muted-foreground">
        <Link href="/">
          <ArrowLeft />
          All suggestions
        </Link>
      </Button>

      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground">
          <SourceBadge source={suggestion.source} />
          <span className="text-xs" aria-hidden>
            ·
          </span>
          <time className="text-xs" dateTime={suggestion.publishedAt}>
            {formatAge(suggestion.publishedAt)}
          </time>
          <Badge variant="secondary">{suggestion.topic}</Badge>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-balance">{suggestion.title}</h1>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
        <div className="space-y-6">
          <section className="rounded-xl border-l-2 border-primary bg-primary/5 px-4 py-3">
            <h2 className="text-xs font-medium tracking-wide text-primary uppercase">Project idea</h2>
            <p className="mt-1">{suggestion.idea}</p>
          </section>

          <section className="space-y-2">
            <h2 className="font-medium">The problem</h2>
            <p className="leading-relaxed whitespace-pre-line text-muted-foreground">{suggestion.rawText}</p>
            <a
              href={suggestion.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm text-primary underline-offset-4 hover:underline"
            >
              View original on {sourceLabel(suggestion.source)}
              <ExternalLink className="size-3.5" aria-hidden />
            </a>
          </section>

          <section className="space-y-2 border-t pt-6">
            <h2 className="font-medium">Was this useful?</h2>
            <StarRating suggestionTitle={suggestion.title} />
          </section>
        </div>

        <aside className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Match</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <ScoreBar label="Relevance" value={suggestion.relevance} />
              <ScoreBar label="Feasibility" value={suggestion.feasibility} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Skills</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <SkillList title="You have" skills={have} kind="have" />
              <SkillList title="Missing" skills={missing} kind="missing" />
            </CardContent>
          </Card>
        </aside>
      </div>
    </article>
  );
}

function SkillList({
  title,
  skills,
  kind,
}: {
  title: string;
  skills: string[];
  kind: "have" | "missing";
}) {
  const Icon = kind === "have" ? Check : X;
  return (
    <div className="space-y-1.5">
      <h3 className="text-xs text-muted-foreground">
        {title} ({skills.length})
      </h3>
      {skills.length > 0 ? (
        <ul className="space-y-1">
          {skills.map((skill) => (
            <li key={skill} className="flex items-center gap-2 text-sm">
              <Icon
                className={kind === "have" ? "size-4 text-primary" : "size-4 text-muted-foreground"}
                aria-hidden
              />
              {skill}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">
          {kind === "have" ? "None of the required skills yet." : "Nothing — you're fully covered."}
        </p>
      )}
    </div>
  );
}
