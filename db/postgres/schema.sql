-- =========================================================
-- Brew — PostgreSQL Schema (includes pgvector extension)
-- =========================================================
-- Run this against a fresh database. Order matters: extensions
-- first, then tables, then indexes/functions/triggers/views.
-- Design rationale, ER diagram, and index inventory: docs/DATABASE.md

-- ---------------------------------------------------------
-- 0. Extensions
-- ---------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector >= 0.5.0 (HNSW support); makes Postgres double as the vector DB

-- ---------------------------------------------------------
-- 1. Core identity, skills, and interests
-- ---------------------------------------------------------
CREATE TABLE users (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email             TEXT NOT NULL UNIQUE,
    name              TEXT NOT NULL,
    -- Credentials for the NextAuth credentials provider. Store only a slow,
    -- salted hash (bcrypt/argon2) — never the password itself.
    password_hash     TEXT NOT NULL,
    role              TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'curator')),
    -- Cached embedding of the user's skills + interests. Same model and
    -- dimensionality as problem_signals.embedding so the two are directly
    -- comparable. NULL until first computed. Not indexed: we search signals
    -- *by* this vector, we never search users by it.
    profile_embedding vector(384),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
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
-- The PK covers "skills of user X". This covers the reverse ("users with
-- skill X") and keeps ON DELETE CASCADE from skills from scanning the table.
CREATE INDEX idx_user_skills_skill ON user_skills (skill_id);

-- Interests are normalized the same way as skills so Postgres is the single
-- source of truth; Neo4j's (:Interest) nodes and INTERESTED_IN edges are a
-- mirror kept up to date through graph_sync_queue (section 6).
CREATE TABLE interests (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE
);

CREATE TABLE user_interests (
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    interest_id     INTEGER NOT NULL REFERENCES interests(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, interest_id)
);
CREATE INDEX idx_user_interests_interest ON user_interests (interest_id);

-- Past collaborations — the source of truth for Neo4j's COLLABORATED_WITH
-- edges. Collaboration is symmetric, so each pair is stored exactly once in
-- canonical order (user_a < user_b): storing both directions would let the
-- two copies disagree. Insert with LEAST()/GREATEST() to normalize:
--   INSERT INTO collaborations (user_a, user_b, project_name)
--   VALUES (LEAST($1, $2)::uuid, GREATEST($1, $2)::uuid, $3);
-- The strict < also rules out self-collaboration (user_a = user_b).
CREATE TABLE collaborations (
    user_a          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_b          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_name    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_a, user_b),
    CONSTRAINT collaborations_canonical_pair CHECK (user_a < user_b)
);
-- The PK serves lookups by user_a; this serves lookups by user_b. "All
-- collaborators of X" is (user_a = X OR user_b = X), answered by combining
-- both indexes. Also keeps the ON DELETE CASCADE on user_b from scanning.
CREATE INDEX idx_collaborations_user_b ON collaborations (user_b);

-- UNIQUE (user_id): exactly one constraints row per user. The feasibility
-- scorer reads "the" user's team size and time budget; several rows per user
-- would make that ambiguous.
CREATE TABLE constraints (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_size       SMALLINT NOT NULL DEFAULT 1 CHECK (team_size >= 1),
    timeframe_hours INTEGER NOT NULL DEFAULT 48 CHECK (timeframe_hours > 0),
    preferred_stack TEXT[],
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id)
);

-- ---------------------------------------------------------
-- 2. Ingestion source management (curator-facing)
-- ---------------------------------------------------------
CREATE TABLE ingestion_sources (
    id              SERIAL PRIMARY KEY,
    source_type     TEXT NOT NULL CHECK (source_type IN ('github', 'arxiv', 'hn')),
    config          JSONB NOT NULL DEFAULT '{}',   -- e.g. repo filters, arXiv categories
    is_active       BOOLEAN NOT NULL DEFAULT true,
    last_fetched_at TIMESTAMPTZ,
    created_by      UUID REFERENCES users(id)
);

