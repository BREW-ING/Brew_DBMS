import "server-only";

import { createHash, timingSafeEqual } from "node:crypto";

/**
 * Checks X-Service-Key against SERVICE_KEY in constant time, mirroring
 * require_service_key in services/ingestion/main.py.
 */
export function checkServiceKey(req: Request): "ok" | "unconfigured" | "invalid" {
  const expected = process.env.SERVICE_KEY;
  if (!expected) return "unconfigured";
  const given = req.headers.get("x-service-key");
  if (given === null) return "invalid";
  // Hash both sides so timingSafeEqual gets equal lengths and leaks none.
  const digest = (s: string) => createHash("sha256").update(s).digest();
  return timingSafeEqual(digest(given), digest(expected)) ? "ok" : "invalid";
}
