import "server-only";

import { getPool } from "@/lib/db";

// Mirrors CHECK (source IN ('github', 'arxiv', 'hn')) on problem_signals.source.
export type SignalSource = "github" | "arxiv" | "hn";

export interface RequiredSkill {
  name: string;
  /** True if the skill is in the user's user_skills. */
  userHas: boolean;
}

export interface Suggestion {
  /** suggestions.id — what feedback references. */
  id: string;
  signalId: string;
  title: string;
  source: SignalSource;
  url: string | null;
  /** COALESCE(published_at, fetched_at), ISO 8601. */
  publishedAt: string;
  ageDays: number;
  /** problem_signals.category_tags */
  topicTags: string[];
  /** signal_skills, skills the user has first, then by tagger confidence. */
  requiredSkills: RequiredSkill[];
  /** Cosine similarity between the profile and signal embeddings. */
  similarity: number;
  /** score_candidates() output, 0-1. */
  feasibility: number;
  /** 0.6 * similarity + 0.4 * feasibility */
  score: number;
}

export interface SuggestionDetail extends Suggestion {
  rawText: string;
  /** The user's feedback.rating, if they've rated it. */
  rating: number | null;
}

export const DEFAULT_LIMIT = 10;
export const MAX_LIMIT = 50;

// Shortlist size for vector search, before feasibility re-ranks it.
const CANDIDATES = 50;
// pgvector's HNSW scan returns at most ef_search rows (default 40), and the
// staleness / dislike filters run after the scan, so it must sit well above
// CANDIDATES for the shortlist to fill up.
const EF_SEARCH = 100;

type SuggestionRow = {
  id: string;
  signal_id: string;
  title: string;
  source: SignalSource;
  url: string | null;
  published_at: Date;
  age_days: number;
  category_tags: string[];
  required_skills: { name: string; user_has: boolean }[];
  similarity: number;
  feasibility: number;
  score: number;
};

// Correlated on signal_id; $1 is the user. An aggregate with no GROUP BY
// always yields one row, so LEFT JOIN LATERAL ... ON true never drops a signal.
const REQUIRED_SKILLS_LATERAL = `
  LEFT JOIN LATERAL (
    SELECT json_agg(
             json_build_object('name', sk.name, 'user_has', us.user_id IS NOT NULL)
             ORDER BY (us.user_id IS NOT NULL) DESC, ss.confidence DESC, sk.name
           ) AS skills
    FROM signal_skills ss
    JOIN skills sk ON sk.id = ss.skill_id
    LEFT JOIN user_skills us ON us.skill_id = ss.skill_id AND us.user_id = $1::uuid
    WHERE ss.signal_id = ps.id
  ) req ON true`;

// One statement: shortlist by vector distance, score feasibility for the whole
// shortlist in one score_candidates() call, keep the top $3, upsert them into
// suggestions, and return them with their suggestion ids.
//
// The nearest CTE keeps the exact `ORDER BY embedding <=> $2 LIMIT n` shape so
// the planner uses idx_problem_signals_embedding (HNSW); its other conditions
// filter that scan's output.
const RANK_SQL = `
WITH nearest AS (
    SELECT ps.id, (1 - (ps.embedding <=> $2::vector))::float8 AS similarity
    FROM problem_signals ps
    WHERE NOT ps.is_stale
      -- url IS NULL rows are seed data, not real signals.
      AND ps.url IS NOT NULL
      -- Signals this user rated 1-2 before are never suggested again.
      AND NOT EXISTS (
          SELECT 1
          FROM feedback f
          JOIN suggestions s ON s.id = f.suggestion_id
          WHERE f.user_id = $1::uuid
            AND f.rating <= 2
            AND s.signal_id = ps.id
      )
    ORDER BY ps.embedding <=> $2::vector
    LIMIT ${CANDIDATES}
),
scored AS (
    SELECT n.id AS signal_id,
           n.similarity,
           sc.score::float8 AS feasibility,
           0.6 * n.similarity + 0.4 * sc.score AS score
    FROM nearest n
    JOIN score_candidates($1::uuid, ARRAY(SELECT id FROM nearest)) sc ON sc.signal_id = n.id
    ORDER BY score DESC
    LIMIT $3::int
),
upserted AS (
    INSERT INTO suggestions (user_id, signal_id, similarity_score, feasibility_score)
    SELECT $1::uuid, signal_id, similarity, feasibility FROM scored
    ON CONFLICT (user_id, signal_id) DO UPDATE
       SET similarity_score  = EXCLUDED.similarity_score,
           feasibility_score = EXCLUDED.feasibility_score
    RETURNING id, signal_id
)
SELECT u.id,
       ps.id AS signal_id,
       ps.title,
       ps.source,
       ps.url,
       COALESCE(ps.published_at, ps.fetched_at) AS published_at,
       floor(extract(epoch FROM now() - COALESCE(ps.published_at, ps.fetched_at)) / 86400)::int AS age_days,
       ps.category_tags,
       COALESCE(req.skills, '[]'::json) AS required_skills,
       sc.similarity,
       sc.feasibility,
       sc.score::float8 AS score
FROM scored sc
JOIN upserted u ON u.signal_id = sc.signal_id
JOIN problem_signals ps ON ps.id = sc.signal_id
${REQUIRED_SKILLS_LATERAL}
ORDER BY sc.score DESC`;

