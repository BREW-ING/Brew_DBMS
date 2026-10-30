-- =========================================================
-- Brew — demo reports (run in the Supabase SQL Editor)
-- =========================================================
-- Each report is one query. Run them one at a time.

-- ---------------------------------------------------------
-- R1. Problem signals collected per source
--     (COUNT, GROUP BY, conditional aggregates)
-- ---------------------------------------------------------
SELECT source,
       COUNT(*)                                   AS total_signals,
       COUNT(*) FILTER (WHERE NOT is_stale)       AS fresh,
       COUNT(*) FILTER (WHERE is_stale)           AS stale,
       COUNT(*) FILTER (WHERE embedded)           AS embedded,
       MAX(fetched_at)::date                      AS last_fetched
FROM problem_signals
GROUP BY source
ORDER BY total_signals DESC;

-- ---------------------------------------------------------
-- R2. Average proficiency of users per skill
--     (the "average salary per department" equivalent: AVG + JOIN + GROUP BY)
-- ---------------------------------------------------------
SELECT s.name                          AS skill,
       COUNT(us.user_id)               AS users_with_skill,
       ROUND(AVG(us.proficiency), 2)   AS avg_proficiency,
       MAX(us.proficiency)             AS max_proficiency
FROM skills s
JOIN user_skills us ON us.skill_id = s.id
GROUP BY s.name
ORDER BY users_with_skill DESC, avg_proficiency DESC;

-- ---------------------------------------------------------
-- R3. Skill supply vs demand (gap analysis)
--     How many users HAVE each skill vs how many problems NEED it.
--     (two aggregated subqueries joined, LEFT JOIN, COALESCE)
-- ---------------------------------------------------------
SELECT s.name                                       AS skill,
       COALESCE(supply.users, 0)                    AS users_who_have_it,
       COALESCE(demand.signals, 0)                  AS problems_needing_it,
       COALESCE(demand.signals, 0) - COALESCE(supply.users, 0) AS gap
FROM skills s
LEFT JOIN (SELECT skill_id, COUNT(*) AS users
           FROM user_skills GROUP BY skill_id) supply ON supply.skill_id = s.id
LEFT JOIN (SELECT skill_id, COUNT(*) AS signals
           FROM signal_skills GROUP BY skill_id) demand ON demand.skill_id = s.id
WHERE supply.users IS NOT NULL OR demand.signals IS NOT NULL
ORDER BY gap DESC;

-- ---------------------------------------------------------
-- R4. Number of users per interest area
-- ---------------------------------------------------------
SELECT i.name AS interest, COUNT(ui.user_id) AS users
FROM interests i
LEFT JOIN user_interests ui ON ui.interest_id = i.id
GROUP BY i.name
ORDER BY users DESC, interest;

-- ---------------------------------------------------------
-- R5. Average team size and time budget, by user role
-- ---------------------------------------------------------
SELECT u.role,
       COUNT(*)                            AS users,
       ROUND(AVG(c.team_size), 1)          AS avg_team_size,
       ROUND(AVG(c.timeframe_hours), 1)    AS avg_hours_available
FROM users u
JOIN constraints c ON c.user_id = u.id
GROUP BY u.role;

-- ---------------------------------------------------------
-- R6. Most-collaborative users (UNION ALL of both sides of the pair)
-- ---------------------------------------------------------
SELECT u.name, COUNT(*) AS past_collaborations
FROM (SELECT user_a AS user_id FROM collaborations
      UNION ALL
      SELECT user_b FROM collaborations) x
JOIN users u ON u.id = x.user_id
GROUP BY u.name
ORDER BY past_collaborations DESC, u.name;

-- ---------------------------------------------------------
-- R7. Top 5 most feasible problems for each user
--     (stored function + LATERAL join + window function RANK)
-- ---------------------------------------------------------
SELECT name, rank, score, title
FROM (
    SELECT u.name,
           left(ps.title, 60)                                         AS title,
           ROUND(sc.score::numeric, 3)                                AS score,
           RANK() OVER (PARTITION BY u.id ORDER BY sc.score DESC)     AS rank
    FROM users u
    CROSS JOIN LATERAL score_candidates(
        u.id, ARRAY(SELECT id FROM problem_signals WHERE NOT is_stale)) sc
    JOIN problem_signals ps ON ps.id = sc.signal_id
) ranked
WHERE rank <= 5
ORDER BY name, rank;

-- ---------------------------------------------------------
-- R8. Average feasibility of all fresh problems, per user
--     (aggregate over a stored function's output)
-- ---------------------------------------------------------
SELECT u.name,
       ROUND(AVG(sc.score)::numeric, 3)  AS avg_feasibility,
       COUNT(*) FILTER (WHERE sc.score >= 0.5) AS problems_feasible_for_them
FROM users u
CROSS JOIN LATERAL score_candidates(
    u.id, ARRAY(SELECT id FROM problem_signals WHERE NOT is_stale)) sc
GROUP BY u.name
ORDER BY avg_feasibility DESC;

-- ---------------------------------------------------------
-- R9. Trending problem areas (materialized view)
-- ---------------------------------------------------------
REFRESH MATERIALIZED VIEW CONCURRENTLY trending_problem_areas;
SELECT * FROM trending_problem_areas ORDER BY signal_count DESC LIMIT 10;

-- ---------------------------------------------------------
-- R10. Pending Postgres -> Neo4j sync events (outbox table)
-- ---------------------------------------------------------
SELECT entity_type, op, COUNT(*) AS pending
FROM graph_sync_queue
WHERE processed_at IS NULL
GROUP BY entity_type, op
ORDER BY entity_type, op;