-- ---------------------------------------------------------
-- 3. Problem signals and their required skills
-- ---------------------------------------------------------
CREATE TABLE problem_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          TEXT NOT NULL CHECK (source IN ('github', 'arxiv', 'hn')),
    external_id     TEXT NOT NULL,             -- dedupe key from the source system
    title           TEXT NOT NULL,
    raw_text        TEXT NOT NULL,
    url             TEXT,
    -- Broad topic areas only (e.g. 'climate', 'healthtech') — these feed the
    -- trending view. Skills a signal requires live in signal_skills, where
    -- they are foreign-keyed to skills and carry a confidence.
    category_tags   TEXT[] NOT NULL DEFAULT '{}'
                    CHECK (array_position(category_tags, NULL) IS NULL),
    published_at    TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    embedding       vector(384),               -- 384 dims = all-MiniLM-L6-v2
    -- Derived from `embedding` instead of maintained by hand, so it can never
    -- disagree with it (no "embedded = true but embedding IS NULL" rows).
    -- The embedding job only writes `embedding`.
    embedded        BOOLEAN GENERATED ALWAYS AS (embedding IS NOT NULL) STORED,
    is_stale        BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (source, external_id)
);

-- HNSW instead of IVFFlat. IVFFlat picks its list centroids from the rows
-- present when the index is built; built on an empty table (as it is here,
-- at schema-creation time) the centroids are meaningless and recall stays
-- poor until a manual REINDEX. HNSW has no training step, so it stays
-- accurate as rows arrive. m / ef_construction are pgvector's defaults,
-- stated explicitly; tune ef_search per session for recall vs. speed.
CREATE INDEX idx_problem_signals_embedding
    ON problem_signals USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Recent-signal scans (trending view's 14-day window, "latest signals" lists).
CREATE INDEX idx_problem_signals_freshness ON problem_signals (fetched_at DESC);
-- Containment queries on topics: category_tags @> ARRAY['climate'].
CREATE INDEX idx_problem_signals_category ON problem_signals USING GIN (category_tags);
-- Embedding job backlog: oldest-first batches of rows with no embedding yet.
-- Partial, so it only ever holds the (small) backlog.
CREATE INDEX idx_problem_signals_unembedded ON problem_signals (fetched_at) WHERE NOT embedded;
-- Staleness sweep: holds only rows that are not yet stale, keyed on the
-- exact expression expire_stale_signals() filters on. Rows already marked
-- stale drop out of the index, so each sweep touches only rows that could
-- actually change.
CREATE INDEX idx_problem_signals_stale_candidates
    ON problem_signals ((COALESCE(published_at, fetched_at)))
    WHERE is_stale = false;

-- Junction table replacing "skills hidden in category_tags": each row says a
-- signal needs a skill, with the tagger's confidence (0..1) in that claim.
CREATE TABLE signal_skills (
    signal_id       UUID NOT NULL REFERENCES problem_signals(id) ON DELETE CASCADE,
    skill_id        INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    confidence      REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    PRIMARY KEY (signal_id, skill_id)
);
-- PK serves the scorer ("skills of signal X"); this serves "signals needing
-- skill X" and cascades from skills.
CREATE INDEX idx_signal_skills_skill ON signal_skills (skill_id);

-- ---------------------------------------------------------
-- 4. Suggestions & feedback
-- ---------------------------------------------------------
CREATE TABLE suggestions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    signal_id       UUID NOT NULL REFERENCES problem_signals(id) ON DELETE CASCADE,
    similarity_score    REAL NOT NULL,
    feasibility_score   REAL NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- A signal is suggested to a given user at most once; re-scoring updates
    -- the existing row (INSERT ... ON CONFLICT DO UPDATE) instead of piling
    -- up duplicates. Also serves "suggestions for user X".
    UNIQUE (user_id, signal_id),
    -- Target for feedback's composite foreign key (see below). id alone is
    -- already unique; this just lets (id, user_id) be referenced together.
    UNIQUE (id, user_id)
);
-- Cascading deletes from problem_signals look rows up by signal_id.
CREATE INDEX idx_suggestions_signal ON suggestions (signal_id);

