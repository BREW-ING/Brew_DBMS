"""Top-10 cosine search: sequential scan vs HNSW (ef_search 40 and 100).

Latency is the server-side Execution Time from EXPLAIN ANALYZE, so network
round trips to Supabase are excluded. Recall@10 compares each HNSW result with
the exact top 10 from the sequential scan for the same query. Every measured
plan is checked: a "seq" run that used the index (or the reverse) aborts.

Expects bench.problem_signals to be loaded (scripts.generate_synthetic_signals).
Run from the repo root:
    python -m benchmarks.bench_vector
"""

import argparse
import math
import random
import time
from typing import Any

import psycopg

from benchmarks.common import (
    EMBEDDING_DIM,
    SEED,
    explain,
    pg_connect,
    plan_nodes,
    plan_shape,
    summarize,
)

INDEX_NAME = "idx_bench_signals_embedding"
K = 10
WARMUP_QUERIES = 5

# Same shape as the nearest CTE in apps/web/lib/suggestions.ts, minus the
# staleness / feedback filters (synthetic rows have none to filter).
KNN_SQL = f"SELECT id FROM bench.problem_signals ORDER BY embedding <=> %s::vector LIMIT {K}"

# (key, label, session settings). Every config sets every knob, so none
# inherits a value from the one before.
CONFIGS: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("seq", "Sequential scan (exact)", {"enable_indexscan": "off", "hnsw.ef_search": "40"}),
    ("hnsw_40", "HNSW, ef_search = 40", {"enable_indexscan": "on", "hnsw.ef_search": "40"}),
    ("hnsw_100", "HNSW, ef_search = 100", {"enable_indexscan": "on", "hnsw.ef_search": "100"}),
)
DEFAULT_SETTINGS = {"enable_indexscan": "on", "hnsw.ef_search": "40"}


def query_vectors(n: int, seed: int = SEED) -> list[str]:
    """n random unit vectors in pgvector's text form; the same for every N."""
    rng = random.Random(seed + 1)  # independent of the users' stream
    vectors = []
    for _ in range(n):
        v = [rng.gauss(0.0, 1.0) for _ in range(EMBEDDING_DIM)]
        norm = math.sqrt(sum(x * x for x in v))
        vectors.append("[" + ",".join(f"{x / norm:.7f}" for x in v) + "]")
    return vectors


def build_hnsw_index(conn: psycopg.Connection, maintenance_work_mem: str | None) -> dict[str, float]:
    """Build the HNSW index with production parameters; return build time and sizes."""
    if maintenance_work_mem:
        conn.execute("SELECT set_config('maintenance_work_mem', %s, false)", [maintenance_work_mem])
    conn.execute(f"DROP INDEX IF EXISTS bench.{INDEX_NAME}")
    started = time.perf_counter()
    # m / ef_construction as in db/postgres/schema.sql.
    conn.execute(
        f"CREATE INDEX {INDEX_NAME} ON bench.problem_signals"
        " USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )
    build_s = time.perf_counter() - started
    conn.execute("ANALYZE bench.problem_signals")
    row = conn.execute(
        "SELECT pg_table_size('bench.problem_signals'), pg_relation_size(%s::regclass)",
        [f"bench.{INDEX_NAME}"],
    ).fetchone()
    assert row is not None
    return {"build_s": build_s, "table_bytes": row[0], "index_bytes": row[1]}


def _apply(conn: psycopg.Connection, settings: dict[str, str]) -> None:
    for name, value in settings.items():
        conn.execute("SELECT set_config(%s, %s, false)", [name, value])


def _check_plan(key: str, plan: dict[str, Any]) -> None:
    nodes = list(plan_nodes(plan))
    uses_index = any(n.get("Index Name") == INDEX_NAME for n in nodes)
    uses_seq = any(n["Node Type"] == "Seq Scan" for n in nodes)
    ok = (uses_seq and not uses_index) if key == "seq" else uses_index
    if not ok:
        raise RuntimeError(f"{key}: unexpected plan {plan_shape(plan)}")


def run_vector(conn: psycopg.Connection, queries: list[str]) -> dict[str, Any]:
    """Measure every config over `queries`; returns per-config latency and recall."""
    results: dict[str, Any] = {}
    exact: list[set[str]] = []
    for key, label, settings in CONFIGS:
        _apply(conn, settings)
        for q in queries[:WARMUP_QUERIES]:
            conn.execute(KNN_SQL, [q]).fetchall()

        latencies = []
        shape = ""
        for q in queries:
            ms, plan = explain(conn, KNN_SQL, [q])
            _check_plan(key, plan)
            latencies.append(ms)
            shape = plan_shape(plan)
        neighbours = [{str(r[0]) for r in conn.execute(KNN_SQL, [q]).fetchall()} for q in queries]

        entry: dict[str, Any] = {"label": label, "latency_ms": summarize(latencies), "plan": shape}
        if key == "seq":
            exact = neighbours
        else:
            recalls = [len(got & truth) / K for got, truth in zip(neighbours, exact)]
            entry["recall_at_10"] = summarize(recalls) | {"min": min(recalls)}
        results[key] = entry
        print(f"  {label}: p50 {entry['latency_ms']['p50']:.2f} ms", flush=True)
    _apply(conn, DEFAULT_SETTINGS)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--maintenance-work-mem", help="e.g. 256MB, for the index build")
    args = parser.parse_args()
    with pg_connect() as conn:
        print(build_hnsw_index(conn, args.maintenance_work_mem))
        run_vector(conn, query_vectors(args.queries))


if __name__ == "__main__":
    main()
