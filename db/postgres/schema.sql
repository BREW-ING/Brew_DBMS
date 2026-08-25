-- =========================================================
-- Brew — PostgreSQL Schema (includes pgvector extension)
-- =========================================================
-- Run this against a fresh database. Order matters: extension
-- first, then tables, then indexes/triggers/procedures/views.

-- ---------------------------------------------------------
-- 0. Extensions
-- ---------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector — this is what makes Postgres double as the vector DB

-- ---------------------------------------------------------
-- 1. Core identity & role tables
-- ---------------------------------------------------------
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'curator')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE skills (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE
);

CREATE TABLE user_skills (
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill_id        INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    proficiency     SMALLINT NOT NULL DEFAULT 3 CHECK (proficiency BETWEEN 1 AND 5),
    PRIMARY KEY (user_id, skill_id)
);

CREATE TABLE constraints (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_size       SMALLINT NOT NULL DEFAULT 1,
    timeframe_hours INTEGER NOT NULL DEFAULT 48,
    preferred_stack TEXT[],
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------
-- 2. Ingestion source management (curator-facing)
-- ---------------------------------------------------------
CREATE TABLE ingestion_sources (
    id              SERIAL PRIMARY KEY,
    source_type     TEXT NOT NULL CHECK (source_type IN ('github', 'arxiv', 'news', 'reddit')),
    config          JSONB NOT NULL DEFAULT '{}',   -- e.g. subreddit list, repo filters
    is_active       BOOLEAN NOT NULL DEFAULT true,
    last_fetched_at TIMESTAMPTZ,
    created_by      UUID REFERENCES users(id)
);

-- ---------------------------------------------------------
-- 3. Problem signals (raw ingested data + embedding pointer)
-- ---------------------------------------------------------
CREATE TABLE problem_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          TEXT NOT NULL CHECK (source IN ('github', 'arxiv', 'news', 'reddit')),
    external_id     TEXT NOT NULL,             -- dedupe key from the source system
    title           TEXT NOT NULL,
    raw_text        TEXT NOT NULL,
    url             TEXT,
    category_tags   TEXT[] NOT NULL DEFAULT '{}',
    published_at    TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    embedded        BOOLEAN NOT NULL DEFAULT false,
    is_stale        BOOLEAN NOT NULL DEFAULT false,
    embedding       vector(384),               -- 384 dims = all-MiniLM-L6-v2; change if using a different model
    UNIQUE (source, external_id)
);

-- Vector similarity index (IVFFlat — good default for a student-scale dataset)
CREATE INDEX idx_problem_signals_embedding
    ON problem_signals USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Standard indexes for the ingestion/query workload
CREATE INDEX idx_problem_signals_freshness ON problem_signals (fetched_at DESC);
CREATE INDEX idx_problem_signals_category ON problem_signals USING GIN (category_tags);
CREATE INDEX idx_problem_signals_embedded ON problem_signals (embedded) WHERE embedded = false;

-- ---------------------------------------------------------
-- 4. Suggestions & feedback
-- ---------------------------------------------------------
CREATE TABLE suggestions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    signal_id       UUID NOT NULL REFERENCES problem_signals(id) ON DELETE CASCADE,
    similarity_score    REAL NOT NULL,
    feasibility_score   REAL NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    suggestion_id   UUID NOT NULL REFERENCES suggestions(id) ON DELETE CASCADE,
    rating          SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------
-- 5. Trigger — auto-flag stale signals (advanced feature #1)
-- ---------------------------------------------------------
CREATE OR REPLACE FUNCTION mark_stale_signals() RETURNS trigger AS $$
BEGIN
    UPDATE problem_signals
    SET is_stale = true
    WHERE fetched_at < now() - INTERVAL '30 days'
      AND is_stale = false;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Runs opportunistically whenever a new signal is inserted, so staleness
-- stays current without needing a separate scheduled job.
CREATE TRIGGER trg_mark_stale_signals
    AFTER INSERT ON problem_signals
    FOR EACH STATEMENT
    EXECUTE FUNCTION mark_stale_signals();

-- ---------------------------------------------------------
-- 6. Stored procedure — feasibility scoring (advanced feature #2)
-- ---------------------------------------------------------
-- Combines the user's skill-coverage ratio against a signal's category tags
-- with a time-budget penalty. Called from the matching engine after vector
-- similarity has already produced a shortlist of candidate signal IDs.
CREATE OR REPLACE FUNCTION compute_feasibility_score(
    p_user_id UUID,
    p_signal_id UUID
) RETURNS REAL AS $$
DECLARE
    v_user_skill_count INTEGER;
    v_matched_skill_count INTEGER;
    v_timeframe_hours INTEGER;
    v_score REAL;
BEGIN
    SELECT COUNT(*) INTO v_user_skill_count
    FROM user_skills WHERE user_id = p_user_id;

    SELECT COUNT(*) INTO v_matched_skill_count
    FROM user_skills us
    JOIN skills s ON s.id = us.skill_id
    JOIN problem_signals ps ON ps.id = p_signal_id
    WHERE us.user_id = p_user_id
      AND s.name = ANY(ps.category_tags);

    SELECT COALESCE(MIN(timeframe_hours), 48) INTO v_timeframe_hours
    FROM constraints WHERE user_id = p_user_id;

    IF v_user_skill_count = 0 THEN
        v_score := 0.3;  -- neutral-low default if no skills recorded yet
    ELSE
        v_score := LEAST(1.0, v_matched_skill_count::REAL / v_user_skill_count);
    END IF;

    -- Penalize short timeframes slightly, since ambitious ideas need more runway
    IF v_timeframe_hours < 24 THEN
        v_score := v_score * 0.85;
    END IF;

    RETURN v_score;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------
-- 7. Materialized view — trending problem areas (advanced feature #3)
-- ---------------------------------------------------------
CREATE MATERIALIZED VIEW trending_problem_areas AS
SELECT
    unnest(category_tags) AS category,
    COUNT(*) AS signal_count,
    MAX(fetched_at) AS most_recent
FROM problem_signals
WHERE fetched_at > now() - INTERVAL '14 days'
  AND is_stale = false
GROUP BY category
ORDER BY signal_count DESC;

-- Refresh on a schedule (e.g. after each ingestion job run):
-- REFRESH MATERIALIZED VIEW trending_problem_areas;

-- ---------------------------------------------------------
-- 8. Seed reference data
-- ---------------------------------------------------------
INSERT INTO skills (name) VALUES
    ('javascript'), ('typescript'), ('python'), ('react'), ('nextjs'),
    ('machine-learning'), ('computer-vision'), ('nlp'), ('postgresql'),
    ('neo4j'), ('vector-search'), ('ui-design'), ('mobile'), ('devops')
ON CONFLICT (name) DO NOTHING;
