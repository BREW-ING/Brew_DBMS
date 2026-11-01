import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";
import { SkillForm } from "@/components/skill-form";
import { Card, CardContent } from "@/components/ui/card";
import { getProfile } from "@/lib/mock-data";

export const metadata: Metadata = { title: "Profile" };

export default async function ProfilePage() {
  const profile = await getProfile();

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
