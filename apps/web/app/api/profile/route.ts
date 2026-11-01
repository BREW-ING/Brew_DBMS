import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";
import { processGraphSyncQueue } from "@/lib/graph-sync";
import { refreshProfileEmbedding } from "@/lib/ingestion";
import { getProfile, saveProfile } from "@/lib/profile";
import { profileSchema } from "@/lib/profile-schema";

// Neo4j is a mirror: if it's down, the save still stands and the queued
// events are picked up by the next run of /api/internal/graph-sync.
async function syncGraph(userId: string): Promise<boolean> {
  try {
    const result = await processGraphSyncQueue({ userIds: [userId], maxBatches: 1 });
    return result.failedUsers.length === 0;
  } catch (err) {
    console.warn("graph-sync: skipped after profile save", { userId, error: err instanceof Error ? err.message : err });
    return false;
  }
}

export async function GET() {
  const session = await auth();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const profile = await getProfile(session.user.id);
  if (!profile) return NextResponse.json({ error: "User not found" }, { status: 404 });
  return NextResponse.json(profile);
}

export async function PUT(req: Request) {
  const session = await auth();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const userId = session.user.id;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Body must be JSON" }, { status: 400 });
  }
  const parsed = profileSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid profile", issues: parsed.error.issues }, { status: 400 });
  }

  if (!(await saveProfile(userId, parsed.data))) {
    return NextResponse.json({ error: "User not found" }, { status: 404 });
  }

  // Both follow-ups are best-effort and independent, so run them together.
  const [embeddingRefreshed, graphSynced] = await Promise.all([refreshProfileEmbedding(userId), syncGraph(userId)]);

  // Return what was stored (names are normalized), so the form can reset to it.
  const profile = await getProfile(userId);
  return NextResponse.json({ profile, embeddingRefreshed, graphSynced });
}
