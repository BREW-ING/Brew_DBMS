import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PageHeader } from "@/components/page-header";
import { SkillForm } from "@/components/skill-form";
import { Card, CardContent } from "@/components/ui/card";
import { auth } from "@/lib/auth";
import { getProfile } from "@/lib/profile";

export const metadata: Metadata = { title: "Profile" };

export default async function ProfilePage() {
  const session = await auth();
  if (!session) redirect("/login");
  const profile = await getProfile(session.user.id);
  if (!profile) redirect("/login");

  return (
    <div className="max-w-2xl">
      <PageHeader
        title="Profile"
        description="Your skills, interests and constraints drive the suggestions and teammate matches you see."
      />
      <Card>
        <CardContent>
          <SkillForm defaultValues={profile} />
        </CardContent>
      </Card>
    </div>
  );
}
