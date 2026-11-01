"""Fill bench.problem_signals with N synthetic signals.

Each signal gets a random unit-length 384-dim embedding (each component drawn
from N(0, 1) via Box-Muller, then L2-normalized, i.e. uniform on the sphere)
and 0-4 required skills in bench.signal_skills.

Vectors are generated inside Postgres, so a 100k-row load doesn't have to
upload ~400 MB of vector text. setseed() makes the run reproducible for a given
Postgres version. Signal ids are md5('bench-signal-<g>')::uuid for g = 1..N,
so other benchmarks can rebuild any id without querying (see signal_id()).

Replaces whatever bench.problem_signals held before. Run from the repo root:
    python -m benchmarks.scripts.generate_synthetic_signals --n 10000
"""

import argparse
import hashlib
import time
from uuid import UUID

import psycopg

from benchmarks.common import EMBEDDING_DIM, SEED, ensure_schema, pg_connect

CHUNK_ROWS = 5000

# The window sum normalizes each signal's 384 components; the ln(1 - u) form
# avoids ln(0) because random() is in [0, 1).
_INSERT_CHUNK = f"""
INSERT INTO bench.problem_signals (id, title, embedding)
SELECT md5('bench-signal-' || g)::uuid,
       'Synthetic signal ' || g,
       array_agg(x / norm ORDER BY d)::real[]::vector({EMBEDDING_DIM})
FROM (
    SELECT g, d, x, sqrt(sum(x * x) OVER (PARTITION BY g)) AS norm
    FROM (
        SELECT g, d, sqrt(-2.0 * ln(1.0 - random())) * cos(2.0 * pi() * random()) AS x
        FROM generate_series(%(lo)s::int, %(hi)s::int) AS g
        CROSS JOIN generate_series(1, {EMBEDDING_DIM}) AS d
    ) gaussian
) normalized
GROUP BY g
"""

# Each (signal, skill) pair with probability 0.15: on average 3 of the 20
# skills, and ~4% of signals get none (score_candidates' neutral 0.5 case).
_INSERT_SIGNAL_SKILLS = """
INSERT INTO bench.signal_skills (signal_id, skill_id, confidence)
SELECT ps.id, s.id, (0.5 + 0.5 * random())::real
FROM bench.problem_signals ps
JOIN bench.skills s ON random() < 0.15
"""


def signal_id(g: int) -> UUID:
    """Id of the g-th synthetic signal; matches md5('bench-signal-' || g)::uuid."""
    return UUID(hashlib.md5(f"bench-signal-{g}".encode()).hexdigest())


def generate_signals(conn: psycopg.Connection, n: int, seed: int = SEED) -> dict[str, float]:
    """Replace bench.problem_signals with n synthetic rows; return load stats."""
    ensure_schema(conn)
    started = time.perf_counter()
    conn.execute("DROP INDEX IF EXISTS bench.idx_bench_signals_embedding")
    conn.execute("TRUNCATE bench.problem_signals CASCADE")
    # setseed() takes a double in [-1, 1].
    conn.execute("SELECT setseed(%s)", [(seed % 1000) / 1000])
    for lo in range(1, n + 1, CHUNK_ROWS):
        hi = min(lo + CHUNK_ROWS - 1, n)
        conn.execute(_INSERT_CHUNK, {"lo": lo, "hi": hi})
        print(f"  signals {hi:,}/{n:,}", flush=True)
    conn.execute(_INSERT_SIGNAL_SKILLS)
    conn.execute("VACUUM ANALYZE bench.problem_signals")
    conn.execute("VACUUM ANALYZE bench.signal_skills")

    row = conn.execute(
        "SELECT count(*), min(vector_norm(embedding)), max(vector_norm(embedding))"
        " FROM bench.problem_signals"
    ).fetchone()
    assert row is not None
    count, min_norm, max_norm = row
    if count != n or abs(min_norm - 1) > 1e-3 or abs(max_norm - 1) > 1e-3:
        raise RuntimeError(f"bad synthetic data: {count} rows, norms {min_norm}..{max_norm}")
    return {"rows": n, "load_s": time.perf_counter() - started}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, required=True, help="number of signals, e.g. 10000")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    with pg_connect() as conn:
        stats = generate_signals(conn, args.n, args.seed)
    print(f"Loaded {stats['rows']:,} signals in {stats['load_s']:.1f}s")


if __name__ == "__main__":
    main()
