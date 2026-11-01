"""Teammate recommendations: the 2-hop Cypher query vs an equivalent SQL query.

The Cypher is db/neo4j/queries/teammates.cypher itself, with its labels and
relationship types renamed (User -> BenchUser, HAS_SKILL -> BENCH_HAS_SKILL,
...) so it only ever matches benchmark nodes, never the real graph. TEAMMATES_SQL
below computes the same scores over the bench Postgres tables. Both engines
get the same synthetic graph (scripts.generate_synthetic_users), and every
query's top-10 is compared between them; any mismatch aborts the run.

Server time: Neo4j's result_available_after + result_consumed_after (whole
milliseconds) vs Postgres's EXPLAIN ANALYZE Execution Time. Wall clock adds
the round trip to each hosted service, which differ (Aura vs Supabase region).

Run from the repo root:
    python -m benchmarks.bench_teammates --users 5000
"""

import argparse
import os
import random
import re
from collections.abc import Iterator, Sequence
from typing import Any, TypeVar

import psycopg
from neo4j import Driver, GraphDatabase, RoutingControl

from benchmarks.common import (
    INTERESTS,
    REPO_ROOT,
    SEED,
    SKILLS,
    explain,
    load_env,
    pg_connect,
    summarize,
    timed,
)
from benchmarks.scripts.generate_synthetic_users import UserGraph, build_user_graph, load_postgres

TEAMMATES_CYPHER = REPO_ROOT / "db" / "neo4j" / "queries" / "teammates.cypher"
LIMIT = 10
WARMUP_QUERIES = 5
BATCH = 1000

RENAMES = {
    "User": "BenchUser",
    "Skill": "BenchSkill",
    "Interest": "BenchInterest",
    "HAS_SKILL": "BENCH_HAS_SKILL",
    "INTERESTED_IN": "BENCH_INTERESTED_IN",
    "COLLABORATED_WITH": "BENCH_COLLABORATED_WITH",
}
BENCH_LABELS = ("BenchUser", "BenchSkill", "BenchInterest")

# Same scoring as teammates.cypher, over the bench tables:
#   +2.0 per complementary skill, -0.5 per overlapping skill,
#   +1.5 per shared interest, +1.0 per mutual collaborator (max 3),
#   +1.0 for a direct past collaboration; candidates need >= 1 complementary skill.
TEAMMATES_SQL = """
WITH my_skills AS (
    SELECT skill_id FROM bench.user_skills WHERE user_id = %(user_id)s::uuid
),
my_interests AS (
    SELECT interest_id FROM bench.user_interests WHERE user_id = %(user_id)s::uuid
),
-- collaborations stores each pair once (user_a < user_b); read it both ways.
edges AS (
    SELECT user_a AS src, user_b AS dst FROM bench.collaborations
    UNION ALL
    SELECT user_b, user_a FROM bench.collaborations
),
my_collaborators AS (
    SELECT dst AS user_id FROM edges WHERE src = %(user_id)s::uuid
),
complementary AS (
    SELECT us.user_id, array_agg(s.name ORDER BY s.name) AS skills
    FROM bench.user_skills us
    JOIN bench.skills s ON s.id = us.skill_id
    WHERE us.user_id <> %(user_id)s::uuid
      AND us.skill_id NOT IN (SELECT skill_id FROM my_skills)
    GROUP BY us.user_id
),
overlapping AS (
    SELECT user_id, count(*) AS n
    FROM bench.user_skills
    WHERE skill_id IN (SELECT skill_id FROM my_skills)
    GROUP BY user_id
),
shared_interests AS (
    SELECT ui.user_id, array_agg(i.name ORDER BY i.name) AS interests
    FROM bench.user_interests ui
    JOIN bench.interests i ON i.id = ui.interest_id
    WHERE ui.interest_id IN (SELECT interest_id FROM my_interests)
    GROUP BY ui.user_id
),
-- 2 hops: candidates who collaborated with one of my collaborators.
mutual AS (
    SELECT e.dst AS user_id, array_agg(DISTINCT mid.name) AS names
    FROM my_collaborators mc
    JOIN edges e ON e.src = mc.user_id
    JOIN bench.users mid ON mid.id = mc.user_id
    WHERE e.dst <> %(user_id)s::uuid
    GROUP BY e.dst
)
SELECT u.id::text AS user_id,
       u.name,
       (  2.0 * cardinality(c.skills)
        - 0.5 * COALESCE(o.n, 0)
        + 1.5 * COALESCE(cardinality(si.interests), 0)
        + 1.0 * LEAST(COALESCE(cardinality(m.names), 0), 3)
        + CASE WHEN pc.user_id IS NOT NULL THEN 1.0 ELSE 0.0 END)::float8 AS score,
       c.skills AS complementary_skills,
       COALESCE(si.interests, '{}') AS shared_interests,
       COALESCE(m.names, '{}') AS mutual_collaborators,
       pc.user_id IS NOT NULL AS past_collaborator
FROM complementary c
JOIN bench.users u ON u.id = c.user_id
LEFT JOIN overlapping o ON o.user_id = c.user_id
LEFT JOIN shared_interests si ON si.user_id = c.user_id
LEFT JOIN mutual m ON m.user_id = c.user_id
LEFT JOIN my_collaborators pc ON pc.user_id = c.user_id
-- "C" collation: plain code-point order, like Cypher's string ORDER BY.
ORDER BY score DESC, u.name COLLATE "C"
LIMIT %(limit)s
"""

