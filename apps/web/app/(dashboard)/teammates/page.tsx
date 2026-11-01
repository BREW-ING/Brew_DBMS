import type { Metadata } from "next";
import Link from "next/link";
import { Users } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { TeammateCard } from "@/components/teammate-card";
import { Button } from "@/components/ui/button";
import { getTeammates } from "@/lib/mock-data";

export const metadata: Metadata = { title: "Teammates" };

export default async function TeammatesPage() {
  const teammates = await getTeammates();

  return (
    <>
      <PageHeader
        title="Teammates"
        description="People whose skills complement yours, found through shared interests and past collaborations."
      />

      {teammates.length > 0 ? (
        <ul className="grid gap-4 sm:grid-cols-2">
          {teammates.map((teammate) => (
            <li key={teammate.id}>
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
