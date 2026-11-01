# Benchmarks

Reproducible performance experiments for Brew's three query paths. Running them writes
the results to `docs/BENCHMARKS.md`. That file isn't in the repository yet: no results have
been published, so this folder describes the experiments, not their outcome.

| Benchmark | What it compares |
|---|---|
| `bench_vector.py` | Top-10 cosine search: sequential scan vs HNSW at `ef_search` 40 and 100, at N = 10k / 50k / 100k. p50/p95 latency and recall@10 |
| `bench_feasibility.py` | `compute_feasibility_score` per row (in an app loop, and per row in one query) vs set-based `score_candidates`, for 50 candidates |
| `bench_teammates.py` | The 2-hop teammate query in Cypher vs an equivalent SQL query, on the same synthetic graph, with results cross-checked |

## Isolation: never touches real data

- **Postgres:** everything lives in the `bench` schema ([sql/bench_schema.sql](sql/bench_schema.sql)),
  and every statement names its tables as `bench.<table>`. `bench.score_candidates` and
  `bench.compute_feasibility_score` are copies of the real functions pointed at the bench
  tables. Keep them in sync with `db/postgres/schema.sql`.
- **Neo4j:** Aura has a single database, so benchmark data uses its own labels and
  relationship types (`BenchUser`, `BenchSkill`, `BenchInterest`, `BENCH_HAS_SKILL`, ...). The
  benchmarked Cypher is `db/neo4j/queries/teammates.cypher` with those names substituted at
  run time. The real queries never match benchmark nodes.
- At the end of `run_all` both are removed (`DROP SCHEMA bench CASCADE`, delete `Bench*` nodes)
  unless you pass `--keep-data`. `python -m benchmarks.cleanup` does the same on demand.

## Running

From the repository root, in a venv (the ingestion one works):

```powershell
pip install -r benchmarks\requirements.txt
python -m benchmarks.run_all
```

Credentials come from `benchmarks/.env` if it exists, otherwise `DATABASE_URL` from
`services/ingestion/.env` and `NEO4J_*` from `apps/web/.env.local`. `DATABASE_URL` must be the
Supabase **session** pooler (port 5432), because the benchmarks rely on session settings.

Useful flags:

```powershell
python -m benchmarks.run_all --sizes 10000,50000          # smaller vector sizes
python -m benchmarks.run_all --only teammates             # one section; others keep last results
python -m benchmarks.run_all --maintenance-work-mem 256MB # faster HNSW build, if your plan has RAM
python -m benchmarks.run_all --db-budget-mb 8000          # Pro plan: allow more disk
python -m benchmarks.report                               # re-render docs/BENCHMARKS.md only
```

Each step is also runnable alone, e.g.
`python -m benchmarks.scripts.generate_synthetic_signals --n 10000` then
`python -m benchmarks.bench_vector`. Run `python -m benchmarks.cleanup` when you're done.

## Disk and time

N = 100k needs about 400 MB in Postgres (≈160 MB of vectors plus a similar-sized HNSW index).
Only one N is stored at a time, so the peak is the largest N. Supabase's free tier caps the
database at 500 MB and switches the project to read-only past it, so `run_all` skips any N that
would push the database over `--db-budget-mb` (default 500) and records why. Expect the whole
run to take tens of minutes, mostly HNSW builds and the per-row feasibility loop's round trips.

## Reproducibility

- Embeddings are generated in Postgres after `setseed()`, so the same Postgres version yields
  the same vectors. The 100 query vectors, users, skills and collaborations come from Python's
  `random.Random(42)`.
- Raw numbers are kept in `results/latest.json`. The report, including its analysis sentences,
  is rendered from that file.
