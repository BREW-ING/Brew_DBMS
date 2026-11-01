"""Remove all benchmark data: the bench Postgres schema and Bench* Neo4j nodes.

run_all does this at the end unless --keep-data was passed. Touches nothing
outside the bench schema / Bench* labels. Run from the repo root:
    python -m benchmarks.cleanup
"""

import os

from benchmarks.common import load_env, pg_connect


def drop_postgres() -> None:
    with pg_connect() as conn:
        conn.execute("DROP SCHEMA IF EXISTS bench CASCADE")


def main() -> None:
    drop_postgres()
    print("Dropped Postgres schema bench")
    load_env()
    if os.environ.get("NEO4J_URI"):
        # Imported here so cleaning Postgres doesn't need the neo4j package.
        from benchmarks.bench_teammates import clear_neo4j, neo4j_driver

        with neo4j_driver() as driver:
            clear_neo4j(driver)
        print("Deleted Bench* nodes from Neo4j")


if __name__ == "__main__":
    main()
