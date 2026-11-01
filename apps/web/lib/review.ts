import "server-only";

import { LOW_CONFIDENCE } from "@/lib/curator-schema";
import { getPool } from "@/lib/db";
import { toSlug } from "@/lib/profile";
import type { SignalSource } from "@/lib/suggestions";

export const REVIEW_PAGE_SIZE = 20;
// What a tag the curator kept or added is stored with: a reviewed tag isn't a guess.
const CURATOR_CONFIDENCE = 1.0;

export interface ReviewFilters {
  source: SignalSource | null;
  lowConfidenceOnly: boolean;
  seedOnly: boolean;
}

export interface SignalTag {
  name: string;
  confidence: number;
}

export interface ReviewSignal {
  id: string;
  source: SignalSource;
  title: string;
  /** Null for seed data. */
  url: string | null;
  isStale: boolean;
  embedded: boolean;
  /** COALESCE(published_at, fetched_at), ISO 8601. */
  publishedAt: string;
  fetchedAt: string;
  /** signal_skills, highest confidence first. */
  skills: SignalTag[];
  /** Null when the signal has no tags. */
  avgConfidence: number | null;
}

export interface ReviewPage {
  signals: ReviewSignal[];
  total: number;
  page: number;
  pageCount: number;
}

type ReviewRow = {
  id: string;
  source: SignalSource;
  title: string;
  url: string | null;
  is_stale: boolean;
  embedded: boolean;
  published_at: Date;
  fetched_at: Date;
  skills: SignalTag[];
  avg_confidence: number | null;
};

// $1 source (null = any), $2 low-confidence only, $3 seed only. A signal with
// no tags has a NULL average, so the low-confidence filter leaves it out.
const FILTER_SQL = `
  ($1::text IS NULL OR ps.source = $1::text)
  AND (NOT $2::boolean OR (
      SELECT AVG(ss.confidence) FROM signal_skills ss WHERE ss.signal_id = ps.id
  ) < ${LOW_CONFIDENCE})
  AND (NOT $3::boolean OR ps.url IS NULL)`;

// Tags are aggregated only for the page's rows, after LIMIT.
const PAGE_SQL = `
SELECT p.id, p.source, p.title, p.url, p.is_stale, p.embedded,
       COALESCE(p.published_at, p.fetched_at) AS published_at,
       p.fetched_at,
       COALESCE(tags.skills, '[]'::json) AS skills,
       tags.avg_confidence
FROM (
    SELECT ps.*
    FROM problem_signals ps
    WHERE ${FILTER_SQL}
    ORDER BY ps.fetched_at DESC, ps.id
    LIMIT $4::int OFFSET $5::int
) p
LEFT JOIN LATERAL (
    SELECT json_agg(json_build_object('name', sk.name, 'confidence', ss.confidence)
                    ORDER BY ss.confidence DESC, sk.name) AS skills,
           AVG(ss.confidence)::float8 AS avg_confidence
    FROM signal_skills ss
    JOIN skills sk ON sk.id = ss.skill_id
    WHERE ss.signal_id = p.id
) tags ON true
ORDER BY p.fetched_at DESC, p.id`;

const COUNT_SQL = `SELECT COUNT(*) AS total FROM problem_signals ps WHERE ${FILTER_SQL}`;

/** Most recently fetched signals first, stale ones included. `page` is 1-based. */
export async function listSignalsForReview(filters: ReviewFilters, page: number): Promise<ReviewPage> {
  const params = [filters.source, filters.lowConfidenceOnly, filters.seedOnly];
  const pool = getPool();
  const [pageResult, countResult] = await Promise.all([
    pool.query<ReviewRow>(PAGE_SQL, [...params, REVIEW_PAGE_SIZE, (page - 1) * REVIEW_PAGE_SIZE]),
    // COUNT(*) is bigint, which pg returns as a string.
    pool.query<{ total: string }>(COUNT_SQL, params),
  ]);
  const total = Number(countResult.rows[0]?.total ?? 0);
  return {
    signals: pageResult.rows.map((r) => ({
      id: r.id,
      source: r.source,
      title: r.title,
      url: r.url,
      isStale: r.is_stale,
      embedded: r.embedded,
      publishedAt: r.published_at.toISOString(),
      fetchedAt: r.fetched_at.toISOString(),
      skills: r.skills,
      avgConfidence: r.avg_confidence,
    })),
    total,
    page,
    pageCount: Math.max(1, Math.ceil(total / REVIEW_PAGE_SIZE)),
  };
}

/** The skill vocabulary, for the tag editor's suggestions. */
export async function listSkillNames(): Promise<string[]> {
  const { rows } = await getPool().query<{ name: string }>("SELECT name FROM skills ORDER BY name");
  return rows.map((r) => r.name);
}

/** False if the signal doesn't exist. Staleness is one-way, so there's no undo. */
export async function markSignalStale(signalId: string): Promise<boolean> {
  const { rowCount } = await getPool().query("UPDATE problem_signals SET is_stale = true WHERE id = $1", [signalId]);
  return rowCount === 1;
}

/**
 * Cascades to signal_skills, suggestions and their feedback. A real signal
 * comes back on the next fetch if the source still returns it; marking it
 * stale is what retires it for good. False if the signal doesn't exist.
 */
export async function deleteSignal(signalId: string): Promise<boolean> {
  const { rowCount } = await getPool().query("DELETE FROM problem_signals WHERE id = $1", [signalId]);
  return rowCount === 1;
}

/**
 * Replaces the signal's tags with `names` in one transaction. Every kept or
 * added tag is stored at full confidence, since a curator has now reviewed it.
 * Returns the stored tags, or null if the signal doesn't exist.
 */
export async function setSignalSkills(signalId: string, names: string[]): Promise<SignalTag[] | null> {
  const skillNames = [...new Set(names.map(toSlug))];

  const client = await getPool().connect();
  try {
    await client.query("BEGIN");

    // Row lock serializes concurrent edits of the same signal.
    const signal = await client.query("SELECT 1 FROM problem_signals WHERE id = $1 FOR UPDATE", [signalId]);
    if (signal.rowCount === 0) {
      await client.query("ROLLBACK");
      return null;
    }

    // Names the vocabulary doesn't have yet become new rows.
    await client.query(
      "INSERT INTO skills (name) SELECT unnest($1::text[]) ON CONFLICT (name) DO NOTHING",
      [skillNames],
    );
    await client.query(
      `DELETE FROM signal_skills ss
       USING skills s
       WHERE ss.signal_id = $1 AND s.id = ss.skill_id AND NOT (s.name = ANY($2::text[]))`,
      [signalId, skillNames],
    );
    await client.query(
      `INSERT INTO signal_skills (signal_id, skill_id, confidence)
       SELECT $1, s.id, $3::real FROM skills s WHERE s.name = ANY($2::text[])
       ON CONFLICT (signal_id, skill_id) DO UPDATE SET confidence = EXCLUDED.confidence`,
      [signalId, skillNames, CURATOR_CONFIDENCE],
    );

    await client.query("COMMIT");
    return skillNames.sort().map((name) => ({ name, confidence: CURATOR_CONFIDENCE }));
  } catch (err) {
    await client.query("ROLLBACK").catch(() => {});
    throw err;
  } finally {
    client.release();
  }
}
