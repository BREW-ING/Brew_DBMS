import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Unplug, Users } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { TeammateCard } from "@/components/teammate-card";
import { Button } from "@/components/ui/button";
import { auth } from "@/lib/auth";
import { getTeammatesForUser } from "@/lib/teammates";

export const metadata: Metadata = { title: "Teammates" };

export default async function TeammatesPage() {
  const session = await auth();
  if (!session) redirect("/login");

  const result = await getTeammatesForUser(session.user.id);

  return (
    <>
      <PageHeader
        title="Teammates"
        description="People whose skills complement yours, found through shared interests and past collaborations."
      />

      {result.status === "graph_unavailable" ? (
        <EmptyState
          icon={Unplug}
          title="Teammate matching is offline"
          description="We can't reach the collaboration graph right now. Your suggestions still work — try this page again in a few minutes."
        />
      ) : result.teammates.length > 0 ? (
        <ul className="grid gap-4 sm:grid-cols-2">
          {result.teammates.map((teammate) => (
            <li key={teammate.userId}>
              <TeammateCard teammate={teammate} />
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          icon={Users}
          title="No teammate matches yet"
          description="Add skills and interests to your profile so we can find people who complement you."
        >
          <Button asChild variant="outline" size="sm">
            <Link href="/profile">Edit profile</Link>
          </Button>
        </EmptyState>
      )}
    </>
  );
}
