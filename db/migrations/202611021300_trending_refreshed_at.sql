-- =========================================================
-- trending_problem_areas: record when the view was last refreshed
-- =========================================================
-- Postgres doesn't track when a materialized view was refreshed, and the
-- trending page shows a "last refreshed" time. now() inside the view's query
-- is evaluated on every REFRESH, so a refreshed_at column records it without
-- any change to the callers (fetch_signals.py, seed.sql, reports.sql R9).
--
-- A materialized view's query can't be altered in place, so drop and
-- recreate it, with the unique index REFRESH ... CONCURRENTLY needs.
-- Nothing else depends on the view.

BEGIN;

DROP MATERIALIZED VIEW trending_problem_areas;

CREATE MATERIALIZED VIEW trending_problem_areas AS
SELECT
    tag                AS category,
    COUNT(*)           AS signal_count,
    MAX(ps.fetched_at) AS most_recent,
    now()              AS refreshed_at
FROM problem_signals ps
CROSS JOIN LATERAL unnest(ps.category_tags) AS tag
WHERE ps.fetched_at > now() - INTERVAL '14 days'
  AND ps.is_stale = false
GROUP BY tag;

CREATE UNIQUE INDEX idx_trending_problem_areas_category ON trending_problem_areas (category);

COMMIT;
