"""Feasibility scoring for 50 candidates: per-row calls vs one set-based call.

Three ways to score the same 50 (user, signal) pairs:
  loop_client  50 round trips, one compute_feasibility_score() call each
               (an application-side N+1 loop); wall clock only
  loop_server  one query calling compute_feasibility_score() once per row
  set_based    one score_candidates() call for all 50, as the suggestions API does
Server time is EXPLAIN ANALYZE's Execution Time; wall clock includes the round
trip(s) from this machine. All three must return identical scores.

Expects bench users (scripts.generate_synthetic_users) and signals
(scripts.generate_synthetic_signals). Run from the repo root:
    python -m benchmarks.bench_feasibility
"""

import argparse
import random
from typing import Any
from uuid import UUID

import psycopg

from benchmarks.common import SEED, explain, pg_connect, summarize, timed
from benchmarks.scripts.generate_synthetic_signals import signal_id

CANDIDATES = 50
WARMUP_TRIALS = 3
RTT_SAMPLES = 50

LOOP_CLIENT_SQL = "SELECT bench.compute_feasibility_score(%s::uuid, %s::uuid)"
LOOP_SERVER_SQL = (
    "SELECT s.id, bench.compute_feasibility_score(%s::uuid, s.id)"
    " FROM unnest(%s::uuid[]) AS s(id)"
)
SET_BASED_SQL = "SELECT signal_id, score FROM bench.score_candidates(%s::uuid, %s::uuid[])"


def _scores_match(a: dict[UUID, float], b: dict[UUID, float]) -> bool:
    return a.keys() == b.keys() and all(abs(a[k] - b[k]) < 1e-6 for k in a)


def _trial(conn: psycopg.Connection, user: UUID, ids: list[UUID]) -> dict[str, float]:
    def loop_client() -> dict[UUID, float]:
        out = {}
        for sid in ids:
            row = conn.execute(LOOP_CLIENT_SQL, [user, sid]).fetchone()
            assert row is not None
            out[sid] = row[0]
        return out

    looped, loop_client_wall = timed(loop_client)
    per_row, loop_server_wall = timed(lambda: dict(conn.execute(LOOP_SERVER_SQL, [user, ids]).fetchall()))
    set_based, set_based_wall = timed(lambda: dict(conn.execute(SET_BASED_SQL, [user, ids]).fetchall()))
    if len(set_based) != len(ids) or not (_scores_match(set_based, looped) and _scores_match(set_based, per_row)):
        raise RuntimeError(f"feasibility variants disagree for user {user}")

    loop_server_ms, _ = explain(conn, LOOP_SERVER_SQL, [user, ids])
    set_based_ms, _ = explain(conn, SET_BASED_SQL, [user, ids])
    return {
        "loop_client_wall": loop_client_wall,
        "loop_server_wall": loop_server_wall,
        "set_based_wall": set_based_wall,
        "loop_server_ms": loop_server_ms,
        "set_based_ms": set_based_ms,
    }


def run_feasibility(conn: psycopg.Connection, n_signals: int, trials: int, seed: int = SEED) -> dict[str, Any]:
    """Score `trials` random (user, 50 signals) draws with each variant."""
    rng = random.Random(seed + 2)
    users = [r[0] for r in conn.execute("SELECT id FROM bench.users ORDER BY name").fetchall()]
    if not users:
        raise RuntimeError("bench.users is empty; run scripts.generate_synthetic_users first")

    rtt = [timed(lambda: conn.execute("SELECT 1").fetchone())[1] for _ in range(RTT_SAMPLES)]
    samples: dict[str, list[float]] = {}
    for i in range(WARMUP_TRIALS + trials):
        user = rng.choice(users)
        ids = [signal_id(g) for g in rng.sample(range(1, n_signals + 1), CANDIDATES)]
        trial = _trial(conn, user, ids)
        if i >= WARMUP_TRIALS:
            for k, v in trial.items():
                samples.setdefault(k, []).append(v)

    return {
        "candidates": CANDIDATES,
        "trials": trials,
        "signals": n_signals,
        "users": len(users),
        "rtt_ms": summarize(rtt),
        "loop_client": {"round_trips": CANDIDATES, "wall_ms": summarize(samples["loop_client_wall"])},
        "loop_server": {
            "round_trips": 1,
            "server_ms": summarize(samples["loop_server_ms"]),
            "wall_ms": summarize(samples["loop_server_wall"]),
        },
        "set_based": {
            "round_trips": 1,
            "server_ms": summarize(samples["set_based_ms"]),
            "wall_ms": summarize(samples["set_based_wall"]),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trials", type=int, default=50)
    args = parser.parse_args()
    with pg_connect() as conn:
        row = conn.execute("SELECT count(*) FROM bench.problem_signals").fetchone()
        assert row is not None
        result = run_feasibility(conn, row[0], args.trials)
    for key in ("loop_client", "loop_server", "set_based"):
        print(key, result[key])


if __name__ == "__main__":
    main()
