import "server-only";

import { Pool } from "pg";

// Reuse one pool across dev hot reloads instead of leaking a new one per edit.
const globalForPg = globalThis as unknown as { pgPool?: Pool };

/** Shared Postgres pool. Created on first use so builds don't need DATABASE_URL. */
export function getPool(): Pool {
  if (globalForPg.pgPool) return globalForPg.pgPool;

  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) throw new Error("DATABASE_URL is not set");

  const pool = new Pool({ connectionString, max: 5 });
  globalForPg.pgPool = pool;
  return pool;
}
