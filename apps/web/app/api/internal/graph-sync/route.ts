import { NextResponse } from "next/server";

import { processGraphSyncQueue } from "@/lib/graph-sync";
import { checkServiceKey } from "@/lib/service-key";

// Called by a cron with X-Service-Key; proxy.ts lets /api/internal through
// without a session so this check is the only gate.
export async function POST(req: Request) {
  const key = checkServiceKey(req);
  if (key === "unconfigured") return NextResponse.json({ error: "SERVICE_KEY is not configured" }, { status: 503 });
  if (key === "invalid") return NextResponse.json({ error: "Invalid or missing X-Service-Key" }, { status: 401 });

  try {
    return NextResponse.json(await processGraphSyncQueue());
  } catch (err) {
    console.warn("graph-sync: run failed", err instanceof Error ? err.message : err);
    return NextResponse.json({ error: "Graph sync failed; pending events were left in the queue" }, { status: 503 });
  }
}
