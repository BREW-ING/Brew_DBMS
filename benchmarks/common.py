"""Shared helpers for the benchmarks: connections, EXPLAIN parsing, stats, results.

Every benchmark works only on the `bench` Postgres schema and on Bench*-labelled
Neo4j nodes; see benchmarks/sql/bench_schema.sql and benchmarks/bench_teammates.py.
"""

import json
import math
import os
import time
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

import psycopg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = REPO_ROOT / "benchmarks"
SCHEMA_SQL = BENCH_DIR / "sql" / "bench_schema.sql"
RESULTS_PATH = BENCH_DIR / "results" / "latest.json"
REPORT_PATH = REPO_ROOT / "docs" / "BENCHMARKS.md"

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2, same as problem_signals.embedding
SEED = 42

# Same reference data as db/postgres/schema.sql section 9 (ids are 1-based
# positions in these tuples).
SKILLS = (
    "javascript", "typescript", "python", "react", "nextjs",
    "machine-learning", "computer-vision", "nlp", "postgresql",
    "neo4j", "vector-search", "ui-design", "mobile", "devops",
    "rust", "go", "data-engineering", "geospatial", "iot", "llm",
)
INTERESTS = (
    "climate", "healthtech", "accessibility", "fintech-alt",
    "education", "security", "conservation", "civic-tech",
    "developer-tools", "research-tools",
)

T = TypeVar("T")


def load_env() -> None:
    """Load env files; earlier files win (python-dotenv never overrides a set var).

    benchmarks/.env is optional; otherwise DATABASE_URL comes from the
    ingestion service's .env and NEO4J_* from the web app's .env.local.
    """
    for path in (
        BENCH_DIR / ".env",
        REPO_ROOT / "services" / "ingestion" / ".env",
        REPO_ROOT / "apps" / "web" / ".env.local",
    ):
        if path.exists():
            load_dotenv(path)


def pg_connect() -> psycopg.Connection:
    """Autocommit connection with client-side parameter binding.

    ClientCursor inlines parameters as literals, so EXPLAIN ANALYZE works with
    them and every query is planned with its actual values.
    """
    load_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (benchmarks/.env or services/ingestion/.env)")
    if ":6543" in url:
        # The transaction pooler drops session settings (SET hnsw.ef_search,
        # enable_indexscan) between statements.
        raise RuntimeError("DATABASE_URL points at the transaction pooler (:6543); use the session pooler (:5432)")
    conn = psycopg.connect(url, autocommit=True, cursor_factory=psycopg.ClientCursor)
    conn.execute("SET statement_timeout = 0")
    return conn


def ensure_schema(conn: psycopg.Connection) -> None:
    """Create the bench schema and its reference rows (idempotent)."""
    conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO bench.skills (id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            list(enumerate(SKILLS, start=1)),
        )
        cur.executemany(
            "INSERT INTO bench.interests (id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            list(enumerate(INTERESTS, start=1)),
        )


def explain(
    conn: psycopg.Connection, query: str, params: Sequence[Any] | dict[str, Any] | None = None
) -> tuple[float, dict[str, Any]]:
    """Run the query under EXPLAIN ANALYZE; return (server execution ms, plan).

    TIMING OFF skips per-node clock reads, which would otherwise inflate the
    total; the overall Execution Time is still measured.
    """
    row = conn.execute("EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON) " + query, params).fetchone()
    assert row is not None
    doc = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    return float(doc[0]["Execution Time"]), doc[0]["Plan"]


def plan_nodes(plan: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield plan
    for child in plan.get("Plans", []):
        yield from plan_nodes(child)


def plan_shape(plan: dict[str, Any]) -> str:
    """Top-down chain of node types, e.g. 'Limit > Index Scan (idx_x)'."""
    parts = []
    for node in plan_nodes(plan):
        label = node["Node Type"]
        if "Index Name" in node:
            label += f" ({node['Index Name']})"
        parts.append(label)
    return " > ".join(parts)


def timed(fn: Callable[[], T]) -> tuple[T, float]:
    """Call fn; return (its result, wall-clock ms)."""
    start = time.perf_counter()
    result = fn()
    return result, (time.perf_counter() - start) * 1000


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile (numpy's default method), p in [0, 100]."""
    if not values:
        raise ValueError("percentile of empty sequence")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * p / 100
    lo, hi = math.floor(rank), math.ceil(rank)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def summarize(values: Sequence[float]) -> dict[str, float]:
    return {
        "n": len(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "mean": sum(values) / len(values),
    }


def pg_environment(conn: psycopg.Connection) -> dict[str, str]:
    row = conn.execute(
        """
        SELECT current_setting('server_version'),
               (SELECT extversion FROM pg_extension WHERE extname = 'vector'),
               current_setting('shared_buffers'),
               current_setting('work_mem'),
               current_setting('max_parallel_workers_per_gather')
        """
    ).fetchone()
    assert row is not None
    keys = ("server_version", "pgvector", "shared_buffers", "work_mem", "max_parallel_workers_per_gather")
    return {k: str(v) for k, v in zip(keys, row)}


def load_results() -> dict[str, Any]:
    if RESULTS_PATH.exists():
        return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    return {}


def save_results(results: dict[str, Any]) -> None:
    """Write results/latest.json. Called after every section so a crash keeps what ran."""
    results["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
