import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";
import { feedbackSchema, saveFeedback } from "@/lib/feedback";

export async function POST(req: Request) {
  const session = await auth();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Body must be JSON" }, { status: 400 });
  }
  const parsed = feedbackSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid feedback", issues: parsed.error.issues }, { status: 400 });
  }

  const result = await saveFeedback(session.user.id, parsed.data);
  if (!result) return NextResponse.json({ error: "Suggestion not found" }, { status: 404 });
  return NextResponse.json(result.feedback, { status: result.created ? 201 : 200 });
}
