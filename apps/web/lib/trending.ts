import "server-only";

import { getPool } from "@/lib/db";

export interface TrendingTopic {
  category: string;
  signalCount: number;
}

export interface TrendingResult {
  topics: TrendingTopic[];
  /** When trending_problem_areas was last refreshed; null if the view is empty. */
  refreshedAt: Date | null;
}

type TrendingRow = { category: string; signal_count: string; refreshed_at: Date };

/** Top topics from the trending_problem_areas materialized view. */
export async function getTrending(limit: number): Promise<TrendingResult> {
  // refreshed_at is now() captured at refresh time, so it's the same on every row.
  const { rows } = await getPool().query<TrendingRow>(
    `SELECT category, signal_count, refreshed_at
     FROM trending_problem_areas
     ORDER BY signal_count DESC, category
     LIMIT $1`,
    [limit],
  );
  return {
    // COUNT(*) is bigint, which pg returns as a string.
    topics: rows.map((r) => ({ category: r.category, signalCount: Number(r.signal_count) })),
    refreshedAt: rows[0]?.refreshed_at ?? null,
  };
}
