-- =========================================================
-- Brew — benchmark schema
-- =========================================================
-- Everything the benchmarks create lives in the `bench` schema. Nothing here
-- reads or writes the application's tables in `public`, and every statement
-- in benchmarks/ names its tables as bench.<table>. Idempotent: the harness
-- runs it before every benchmark. Remove it all with
--   python -m benchmarks.cleanup        (or: DROP SCHEMA bench CASCADE;)
--
-- The tables keep only the columns the benchmarked queries touch, with the
-- same types, keys and indexes as db/postgres/schema.sql.

CREATE SCHEMA IF NOT EXISTS bench;

CREATE TABLE IF NOT EXISTS bench.users (
    id      UUID PRIMARY KEY,
    name    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bench.skills (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS bench.interests (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS bench.user_skills (
    user_id     UUID NOT NULL REFERENCES bench.users(id) ON DELETE CASCADE,
    skill_id    INTEGER NOT NULL REFERENCES bench.skills(id) ON DELETE CASCADE,
    proficiency SMALLINT NOT NULL CHECK (proficiency BETWEEN 1 AND 5),
    PRIMARY KEY (user_id, skill_id)
);
CREATE INDEX IF NOT EXISTS idx_bench_user_skills_skill ON bench.user_skills (skill_id);

CREATE TABLE IF NOT EXISTS bench.user_interests (
    user_id     UUID NOT NULL REFERENCES bench.users(id) ON DELETE CASCADE,
    interest_id INTEGER NOT NULL REFERENCES bench.interests(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, interest_id)
);
CREATE INDEX IF NOT EXISTS idx_bench_user_interests_interest ON bench.user_interests (interest_id);

-- One row per pair in canonical order, as in public.collaborations.
CREATE TABLE IF NOT EXISTS bench.collaborations (
    user_a       UUID NOT NULL REFERENCES bench.users(id) ON DELETE CASCADE,
    user_b       UUID NOT NULL REFERENCES bench.users(id) ON DELETE CASCADE,
    project_name TEXT NOT NULL,
    PRIMARY KEY (user_a, user_b),
    CHECK (user_a < user_b)
);
CREATE INDEX IF NOT EXISTS idx_bench_collaborations_user_b ON bench.collaborations (user_b);

-- public.constraints has a surrogate id plus UNIQUE (user_id); score_candidates
-- only ever looks rows up by user_id, which a primary key serves the same way.
CREATE TABLE IF NOT EXISTS bench.constraints (
    user_id         UUID PRIMARY KEY REFERENCES bench.users(id) ON DELETE CASCADE,
    team_size       SMALLINT NOT NULL CHECK (team_size >= 1),
    timeframe_hours INTEGER NOT NULL CHECK (timeframe_hours > 0)
);

-- The HNSW index is created (and timed) by benchmarks/bench_vector.py after
-- the rows are loaded, so it is not declared here.
CREATE TABLE IF NOT EXISTS bench.problem_signals (
    id          UUID PRIMARY KEY,
    title       TEXT NOT NULL,
    embedding   vector(384) NOT NULL
);

CREATE TABLE IF NOT EXISTS bench.signal_skills (
    signal_id   UUID NOT NULL REFERENCES bench.problem_signals(id) ON DELETE CASCADE,
    skill_id    INTEGER NOT NULL REFERENCES bench.skills(id) ON DELETE CASCADE,
    confidence  REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    PRIMARY KEY (signal_id, skill_id)
);
CREATE INDEX IF NOT EXISTS idx_bench_signal_skills_skill ON bench.signal_skills (skill_id);

-- ---------------------------------------------------------
-- Feasibility scoring: copies of public.score_candidates and
-- public.compute_feasibility_score (db/postgres/schema.sql section 5) with
-- the tables pointed at bench. Keep the bodies in sync with that file.
-- ---------------------------------------------------------
CREATE OR REPLACE FUNCTION bench.score_candidates(
    p_user_id    UUID,
    p_signal_ids UUID[]
) RETURNS TABLE (signal_id UUID, score REAL)
LANGUAGE sql
STABLE
AS $$
    WITH user_constraints AS (
        SELECT COALESCE(MAX(c.team_size), 1)        AS team_size,
               COALESCE(MAX(c.timeframe_hours), 48) AS timeframe_hours
        FROM bench.constraints c
        WHERE c.user_id = p_user_id
    ),
    coverage AS (
        SELECT ps.id                                   AS signal_id,
               COUNT(ss.skill_id)                      AS required_skills,
               COALESCE(SUM(us.proficiency / 5.0), 0)  AS weighted_matches
        FROM bench.problem_signals ps
        LEFT JOIN bench.signal_skills ss ON ss.signal_id = ps.id
        LEFT JOIN bench.user_skills   us ON us.skill_id = ss.skill_id
                                        AND us.user_id  = p_user_id
        WHERE ps.id = ANY (p_signal_ids)
        GROUP BY ps.id
    )
    SELECT cov.signal_id,
           (
               CASE WHEN cov.required_skills = 0 THEN 0.5
                    ELSE cov.weighted_matches / cov.required_skills
               END
               * LEAST(1.0, 0.6 + 0.1 * uc.team_size)
               * CASE WHEN uc.timeframe_hours < 24 THEN 0.85 ELSE 1.0 END
           )::REAL
    FROM coverage cov
    CROSS JOIN user_constraints uc;
$$;

CREATE OR REPLACE FUNCTION bench.compute_feasibility_score(
    p_user_id   UUID,
    p_signal_id UUID
) RETURNS REAL
LANGUAGE sql
STABLE
AS $$
    SELECT sc.score FROM bench.score_candidates(p_user_id, ARRAY[p_signal_id]) sc;
$$;
