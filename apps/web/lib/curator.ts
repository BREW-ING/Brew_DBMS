import "server-only";

import { NextResponse } from "next/server";

import { auth, type Role } from "@/lib/auth";
import { getPool } from "@/lib/db";

export type CuratorCheck = { ok: true; userId: string } | { ok: false; response: NextResponse };

/**
 * Gate for every /api/curator mutation. proxy.ts already checks the role in
 * the JWT, but that copy lives until the token expires, so a curator who was
 * demoted would keep access. This re-reads users.role on each call.
 */
export async function requireCurator(): Promise<CuratorCheck> {
  const session = await auth();
  if (!session) return { ok: false, response: NextResponse.json({ error: "Unauthorized" }, { status: 401 }) };

  const { rows } = await getPool().query<{ role: Role }>("SELECT role FROM users WHERE id = $1", [session.user.id]);
  if (rows[0]?.role !== "curator") {
    return { ok: false, response: NextResponse.json({ error: "Forbidden" }, { status: 403 }) };
  }
  return { ok: true, userId: session.user.id };
}
