import Link from "next/link";
import { redirect } from "next/navigation";
import { Inbox, UserPen } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SuggestionCard } from "@/components/suggestion-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { auth } from "@/lib/auth";
import { getProfile } from "@/lib/profile";
import { getSuggestionsForUser } from "@/lib/suggestions";

export default async function SuggestionsPage() {
  const session = await auth();
  if (!session) redirect("/login");
  const userId = session.user.id;

  const [profile, result] = await Promise.all([getProfile(userId), getSuggestionsForUser(userId)]);
  if (!profile) redirect("/login");

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

      {result.status === "profile_incomplete" ? (
        <EmptyState
          icon={UserPen}
          title="Complete your profile"
          description="Add your skills and interests so we can match you with problems worth solving."
        >
          <Button asChild variant="outline" size="sm">
            <Link href="/profile">Edit profile</Link>
          </Button>
        </EmptyState>
      ) : result.suggestions.length > 0 ? (
        <ul className="space-y-4">
          {result.suggestions.map((suggestion) => (
            <li key={suggestion.id}>
              <SuggestionCard suggestion={suggestion} />
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          icon={Inbox}
          title="No suggestions yet"
          description="There are no fresh problem signals close to your profile right now. Try broadening your skills and interests, or check back after the next ingestion run."
        >
          <Button asChild variant="outline" size="sm">
            <Link href="/profile">Edit profile</Link>
          </Button>
        </EmptyState>
      )}
    </>
  );
}