T = TypeVar("T")


def bench_cypher() -> str:
    """teammates.cypher with every label / relationship type renamed to its Bench* twin."""
    text = TEAMMATES_CYPHER.read_text(encoding="utf-8")
    for old, new in RENAMES.items():
        text = re.sub(rf":{old}\b", f":{new}", text)
    leftover = re.search(rf":({'|'.join(RENAMES)})\b", text)
    if leftover:
        raise RuntimeError(f"teammates.cypher still references {leftover.group(0)} after renaming")
    return text.strip().rstrip(";")


def neo4j_driver() -> Driver:
    load_env()
    uri, user, password = (os.environ.get(k) for k in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"))
    if not uri or not user or not password:
        raise RuntimeError("NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD must be set")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver


def neo4j_version(driver: Driver) -> str:
    records, _, _ = driver.execute_query(
        "CALL dbms.components() YIELD versions, edition RETURN versions[0] + ' ' + edition AS v",
        routing_=RoutingControl.READ,
    )
    return str(records[0]["v"])


def _chunks(rows: Sequence[T]) -> Iterator[Sequence[T]]:
    for start in range(0, len(rows), BATCH):
        yield rows[start : start + BATCH]


def clear_neo4j(driver: Driver) -> None:
    """Delete every Bench* node (and so its relationships) and the bench constraints."""
    with driver.session() as session:
        for label in BENCH_LABELS:
            # CALL ... IN TRANSACTIONS needs an auto-commit transaction (session.run).
            session.run(
                f"MATCH (n:{label}) CALL {{ WITH n DETACH DELETE n }} IN TRANSACTIONS OF {BATCH} ROWS"
            ).consume()
    for label in BENCH_LABELS:
        driver.execute_query(f"DROP CONSTRAINT {label.lower()}_bench_key IF EXISTS")


def load_neo4j(driver: Driver, graph: UserGraph) -> None:
    """Replace the Bench* subgraph with `graph`, mirroring the real graph model."""
    clear_neo4j(driver)
    for label, key in (("BenchUser", "id"), ("BenchSkill", "name"), ("BenchInterest", "name")):
        driver.execute_query(
            f"CREATE CONSTRAINT {label.lower()}_bench_key IF NOT EXISTS"
            f" FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
        )
    driver.execute_query("UNWIND $names AS name CREATE (:BenchSkill {name: name})", names=list(SKILLS))
    driver.execute_query("UNWIND $names AS name CREATE (:BenchInterest {name: name})", names=list(INTERESTS))

    statements: list[tuple[str, list[dict[str, Any]]]] = [
        (
            "UNWIND $rows AS row CREATE (:BenchUser {id: row.id, name: row.name})",
            [{"id": str(uid), "name": name} for uid, name in graph.users],
        ),
        (
            "UNWIND $rows AS row MATCH (u:BenchUser {id: row.user}), (s:BenchSkill {name: row.skill})"
            " CREATE (u)-[:BENCH_HAS_SKILL {proficiency: row.p}]->(s)",
            [{"user": str(u), "skill": SKILLS[s - 1], "p": p} for u, s, p in graph.user_skills],
        ),
        (
            "UNWIND $rows AS row MATCH (u:BenchUser {id: row.user}), (i:BenchInterest {name: row.interest})"
            " CREATE (u)-[:BENCH_INTERESTED_IN]->(i)",
            [{"user": str(u), "interest": INTERESTS[i - 1]} for u, i in graph.user_interests],
        ),
        (
            # One edge per pair, lower id -> higher id, as in the real graph.
            "UNWIND $rows AS row MATCH (a:BenchUser {id: row.a}), (b:BenchUser {id: row.b})"
            " CREATE (a)-[:BENCH_COLLABORATED_WITH {project_name: row.project}]->(b)",
            [{"a": str(a), "b": str(b), "project": p} for a, b, p in graph.collaborations],
        ),
    ]
    for query, rows in statements:
        for batch in _chunks(rows):
            driver.execute_query(query, rows=list(batch))


def _normalize(user_id: str, score: float, skills: list[str], interests: list[str],
               mutual: list[str], past: bool) -> tuple[Any, ...]:
    # List order inside a row is not part of the contract; compare as sorted.
    return (user_id, round(score, 6), sorted(skills), sorted(interests), sorted(mutual), past)


def run_teammates(
    conn: psycopg.Connection, driver: Driver, graph: UserGraph, n_queries: int, seed: int = SEED
) -> dict[str, Any]:
    """Run both queries for `n_queries` random users; return timings and agreement."""
    cypher = bench_cypher()
    rng = random.Random(seed + 3)
    users = [str(uid) for uid, _ in rng.sample(graph.users, min(n_queries, len(graph.users)))]

    def run_cypher(user_id: str) -> Any:
        return driver.execute_query(cypher, userId=user_id, limit=LIMIT, routing_=RoutingControl.READ)

    def run_sql(user_id: str) -> list[tuple[Any, ...]]:
        return conn.execute(TEAMMATES_SQL, {"user_id": user_id, "limit": LIMIT}).fetchall()

    for user_id in users[:WARMUP_QUERIES]:
        run_cypher(user_id)
        run_sql(user_id)

    samples: dict[str, list[float]] = {k: [] for k in ("neo4j_server", "neo4j_wall", "pg_server", "pg_wall")}
    mismatches = 0
    for user_id in users:
        (records, summary, _), neo_wall = timed(lambda: run_cypher(user_id))
        rows, pg_wall = timed(lambda: run_sql(user_id))
        pg_ms, _ = explain(conn, TEAMMATES_SQL, {"user_id": user_id, "limit": LIMIT})

        neo = [
            _normalize(r["userId"], r["score"], r["complementarySkills"], r["sharedInterests"],
                       r["mutualCollaborators"], r["pastCollaborator"])
            for r in records
        ]
        pg = [_normalize(r[0], r[2], r[3], r[4], r[5], r[6]) for r in rows]
        if neo != pg:
            mismatches += 1
            print(f"  MISMATCH for {user_id}:\n    neo4j {neo[:3]}\n    sql   {pg[:3]}", flush=True)

        samples["neo4j_server"].append(float(summary.result_available_after + summary.result_consumed_after))
        samples["neo4j_wall"].append(neo_wall)
        samples["pg_server"].append(pg_ms)
        samples["pg_wall"].append(pg_wall)

    if mismatches:
        raise RuntimeError(f"Cypher and SQL disagreed for {mismatches}/{len(users)} users")
    return {
        "users": len(graph.users),
        "collaborations": len(graph.collaborations),
        "user_skills": len(graph.user_skills),
        "queries": len(users),
        "agreement": f"{len(users)}/{len(users)}",
        "neo4j": {"server_ms": summarize(samples["neo4j_server"]), "wall_ms": summarize(samples["neo4j_wall"])},
        "postgres": {"server_ms": summarize(samples["pg_server"]), "wall_ms": summarize(samples["pg_wall"])},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--users", type=int, default=5000)
    parser.add_argument("--queries", type=int, default=100)
    args = parser.parse_args()
    graph = build_user_graph(args.users)
    with pg_connect() as conn, neo4j_driver() as driver:
        load_postgres(conn, graph)
        load_neo4j(driver, graph)
        result = run_teammates(conn, driver, graph, args.queries)
    print(result)


if __name__ == "__main__":
    main()
