import { NextResponse } from "next/server";
import { z } from "zod";

import { requireCurator } from "@/lib/curator";
import { sourceUpdateSchema } from "@/lib/curator-schema";
import { updateSource } from "@/lib/sources";

// ingestion_sources.id is SERIAL.
const idSchema = z.coerce.number().int().positive();

export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const check = await requireCurator();
  if (!check.ok) return check.response;

  const id = idSchema.safeParse((await params).id);
  if (!id.success) return NextResponse.json({ error: "Source not found" }, { status: 404 });

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Body must be JSON" }, { status: 400 });
  }
  const parsed = sourceUpdateSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid source update", issues: parsed.error.issues }, { status: 400 });
  }

  const source = await updateSource(id.data, parsed.data);
  if (!source) return NextResponse.json({ error: "Source not found" }, { status: 404 });
  return NextResponse.json(source);
}
