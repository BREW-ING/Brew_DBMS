import { NextResponse } from "next/server";
import { z } from "zod";

import { auth } from "@/lib/auth";
import { DEFAULT_LIMIT, getProfileEmbedding, MAX_LIMIT, rankSuggestions } from "@/lib/suggestions";

const querySchema = z.object({
  limit: z.coerce.number().int().min(1).max(MAX_LIMIT).default(DEFAULT_LIMIT),
});

function ms(start: number): string {
  return (performance.now() - start).toFixed(1);
}

export async function GET(req: Request) {
  const session = await auth();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const userId = session.user.id;

  const parsed = querySchema.safeParse({
    limit: new URL(req.url).searchParams.get("limit") ?? undefined,
  });
  if (!parsed.success) {
    return NextResponse.json(
      { error: `limit must be an integer from 1 to ${MAX_LIMIT}`, issues: parsed.error.issues },
      { status: 400 },
    );
  }
  const { limit } = parsed.data;

  let step = "load profile embedding";
  try {
    const profileStart = performance.now();
    const embedding = await getProfileEmbedding(userId);
    const timings = [`db-profile;dur=${ms(profileStart)}`];

    if (!embedding) {
      return NextResponse.json(
        {
          status: "profile_incomplete",
          message: "Add skills and interests to your profile to get suggestions.",
          suggestions: [],
        },
        { headers: { "Server-Timing": timings.join(", ") } },
      );
    }

    step = "rank suggestions";
    const rankStart = performance.now();
    const suggestions = await rankSuggestions(userId, embedding, limit);
    timings.push(`db-suggestions;dur=${ms(rankStart)};desc="vector search + feasibility + upsert"`);

    return NextResponse.json({ status: "ok", suggestions }, { headers: { "Server-Timing": timings.join(", ") } });
  } catch (err) {
    console.error(`suggestions: ${step} failed`, { userId, error: err instanceof Error ? err.message : err });
    return NextResponse.json({ error: "Couldn't load suggestions" }, { status: 500 });
  }
}
