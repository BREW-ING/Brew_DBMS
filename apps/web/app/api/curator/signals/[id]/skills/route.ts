import { NextResponse } from "next/server";
import { z } from "zod";

import { requireCurator } from "@/lib/curator";
import { signalSkillsSchema } from "@/lib/curator-schema";
import { setSignalSkills } from "@/lib/review";

// guid, not uuid: seed rows can have hand-written ids that aren't RFC 4122.
const idSchema = z.guid();

/** Replaces the signal's skill tags. Body: { "skills": ["python", ...] }. */
export async function PUT(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const check = await requireCurator();
  if (!check.ok) return check.response;

  const id = idSchema.safeParse((await params).id);
  if (!id.success) return NextResponse.json({ error: "Signal not found" }, { status: 404 });

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Body must be JSON" }, { status: 400 });
  }
  const parsed = signalSkillsSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid skills", issues: parsed.error.issues }, { status: 400 });
  }

  const skills = await setSignalSkills(id.data, parsed.data.skills);
  if (!skills) return NextResponse.json({ error: "Signal not found" }, { status: 404 });
  return NextResponse.json({ skills });
}
