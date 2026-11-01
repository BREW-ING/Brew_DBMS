"""Embed signals that have no vector yet and tag them with skills.

Run from services/ingestion:  python -m jobs.embed_signals

Walks `WHERE NOT embedded` oldest first in batches of BATCH_SIZE. Each batch
writes its embeddings and signal_skills rows in one transaction; a batch that
fails rolls back on its own (its rows stay unembedded for the next run) and
the job moves on. The process exits 1 if any batch failed, so the scheduled
workflow shows up red.

Seed rows (url IS NULL) are embedded but not auto-tagged: their signal_skills
rows are hand-written in seed.sql.
"""

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from common.db import get_connection
from common.embeddings import embed_texts
from common.skill_tagger import SkillTagger
from common.skills_data import SKILLS

log = logging.getLogger("embed_signals")

BATCH_SIZE = 64


@dataclass
class Summary:
    batches: int = 0
    embedded: int = 0
    tags_inserted: int = 0
    failed: list[str] = field(default_factory=list)  # one entry per failed batch


def signal_text(title: str, raw_text: str) -> str:
    return f"{title}\n\n{raw_text}" if raw_text else title


def to_vector_literal(vector: list[float]) -> str:
    """pgvector's text input format, so no pgvector adapter is needed."""
    return "[" + ",".join(f"{x:.7g}" for x in vector) + "]"


def load_skill_ids(conn: psycopg.Connection) -> dict[str, int]:
    """skills.name -> id for skills that have tagging data; warns about the rest."""
    rows = conn.execute("SELECT id, name FROM skills ORDER BY id").fetchall()
    ids = {name: skill_id for skill_id, name in rows if name in SKILLS}
    missing = sorted(name for _, name in rows if name not in SKILLS)
    if missing:
        log.warning("Skills with no entry in skills_data, never tagged: %s", ", ".join(missing))
    return ids


def next_batch(
    conn: psycopg.Connection, after: tuple[datetime, UUID] | None
) -> list[dict[str, Any]]:
    """Keyset pagination on (fetched_at, id): successful rows drop out of
    `NOT embedded` anyway, and this keeps a failed batch from being re-read."""
    keyset = "AND (fetched_at, id) > (%s, %s)" if after is not None else ""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT id, title, raw_text, url, fetched_at FROM problem_signals"
            f" WHERE NOT embedded {keyset} ORDER BY fetched_at, id LIMIT %s",
            (*(after or ()), BATCH_SIZE),
        )
        return cur.fetchall()


def process_batch(
    conn: psycopg.Connection,
    rows: list[dict[str, Any]],
    tagger: SkillTagger,
    skill_ids: dict[str, int],
) -> tuple[int, int]:
    """Returns (signals embedded, signal_skills rows inserted)."""
    texts = [signal_text(r["title"], r["raw_text"]) for r in rows]
    vectors = embed_texts(texts, batch_size=BATCH_SIZE)
    tag_rows = [
        (r["id"], skill_ids[name], confidence)
        for r, text, vec in zip(rows, texts, vectors)
        if r["url"] is not None
        for name, confidence in tagger.tag(text, vec)
    ]
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            "UPDATE problem_signals SET embedding = %s::vector WHERE id = %s",
            [(to_vector_literal(v), r["id"]) for r, v in zip(rows, vectors)],
        )
        embedded = cur.rowcount
        inserted = 0
        if tag_rows:
            cur.executemany(
                "INSERT INTO signal_skills (signal_id, skill_id, confidence)"
                " VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                tag_rows,
            )
            inserted = cur.rowcount
    return embedded, inserted


def run(conn: psycopg.Connection) -> Summary:
    summary = Summary()
    skill_ids = load_skill_ids(conn)
    tagger = SkillTagger(list(skill_ids), embed_texts)
    after: tuple[datetime, UUID] | None = None
    while rows := next_batch(conn, after):
        after = (rows[-1]["fetched_at"], rows[-1]["id"])
        summary.batches += 1
        try:
            embedded, inserted = process_batch(conn, rows, tagger, skill_ids)
            summary.embedded += embedded
            summary.tags_inserted += inserted
            log.info("Batch %d: embedded %d, tagged %d", summary.batches, embedded, inserted)
        except Exception as exc:  # isolate batches from each other
            log.exception("Batch %d failed (%d signals)", summary.batches, len(rows))
            summary.failed.append(
                f"batch {summary.batches} ({len(rows)} signals, first id {rows[0]['id']}):"
                f" {type(exc).__name__}: {exc}"
            )
    return summary


def print_summary(summary: Summary) -> None:
    print(f"batches:           {summary.batches} ({len(summary.failed)} failed)")
    print(f"signals embedded:  {summary.embedded}")
    print(f"skill tags added:  {summary.tags_inserted}")
    for line in summary.failed:
        print(f"FAILED {line}")


def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    with get_connection() as conn:
        # Each batch commits in its own transaction block.
        conn.autocommit = True
        summary = run(conn)

    print_summary(summary)
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main())
