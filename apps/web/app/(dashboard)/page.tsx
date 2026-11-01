import Link from "next/link";
import { Inbox } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SuggestionCard } from "@/components/suggestion-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getProfile, getSuggestions } from "@/lib/mock-data";

export default async function SuggestionsPage() {
  const [profile, suggestions] = await Promise.all([getProfile(), getSuggestions()]);

  return (
    <>
      <PageHeader title="Suggestions" description="Project ideas grounded in real problems, ranked for you.">
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          {profile.skills.map((skill) => (
            <Badge key={skill.name} variant="secondary">
              {skill.name}
            </Badge>
          ))}
          <span className="ml-1 text-sm text-muted-foreground">
            team of {profile.teamSize} · {profile.hoursAvailable} hours
          </span>
        </div>
      </PageHeader>

      {suggestions.length > 0 ? (
        <ul className="space-y-4">
          {suggestions.map((suggestion) => (
            <li key={suggestion.id}>
              <SuggestionCard suggestion={suggestion} />
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          icon={Inbox}
          title="No suggestions yet"
          description="Add a few skills and interests to your profile and we'll match you with problems worth solving."
        >
          <Button asChild variant="outline" size="sm">
            <Link href="/profile">Edit profile</Link>
          </Button>
        </EmptyState>
      )}
    </>
  );
}