CREATE TABLE feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    suggestion_id   UUID NOT NULL,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating          SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- One piece of feedback per user per suggestion.
    UNIQUE (user_id, suggestion_id),
    -- Composite FK: the feedback's user_id must be the user the suggestion
    -- was made to. Storing user_id here makes "all feedback by user X" a
    -- single-table query; this FK stops it from ever disagreeing with
    -- suggestions.user_id.
    FOREIGN KEY (suggestion_id, user_id)
        REFERENCES suggestions (id, user_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------
-- 5. Feasibility scoring (set-based)
-- ---------------------------------------------------------
-- Scores every candidate signal for one user in a single query, instead of
-- one function call (and three lookups) per candidate. Called by the
-- suggestions API after vector search has produced the shortlist:
--
--   SELECT * FROM score_candidates($1, $2::uuid[]);
--
-- score = skill_coverage * team_factor * time_factor, in [0, 1], where
--   skill_coverage = SUM(proficiency / 5 for each required skill the user has)
--                    / number of skills the signal requires
--                    (0.5 — neutral — if the signal has no tagged skills, so
--                    untagged signals are neither buried nor promoted)
--   team_factor    = LEAST(1, 0.6 + 0.1 * team_size): a solo builder gets 0.7,
--                    a team of 4+ gets 1.0 — teammates cover skill gaps
--   time_factor    = 0.85 if timeframe < 24h, else 1.0
-- Users without a constraints row get the defaults (team of 1, 48h).
-- Signal IDs that don't exist are silently dropped from the result.
CREATE OR REPLACE FUNCTION score_candidates(
    p_user_id    UUID,
    p_signal_ids UUID[]
) RETURNS TABLE (signal_id UUID, score REAL)
LANGUAGE sql
STABLE
AS $$
    WITH user_constraints AS (
        -- An aggregate with no GROUP BY always yields exactly one row, so
        -- the defaults apply when the user has no constraints row.
        SELECT COALESCE(MAX(c.team_size), 1)        AS team_size,
               COALESCE(MAX(c.timeframe_hours), 48) AS timeframe_hours
        FROM constraints c
        WHERE c.user_id = p_user_id
    ),
    coverage AS (
        SELECT ps.id                                   AS signal_id,
               COUNT(ss.skill_id)                      AS required_skills,
               COALESCE(SUM(us.proficiency / 5.0), 0)  AS weighted_matches
        FROM problem_signals ps
        LEFT JOIN signal_skills ss ON ss.signal_id = ps.id
        LEFT JOIN user_skills   us ON us.skill_id = ss.skill_id
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

-- Single-signal convenience wrapper, kept for readability in ad-hoc queries
-- and docs. Application code should call score_candidates() with the whole
-- shortlist instead of looping over this.
CREATE OR REPLACE FUNCTION compute_feasibility_score(
    p_user_id   UUID,
    p_signal_id UUID
) RETURNS REAL
LANGUAGE sql
STABLE
AS $$
    SELECT sc.score FROM score_candidates(p_user_id, ARRAY[p_signal_id]) sc;
$$;

-- ---------------------------------------------------------
-- 6. Staleness
-- ---------------------------------------------------------
-- A signal is stale once its age — measured from when it was *published*,
-- falling back to when we fetched it — passes 30 days. Using published_at
-- matters: an arXiv paper from last year that we only just fetched is not
-- fresh. Staleness is one-way: nothing here sets is_stale back to false, so
-- a signal a curator retired by hand stays retired.

-- Callable from a scheduled job (and from the trigger below). Returns how
-- many rows were newly marked stale. The WHERE clause matches
-- idx_problem_signals_stale_candidates exactly, so it reads only the
-- not-yet-stale rows past the cutoff and never rewrites already-stale rows.
CREATE OR REPLACE FUNCTION expire_stale_signals() RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INTEGER;
BEGIN
    UPDATE problem_signals
    SET is_stale = true
    WHERE is_stale = false
      AND COALESCE(published_at, fetched_at) < now() - INTERVAL '30 days';
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

-- Row-level: decide staleness for the incoming row itself before it is
-- written, so an old item (e.g. a backfilled paper) is never visible as
-- fresh, and without a second UPDATE on the same row.
CREATE OR REPLACE FUNCTION set_signal_staleness() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF COALESCE(NEW.published_at, NEW.fetched_at) < now() - INTERVAL '30 days' THEN
        NEW.is_stale := true;
    END IF;
    RETURN NEW;
END;
$$;

-- Fires only when a date that staleness depends on is written.
CREATE TRIGGER trg_set_signal_staleness
    BEFORE INSERT OR UPDATE OF published_at, fetched_at ON problem_signals
    FOR EACH ROW
    EXECUTE FUNCTION set_signal_staleness();

-- Statement-level: after each ingestion insert, sweep *existing* rows that
-- have aged past the cutoff since the last run. Thanks to the partial index
-- this is an index range scan that usually finds nothing. The scheduled job
-- calling expire_stale_signals() covers quiet periods with no inserts.
CREATE OR REPLACE FUNCTION sweep_stale_signals() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM expire_stale_signals();
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_sweep_stale_signals
    AFTER INSERT ON problem_signals
    FOR EACH STATEMENT
    EXECUTE FUNCTION sweep_stale_signals();

-- ---------------------------------------------------------
-- 7. Graph sync outbox (Postgres -> Neo4j)
-- ---------------------------------------------------------
-- Transactional outbox: triggers write a row here in the same transaction
-- as the change, so a change is recorded exactly when it commits, and never
-- when it rolls back. A sync worker drains the queue into Neo4j.
--
-- Consumer contract (state-based, idempotent):
--   1. SELECT ... WHERE processed_at IS NULL ORDER BY id
--      FOR UPDATE SKIP LOCKED LIMIT n
--   2. For each distinct entity_id (always a users.id), re-read that user's
--      current name, skills, interests, and collaborations from Postgres.
--      If the user no longer exists, DETACH DELETE the (:User) node;
--      otherwise MERGE the node and replace its HAS_SKILL, INTERESTED_IN,
--      and COLLABORATED_WITH edges.
--   3. SET processed_at = now() on the batch.
-- Because step 2 copies current state rather than replaying deltas, events
-- can be processed late, twice, or collapsed per user without drift.
CREATE TABLE graph_sync_queue (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_type     TEXT NOT NULL CHECK (entity_type IN ('user', 'user_skill', 'user_interest', 'collaboration')),
    -- The affected users.id. Deliberately not a foreign key: DELETE events
    -- must survive the user row being deleted.
    entity_id       UUID NOT NULL,
    op              TEXT NOT NULL CHECK (op IN ('INSERT', 'UPDATE', 'DELETE')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at    TIMESTAMPTZ
);
-- The worker's poll: pending events in id order. Partial, so processed
-- history doesn't bloat it.
CREATE INDEX idx_graph_sync_queue_pending ON graph_sync_queue (id) WHERE processed_at IS NULL;

CREATE OR REPLACE FUNCTION enqueue_user_graph_sync() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO graph_sync_queue (entity_type, entity_id, op) VALUES ('user', OLD.id, TG_OP);
    ELSE
        INSERT INTO graph_sync_queue (entity_type, entity_id, op) VALUES ('user', NEW.id, TG_OP);
    END IF;
    RETURN NULL;
END;
$$;

-- For user_skills / user_interests. TG_ARGV[0] is the entity_type.
CREATE OR REPLACE FUNCTION enqueue_user_link_graph_sync() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        INSERT INTO graph_sync_queue (entity_type, entity_id, op) VALUES (TG_ARGV[0], OLD.user_id, TG_OP);
    END IF;
    -- On UPDATE, only enqueue NEW too if the row moved to a different user.
    IF TG_OP = 'INSERT' OR (TG_OP = 'UPDATE' AND NEW.user_id IS DISTINCT FROM OLD.user_id) THEN
        INSERT INTO graph_sync_queue (entity_type, entity_id, op) VALUES (TG_ARGV[0], NEW.user_id, TG_OP);
    END IF;
    RETURN NULL;
END;
$$;

-- For collaborations: a pair touches two users, so enqueue both. On UPDATE
-- that changes the pair, the old and new users are all enqueued; duplicates
-- are harmless because the consumer collapses events per user.
CREATE OR REPLACE FUNCTION enqueue_collaboration_graph_sync() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        INSERT INTO graph_sync_queue (entity_type, entity_id, op)
        VALUES ('collaboration', OLD.user_a, TG_OP), ('collaboration', OLD.user_b, TG_OP);
    END IF;
    IF TG_OP = 'INSERT'
       OR (TG_OP = 'UPDATE' AND (NEW.user_a, NEW.user_b) IS DISTINCT FROM (OLD.user_a, OLD.user_b)) THEN
        INSERT INTO graph_sync_queue (entity_type, entity_id, op)
        VALUES ('collaboration', NEW.user_a, TG_OP), ('collaboration', NEW.user_b, TG_OP);
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_users_graph_sync
    AFTER INSERT OR DELETE ON users
    FOR EACH ROW
    EXECUTE FUNCTION enqueue_user_graph_sync();

-- Neo4j only stores id and name, so password, email, role, and embedding
-- updates don't generate sync traffic.
CREATE TRIGGER trg_users_graph_sync_name
    AFTER UPDATE OF name ON users
    FOR EACH ROW
    WHEN (OLD.name IS DISTINCT FROM NEW.name)
    EXECUTE FUNCTION enqueue_user_graph_sync();

CREATE TRIGGER trg_user_skills_graph_sync
    AFTER INSERT OR UPDATE OR DELETE ON user_skills
    FOR EACH ROW
    EXECUTE FUNCTION enqueue_user_link_graph_sync('user_skill');

CREATE TRIGGER trg_user_interests_graph_sync
    AFTER INSERT OR UPDATE OR DELETE ON user_interests
    FOR EACH ROW
    EXECUTE FUNCTION enqueue_user_link_graph_sync('user_interest');

-- Fires on any change, including a project_name-only UPDATE, because the
-- graph edge carries project_name too.
CREATE TRIGGER trg_collaborations_graph_sync
    AFTER INSERT OR UPDATE OR DELETE ON collaborations
    FOR EACH ROW
    EXECUTE FUNCTION enqueue_collaboration_graph_sync();

-- ---------------------------------------------------------
-- 8. Materialized view — trending problem areas
-- ---------------------------------------------------------
CREATE MATERIALIZED VIEW trending_problem_areas AS
SELECT
    tag              AS category,
    COUNT(*)         AS signal_count,
    MAX(ps.fetched_at) AS most_recent
FROM problem_signals ps
CROSS JOIN LATERAL unnest(ps.category_tags) AS tag
WHERE ps.fetched_at > now() - INTERVAL '14 days'
  AND ps.is_stale = false
GROUP BY tag;

-- A unique index is required for REFRESH ... CONCURRENTLY, which rebuilds
-- the view without taking a lock that blocks readers of the trending page.
-- `category` is unique by construction (it is the GROUP BY key), and the
-- CHECK on category_tags keeps NULL tags out.
CREATE UNIQUE INDEX idx_trending_problem_areas_category ON trending_problem_areas (category);

-- Refresh after each ingestion run (sort at query time with ORDER BY):
-- REFRESH MATERIALIZED VIEW CONCURRENTLY trending_problem_areas;

-- ---------------------------------------------------------
-- 9. Reference data (needed by the app, not demo data — see seed.sql)
-- ---------------------------------------------------------
INSERT INTO skills (name) VALUES
    ('javascript'), ('typescript'), ('python'), ('react'), ('nextjs'),
    ('machine-learning'), ('computer-vision'), ('nlp'), ('postgresql'),
    ('neo4j'), ('vector-search'), ('ui-design'), ('mobile'), ('devops'),
    ('rust'), ('go'), ('data-engineering'), ('geospatial'), ('iot'), ('llm')
ON CONFLICT (name) DO NOTHING;

-- Interests double as the vocabulary for problem_signals.category_tags.
INSERT INTO interests (name) VALUES
    ('climate'), ('healthtech'), ('accessibility'), ('fintech-alt'),
    ('education'), ('security'), ('conservation'), ('civic-tech'),
    ('developer-tools'), ('research-tools')
ON CONFLICT (name) DO NOTHING;
