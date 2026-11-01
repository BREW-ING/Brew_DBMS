import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";
import { getTeammatesForUser } from "@/lib/teammates";

// Neo4j being down is a 200 with status "graph_unavailable", not a 500, so
// the rest of the dashboard keeps working (docs/ARCHITECTURE.md section 5).
export async function GET() {
  const session = await auth();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const result = await getTeammatesForUser(session.user.id);
  return NextResponse.json({ status: result.status, teammates: result.teammates });
}
