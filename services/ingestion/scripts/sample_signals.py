"""Print a random sample of signals to eyeball ingestion quality.

Run from services/ingestion:
  python -m scripts.sample_signals              # 15 random github rows from the DB
  python -m scripts.sample_signals -n 30 --source hn
  python -m scripts.sample_signals --live       # fetch from GitHub now, write nothing
"""

import argparse
import logging
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv
from psycopg.rows import dict_row

from adapters.github_adapter import GithubAdapter
from common.db import get_connection


def sample_db(n: int, source: str) -> list[dict[str, Any]]:
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT count(*) AS total, count(*) FILTER (WHERE is_stale) AS stale"
            " FROM problem_signals WHERE source = %s",
            (source,),
        )
        counts = cur.fetchone()
        assert counts is not None
        print(f"{source}: {counts['total']} rows, {counts['stale']} stale\n")
        cur.execute(
            "SELECT title, url, category_tags, is_stale FROM problem_signals"
            " WHERE source = %s ORDER BY random() LIMIT %s",
            (source, n),
        )
        return cur.fetchall()


def sample_live(n: int, days: int) -> list[dict[str, Any]]:
    """Run the GitHub adapter with the config stored in ingestion_sources."""
    config: dict[str, Any] = {}
    with get_connection() as conn:
        row = conn.execute(
            "SELECT config FROM ingestion_sources"
            " WHERE source_type = 'github' AND is_active ORDER BY id LIMIT 1"
        ).fetchone()
        if row is not None:
            config = row[0] or {}
    print(f"config: {config or '(defaults)'}")
    signals = GithubAdapter(config).fetch(datetime.now(timezone.utc) - timedelta(days=days))
    print(f"fetched {len(signals)} signals from the last {days} days\n")
    picked = random.sample(signals, min(n, len(signals)))
    return [
        {"title": s.title, "url": s.url, "category_tags": s.category_tags, "is_stale": None}
        for s in picked
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("-n", type=int, default=15, help="how many to print (default 15)")
    parser.add_argument("--source", default="github", choices=["github", "arxiv", "hn"])
    parser.add_argument("--live", action="store_true", help="sample a fresh GitHub fetch instead of the DB")
    parser.add_argument("--days", type=int, default=30, help="--live lookback window (default 30)")
    args = parser.parse_args()

    load_dotenv()
    # Titles carry emoji; don't crash on consoles or pipes that can't print them.
    sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.live and args.source != "github":
        parser.error("--live only supports --source github")
    rows = sample_live(args.n, args.days) if args.live else sample_db(args.n, args.source)

    for i, row in enumerate(rows, 1):
        stale = " [stale]" if row["is_stale"] else ""
        tags = ", ".join(row["category_tags"]) or "-"
        print(f"{i:>2}. {row['title']}{stale}\n    {row['url']}\n    tags: {tags}\n")


if __name__ == "__main__":
    main()
