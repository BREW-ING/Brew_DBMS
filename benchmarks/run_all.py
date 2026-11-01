"""Run every benchmark, save benchmarks/results/latest.json, write docs/BENCHMARKS.md.

Run from the repo root:
    python -m benchmarks.run_all                       # everything, defaults
    python -m benchmarks.run_all --sizes 10000,50000   # fewer vector sizes
    python -m benchmarks.run_all --only vector         # one section; the others keep their last results

Order: teammates (loads users into Postgres and Neo4j), then for each N the
signals load + vector benchmark, with the feasibility benchmark on the largest
N that was loaded. Only one N is stored at a time; each load replaces the last.
Unless --keep-data is given, the bench schema and Bench* nodes are dropped at
the end, whether or not the run succeeded.
"""

import argparse
from typing import Any

import psycopg
from neo4j import Driver

from benchmarks import bench_feasibility, bench_teammates, bench_vector, cleanup, report
from benchmarks.common import SEED, ensure_schema, load_results, pg_connect, pg_environment, save_results
from benchmarks.scripts.generate_synthetic_signals import generate_signals
from benchmarks.scripts.generate_synthetic_users import build_user_graph, load_postgres

SECTIONS = ("vector", "feasibility", "teammates")

# Disk per synthetic signal: ~1.6 KB heap row + ~2 KB HNSW element + ~0.1 KB
# signal_skills. Rounded up; used only for the --db-budget-mb guard.
BYTES_PER_SIGNAL = 4 * 1024


def _ints(text: str) -> list[int]:
    return [int(x) for x in text.split(",") if x.strip()]


def _fits(conn: psycopg.Connection, n: int, budget_mb: int) -> str | None:
    """None if n signals fit under the budget, else the reason they don't."""
    if budget_mb <= 0:
        return None
    row = conn.execute(
        """
        SELECT pg_database_size(current_database()),
               COALESCE(sum(pg_total_relation_size(c.oid)), 0)
        FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
        WHERE ns.nspname = 'bench' AND c.relkind IN ('r', 'm')
        """
    ).fetchone()
    assert row is not None
    # The bench tables are truncated before each load, so they don't count.
    other_mb = (row[0] - row[1]) / 1024**2
    need_mb = n * BYTES_PER_SIGNAL / 1024**2
    if other_mb + need_mb <= budget_mb:
        return None
    return (
        f"needs ~{need_mb:,.0f} MB on top of {other_mb:,.0f} MB already used, over the"
        f" {budget_mb} MB --db-budget-mb (raise it if your plan has more space)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sizes", type=_ints, default=[10_000, 50_000, 100_000], help="signal counts")
    parser.add_argument("--users", type=_ints, default=[1_000, 5_000], help="user-graph sizes")
    parser.add_argument("--queries", type=int, default=100, help="vector queries per config")
    parser.add_argument("--trials", type=int, default=50, help="feasibility trials")
    parser.add_argument("--teammate-queries", type=int, default=100)
    parser.add_argument("--only", choices=SECTIONS, action="append", help="repeatable; default all")
    parser.add_argument("--maintenance-work-mem", help="for the HNSW build, e.g. 256MB")
    parser.add_argument(
        "--db-budget-mb", type=int, default=500,
        help="skip signal sizes that would push the database past this (Supabase free tier: 500); 0 disables",
    )
    parser.add_argument("--keep-data", action="store_true", help="don't drop the bench data at the end")
    args = parser.parse_args()
    sections = set(args.only or SECTIONS)

    results: dict[str, Any] = load_results()
    results["config"] = {"seed": SEED, "queries": args.queries, "trials": args.trials,
                         "teammate_queries": args.teammate_queries}
    driver = bench_teammates.neo4j_driver() if "teammates" in sections else None
    try:
        with pg_connect() as conn:
            ensure_schema(conn)
            env = pg_environment(conn)
            # Keep the Neo4j version from an earlier run if teammates isn't re-run.
            if "neo4j" in results.get("environment", {}):
                env["neo4j"] = results["environment"]["neo4j"]
            results["environment"] = env
            _run(conn, driver, args, sections, results)
    finally:
        if driver is not None:
            if not args.keep_data:
                bench_teammates.clear_neo4j(driver)
            driver.close()
        if not args.keep_data:
            cleanup.drop_postgres()
    report.write_report(results)
    print(f"Wrote {report.REPORT_PATH}")


def _run(
    conn: psycopg.Connection,
    driver: Driver | None,
    args: argparse.Namespace,
    sections: set[str],
    results: dict[str, Any],
) -> None:
    if driver is not None:
        results["environment"]["neo4j"] = bench_teammates.neo4j_version(driver)
        results["teammates"] = {}
        for n_users in args.users:
            print(f"Teammates: {n_users:,} users", flush=True)
            graph = build_user_graph(n_users)
            load_postgres(conn, graph)
            bench_teammates.load_neo4j(driver, graph)
            results["teammates"][str(n_users)] = bench_teammates.run_teammates(
                conn, driver, graph, args.teammate_queries
            )
            save_results(results)
    elif "feasibility" in sections:
        # Feasibility needs users even when the teammate section is skipped.
        load_postgres(conn, build_user_graph(args.users[-1]))

    if not sections & {"vector", "feasibility"}:
        return
    # Feasibility alone only needs the largest size.
    sizes = args.sizes if "vector" in sections else args.sizes[-1:]
    if "vector" in sections:
        results["vector"] = {}
    queries = bench_vector.query_vectors(args.queries)
    loaded = 0
    for n in sizes:
        reason = _fits(conn, n, args.db_budget_mb)
        if reason:
            print(f"Skipping N = {n:,}: {reason}", flush=True)
            if "vector" in sections:
                results["vector"][str(n)] = {"skipped": reason}
            continue
        print(f"Signals: N = {n:,}", flush=True)
        entry: dict[str, Any] = generate_signals(conn, n)
        loaded = n
        if "vector" in sections:
            entry["index"] = bench_vector.build_hnsw_index(conn, args.maintenance_work_mem)
            entry["configs"] = bench_vector.run_vector(conn, queries)
            results["vector"][str(n)] = entry
            save_results(results)

    if "feasibility" in sections:
        if not loaded:
            raise RuntimeError("no signal size fit under --db-budget-mb; nothing to score")
        print(f"Feasibility: {loaded:,} signals", flush=True)
        results["feasibility"] = bench_feasibility.run_feasibility(conn, loaded, args.trials)
        save_results(results)


if __name__ == "__main__":
    main()
