import { NextResponse } from "next/server";
import { z } from "zod";

import { requireCurator } from "@/lib/curator";
import { signalStaleSchema } from "@/lib/curator-schema";
import { deleteSignal, markSignalStale } from "@/lib/review";

// guid, not uuid: seed rows can have hand-written ids that aren't RFC 4122.
const idSchema = z.guid();

/** Marks the signal stale. Body: { "isStale": true }. */
export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
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
  const parsed = signalStaleSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid signal update", issues: parsed.error.issues }, { status: 400 });
  }

  if (!(await markSignalStale(id.data))) return NextResponse.json({ error: "Signal not found" }, { status: 404 });
  return NextResponse.json({ id: id.data, isStale: true });
}

export async function DELETE(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const check = await requireCurator();
  if (!check.ok) return check.response;

  const id = idSchema.safeParse((await params).id);
  if (!id.success) return NextResponse.json({ error: "Signal not found" }, { status: 404 });

  if (!(await deleteSignal(id.data))) return NextResponse.json({ error: "Signal not found" }, { status: 404 });
  return new NextResponse(null, { status: 204 });
}