const DETAIL_SQL = `
SELECT s.id,
       ps.id AS signal_id,
       ps.title,
       ps.raw_text,
       ps.source,
       ps.url,
       COALESCE(ps.published_at, ps.fetched_at) AS published_at,
       floor(extract(epoch FROM now() - COALESCE(ps.published_at, ps.fetched_at)) / 86400)::int AS age_days,
       ps.category_tags,
       COALESCE(req.skills, '[]'::json) AS required_skills,
       s.similarity_score::float8 AS similarity,
       s.feasibility_score::float8 AS feasibility,
       (0.6 * s.similarity_score + 0.4 * s.feasibility_score)::float8 AS score,
       f.rating
FROM suggestions s
JOIN problem_signals ps ON ps.id = s.signal_id
LEFT JOIN feedback f ON f.suggestion_id = s.id AND f.user_id = s.user_id
${REQUIRED_SKILLS_LATERAL}
WHERE s.user_id = $1::uuid AND s.id = $2::uuid`;

function toSuggestion(row: SuggestionRow): Suggestion {
  return {
    id: row.id,
    signalId: row.signal_id,
    title: row.title,
    source: row.source,
    url: row.url,
    publishedAt: row.published_at.toISOString(),
    ageDays: row.age_days,
    topicTags: row.category_tags,
    requiredSkills: row.required_skills.map((s) => ({ name: s.name, userHas: s.user_has })),
    similarity: row.similarity,
    feasibility: row.feasibility,
    score: row.score,
  };
}

/**
 * The user's profile_embedding in pgvector's text form ("[0.1,0.2,...]"), so it
 * can be passed straight back as a $n::vector parameter. Null if it hasn't been
 * computed yet (or the user doesn't exist).
 */
export async function getProfileEmbedding(userId: string): Promise<string | null> {
  const { rows } = await getPool().query<{ embedding: string | null }>(
    "SELECT profile_embedding::text AS embedding FROM users WHERE id = $1",
    [userId],
  );
  return rows[0]?.embedding ?? null;
}

/** Ranks, upserts into suggestions, and returns the top `limit` for the user. */
export async function rankSuggestions(userId: string, embedding: string, limit: number): Promise<Suggestion[]> {
  const client = await getPool().connect();
  try {
    // SET LOCAL needs a transaction, and keeps the setting off pooled connections.
    await client.query("BEGIN");
    await client.query(`SET LOCAL hnsw.ef_search = ${EF_SEARCH}`);
    const { rows } = await client.query<SuggestionRow>(RANK_SQL, [userId, embedding, limit]);
    await client.query("COMMIT");
    return rows.map(toSuggestion);
  } catch (err) {
    await client.query("ROLLBACK").catch(() => {});
    throw err;
  } finally {
    client.release();
  }
}

export type SuggestionsResult = { status: "ok"; suggestions: Suggestion[] } | { status: "profile_incomplete" };

/** Both steps together, for server components. */
export async function getSuggestionsForUser(userId: string, limit = DEFAULT_LIMIT): Promise<SuggestionsResult> {
  const embedding = await getProfileEmbedding(userId);
  if (!embedding) return { status: "profile_incomplete" };
  return { status: "ok", suggestions: await rankSuggestions(userId, embedding, limit) };
}

/** One of the user's own suggestions, or null if it doesn't exist or isn't theirs. */
export async function getSuggestion(userId: string, suggestionId: string): Promise<SuggestionDetail | null> {
  const { rows } = await getPool().query<SuggestionRow & { raw_text: string; rating: number | null }>(DETAIL_SQL, [
    userId,
    suggestionId,
  ]);
  const row = rows[0];
  if (!row) return null;
  return { ...toSuggestion(row), rawText: row.raw_text, rating: row.rating };
}
