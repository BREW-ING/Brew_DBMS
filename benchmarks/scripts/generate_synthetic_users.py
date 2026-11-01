"""Build a synthetic user graph and load it into the bench Postgres tables.

The graph is generated in Python from a fixed seed, so the exact same users,
skills, interests and collaborations can be loaded into both Postgres (here)
and Neo4j (benchmarks/bench_teammates.py) for the teammate comparison. The
feasibility benchmark uses the same users and their constraints rows.

Replaces whatever bench.users held before. Run from the repo root:
    python -m benchmarks.scripts.generate_synthetic_users --users 5000
"""

import argparse
import random
from dataclasses import dataclass
from uuid import UUID

import psycopg

from benchmarks.common import INTERESTS, SEED, SKILLS, ensure_schema, pg_connect


@dataclass(frozen=True)
class UserGraph:
    users: list[tuple[UUID, str]]
    user_skills: list[tuple[UUID, int, int]]  # (user, skill id, proficiency)
    user_interests: list[tuple[UUID, int]]  # (user, interest id)
    collaborations: list[tuple[UUID, UUID, str]]  # (user_a < user_b, project)
    constraints: list[tuple[UUID, int, int]]  # (user, team size, timeframe hours)


def build_user_graph(n_users: int, seed: int = SEED) -> UserGraph:
    """2-5 skills, 1-3 interests and 0-3 new collaborators per user (~3 edges each)."""
    rng = random.Random(seed)
    width = len(str(n_users))
    ids = [UUID(int=rng.getrandbits(128), version=4) for _ in range(n_users)]
    users = [(uid, f"Bench User {i:0{width}d}") for i, uid in enumerate(ids, start=1)]

    user_skills = []
    user_interests = []
    constraints = []
    pairs: dict[tuple[UUID, UUID], str] = {}
    for uid in ids:
        for skill_id in rng.sample(range(1, len(SKILLS) + 1), rng.randint(2, 5)):
            user_skills.append((uid, skill_id, rng.randint(1, 5)))
        for interest_id in rng.sample(range(1, len(INTERESTS) + 1), rng.randint(1, 3)):
            user_interests.append((uid, interest_id))
        constraints.append((uid, rng.randint(1, 5), rng.choice((12, 24, 48, 72))))
        for other in rng.sample(ids, rng.randint(0, 3)):
            if other != uid:
                # Python UUID ordering matches Postgres's byte-wise uuid ordering.
                pair = (min(uid, other), max(uid, other))
                pairs.setdefault(pair, f"bench-project-{len(pairs) + 1}")
    collaborations = [(a, b, name) for (a, b), name in pairs.items()]
    return UserGraph(users, user_skills, user_interests, collaborations, constraints)


def load_postgres(conn: psycopg.Connection, graph: UserGraph) -> None:
    """Replace the bench user tables with `graph` (COPY, one transaction)."""
    ensure_schema(conn)
    with conn.transaction(), conn.cursor() as cur:
        # Cascades to user_skills, user_interests, collaborations, constraints.
        cur.execute("TRUNCATE bench.users CASCADE")
        tables = (
            ("bench.users (id, name)", graph.users),
            ("bench.user_skills (user_id, skill_id, proficiency)", graph.user_skills),
            ("bench.user_interests (user_id, interest_id)", graph.user_interests),
            ("bench.collaborations (user_a, user_b, project_name)", graph.collaborations),
            ("bench.constraints (user_id, team_size, timeframe_hours)", graph.constraints),
        )
        for target, rows in tables:
            with cur.copy(f"COPY {target} FROM STDIN") as copy:
                for row in rows:
                    copy.write_row(row)
    for table in ("users", "user_skills", "user_interests", "collaborations", "constraints"):
        conn.execute(f"VACUUM ANALYZE bench.{table}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--users", type=int, required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    graph = build_user_graph(args.users, args.seed)
    with pg_connect() as conn:
        load_postgres(conn, graph)
    print(f"Loaded {len(graph.users):,} users, {len(graph.collaborations):,} collaborations")


if __name__ == "__main__":
    main()
