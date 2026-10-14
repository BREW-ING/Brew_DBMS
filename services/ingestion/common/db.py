"""Postgres access for the ingestion service."""

import os
from collections.abc import Sequence

import psycopg
from dotenv import load_dotenv
from psycopg import sql

from common.schema import ProblemSignal

# Rows per INSERT statement. 7 params/row keeps us far below Postgres's
# 65535 bind-parameter limit.
UPSERT_CHUNK_SIZE = 500

_COLUMNS = (
    "source",
    "external_id",
    "title",
    "raw_text",
    "url",
    "category_tags",
    "published_at",
)
_UPDATABLE = _COLUMNS[2:]  # everything except the (source, external_id) key


def get_connection() -> psycopg.Connection:
    """Open a new connection using DATABASE_URL (from the env or a .env file)."""
    load_dotenv()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(url)


def _upsert_query(n_rows: int) -> sql.Composed:
    row = sql.SQL("({})").format(sql.SQL(", ").join(sql.Placeholder() * len(_COLUMNS)))
    target = sql.Identifier("problem_signals")

    def cols(prefix: sql.Composable | None, names: Sequence[str]) -> sql.Composable:
        idents = [
            sql.Identifier(c)
            if prefix is None
            else sql.SQL("{}.{}").format(prefix, sql.Identifier(c))
            for c in names
        ]
        return sql.SQL(", ").join(idents)

    excluded = sql.SQL("EXCLUDED")
    return sql.SQL(
        """
        INSERT INTO {target} ({cols})
        VALUES {rows}
        ON CONFLICT (source, external_id) DO UPDATE SET
            {assignments},
            -- The stored vector was computed from the old text; clear it so the
            -- embed job picks the row up again.
            embedding = CASE
                WHEN ({target}.title, {target}.raw_text)
                     IS DISTINCT FROM (EXCLUDED.title, EXCLUDED.raw_text)
                THEN NULL
                ELSE {target}.embedding
            END
        -- Skip no-op updates: no dead tuples, no trigger work, and the
        -- returned count reflects rows that actually changed.
        WHERE ({old}) IS DISTINCT FROM ({new})
        """
    ).format(
        target=target,
        cols=cols(None, _COLUMNS),
        rows=sql.SQL(", ").join([row] * n_rows),
        assignments=sql.SQL(", ").join(
            sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in _UPDATABLE
        ),
        old=cols(target, _UPDATABLE),
        new=cols(excluded, _UPDATABLE),
    )


def upsert_signals(
    signals: list[ProblemSignal], conn: psycopg.Connection | None = None
) -> int:
    """Insert or update signals keyed on (source, external_id).

    Returns the number of rows inserted or changed; re-fetching an unchanged
    signal counts as 0. `fetched_at` keeps its first-fetch value and
    `is_stale` is left alone (staleness is one-way, see DATABASE.md).

    If `conn` is given the caller owns the transaction; otherwise a
    connection is opened and committed here.
    """
    # Postgres rejects an ON CONFLICT DO UPDATE that touches the same row twice
    # in one statement, so collapse duplicates within the batch (last wins).
    unique = list({(s.source, s.external_id): s for s in signals}.values())
    if not unique:
        return 0

    if conn is None:
        with get_connection() as own_conn:  # commits on clean exit
            return _upsert(own_conn, unique)
    return _upsert(conn, unique)


def _upsert(conn: psycopg.Connection, signals: list[ProblemSignal]) -> int:
    affected = 0
    with conn.cursor() as cur:
        for start in range(0, len(signals), UPSERT_CHUNK_SIZE):
            chunk = signals[start : start + UPSERT_CHUNK_SIZE]
            params = [getattr(s, c) for s in chunk for c in _COLUMNS]
            cur.execute(_upsert_query(len(chunk)), params)
            affected += cur.rowcount
    return affected
