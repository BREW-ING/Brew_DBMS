import "server-only";

/**
 * Asks the ingestion service to recompute users.profile_embedding. Never
 * throws: a stale embedding only makes suggestions slightly less fresh, so
 * failures are logged and reported as false.
 */
export async function refreshProfileEmbedding(userId: string): Promise<boolean> {
  const baseUrl = process.env.INGESTION_URL;
  const serviceKey = process.env.SERVICE_KEY;
  if (!baseUrl || !serviceKey) {
    console.warn("ingestion: INGESTION_URL or SERVICE_KEY is not set; skipping embedding refresh");
    return false;
  }

  try {
    const res = await fetch(
      `${baseUrl.replace(/\/+$/, "")}/users/${encodeURIComponent(userId)}/refresh-embedding`,
      {
        method: "POST",
        headers: { "X-Service-Key": serviceKey },
        cache: "no-store",
        // Generous: the first call after a cold start loads the embedding model.
        signal: AbortSignal.timeout(20_000),
      },
    );
    if (!res.ok) {
      console.warn("ingestion: embedding refresh failed", { userId, status: res.status });
      return false;
    }
    return true;
  } catch (err) {
    console.warn("ingestion: embedding refresh failed", { userId, error: err instanceof Error ? err.message : err });
    return false;
  }
}
