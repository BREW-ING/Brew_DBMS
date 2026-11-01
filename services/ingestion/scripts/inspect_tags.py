"""Print random embedded signals with their skill tags, to eyeball tagging quality.

Run from services/ingestion:
  python -m scripts.inspect_tags                 # 20 random real (non-seed) signals
  python -m scripts.inspect_tags -n 40 --source arxiv
  python -m scripts.inspect_tags --include-seed
"""

import argparse
import sys

from dotenv import load_dotenv
from psycopg.rows import dict_row

from common.db import get_connection


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("-n", type=int, default=20, help="how many to print (default 20)")
    parser.add_argument("--source", choices=["github", "arxiv", "hn"], help="only this source")
    parser.add_argument("--include-seed", action="store_true", help="include seed rows (url IS NULL)")
    args = parser.parse_args()

    load_dotenv()
    # Titles carry emoji; don't crash on consoles or pipes that can't print them.
    sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]

    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE embedded) AS embedded,
                   count(*) FILTER (WHERE embedded AND NOT EXISTS (
                       SELECT 1 FROM signal_skills ss WHERE ss.signal_id = ps.id)) AS untagged,
                   count(*) AS total
            FROM problem_signals ps
            WHERE (%(source)s::text IS NULL OR source = %(source)s)
              AND (%(seed)s OR url IS NOT NULL)
            """,
            {"source": args.source, "seed": args.include_seed},
        )
        counts = cur.fetchone()
        assert counts is not None
        print(
            f"{counts['embedded']}/{counts['total']} embedded,"
            f" {counts['untagged']} embedded with no skill tags\n"
        )
        cur.execute(
            """
            SELECT ps.source, ps.title, ps.url,
                   coalesce(
                       (SELECT array_agg(s.name || ' ' || to_char(ss.confidence, 'FM0.00')
                                         ORDER BY ss.confidence DESC, s.name)
                        FROM signal_skills ss JOIN skills s ON s.id = ss.skill_id
                        WHERE ss.signal_id = ps.id),
                       '{}') AS tags
            FROM problem_signals ps
            WHERE ps.embedded
              AND (%(source)s::text IS NULL OR ps.source = %(source)s)
              AND (%(seed)s OR ps.url IS NOT NULL)
            ORDER BY random()
            LIMIT %(n)s
            """,
            {"source": args.source, "seed": args.include_seed, "n": args.n},
        )
        rows = cur.fetchall()

    for i, row in enumerate(rows, 1):
        tags = ", ".join(row["tags"]) or "-"
        print(f"{i:>2}. [{row['source']}] {row['title']}\n    {row['url'] or '(seed)'}\n    skills: {tags}\n")


if __name__ == "__main__":
    main()
