"""Fetch problem signals from every active source and upsert them.

Run from services/ingestion:  python -m jobs.fetch_signals

Each source runs independently: a failure in one is logged and reported in the
summary The process exits 1 if any source failed,
so the scheduled workflow shows up red.
"""

import logging
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from adapters.arxiv_adapter import ArxivAdapter
from adapters.base import BaseAdapter
from adapters.github_adapter import GithubAdapter
from common.db import get_connection, upsert_signals

log = logging.getLogger("fetch_signals")

# source_type -> factory taking ingestion_sources.config. Add HN here.
ADAPTERS: dict[str, Callable[[Mapping[str, Any]], BaseAdapter]] = {
    "github": lambda config: GithubAdapter(config),
    "arxiv": lambda config: ArxivAdapter(config),
}

# How far back to look when a source has never been fetched. Matches the
# staleness window: anything older would be marked stale on insert anyway.
FIRST_RUN_LOOKBACK = timedelta(days=30)


@dataclass
class SourceConfig:
    source_type: str
    row_id: int | None  # None = no ingestion_sources row; ran with defaults
    config: dict[str, Any]
    last_fetched_at: datetime | None

    @property
    def label(self) -> str:
        return self.source_type if self.row_id is None else f"{self.source_type}#{self.row_id}"


@dataclass
class SourceResult:
    label: str
    fetched: int = 0
    upserted: int = 0
    error: str | None = None


def load_sources(conn: psycopg.Connection) -> list[SourceConfig]:
    """Active ingestion_sources rows that have an adapter, plus defaults for
    adapter types with no row at all. Types whose rows are all inactive are
    skipped: a curator turned them off."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id, source_type, config, is_active, last_fetched_at"
            " FROM ingestion_sources ORDER BY id"
        )
        rows = cur.fetchall()

    sources: list[SourceConfig] = []
    for source_type in ADAPTERS:
        typed = [r for r in rows if r["source_type"] == source_type]
        if not typed:
            log.info("No ingestion_sources row for %s; using default config", source_type)
            sources.append(SourceConfig(source_type, None, {}, None))
        for r in typed:
            if r["is_active"]:
                sources.append(
                    SourceConfig(source_type, r["id"], r["config"] or {}, r["last_fetched_at"])
                )
            else:
                log.info("Skipping inactive source %s#%d", source_type, r["id"])
    return sources


def run_source(conn: psycopg.Connection, src: SourceConfig) -> SourceResult:
    result = SourceResult(src.label)
    # Taken before fetching so items updated mid-run are picked up next time.
    started = datetime.now(timezone.utc)
    since = src.last_fetched_at or started - FIRST_RUN_LOOKBACK
    try:
        adapter = ADAPTERS[src.source_type](src.config)
        signals = adapter.fetch(since)
        result.fetched = len(signals)
        # Upsert and cursor advance commit together: if the upsert fails, the
        # next run retries the same window.
        with conn.transaction():
            result.upserted = upsert_signals(signals, conn=conn)
            if src.row_id is not None:
                conn.execute(
                    "UPDATE ingestion_sources SET last_fetched_at = %s WHERE id = %s",
                    (started, src.row_id),
                )
    except Exception as exc:  # isolate sources from each other
        log.exception("Source %s failed", src.label)
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def finalize(conn: psycopg.Connection) -> int:
    """Expire aged-out signals and refresh the trending view. Returns rows expired."""
    row = conn.execute("SELECT expire_stale_signals()").fetchone()
    expired = int(row[0]) if row else 0
    conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY trending_problem_areas")
    return expired


def print_summary(results: list[SourceResult], expired: int | None) -> None:
    width = max([len("source"), *(len(r.label) for r in results)])
    print(f"{'source':<{width}}  {'fetched':>7}  {'inserted/updated':>16}  status")
    for r in results:
        status = "ok" if r.error is None else f"FAILED ({r.error})"
        print(f"{r.label:<{width}}  {r.fetched:>7}  {r.upserted:>16}  {status}")
    if expired is not None:
        print(f"expired {expired} stale signal(s); refreshed trending_problem_areas")


def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per request

    with get_connection() as conn:
        # Each source commits in its own transaction block; REFRESH runs on its own.
        conn.autocommit = True
        results = [run_source(conn, src) for src in load_sources(conn)]
        expired: int | None = None
        try:
            expired = finalize(conn)
        except Exception:
            log.exception("Post-ingestion maintenance failed")
            results.append(SourceResult("maintenance", error="see log above"))

    print_summary(results, expired)
    return 1 if any(r.error for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
