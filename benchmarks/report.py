"""Render benchmarks/results/latest.json into docs/BENCHMARKS.md.

run_all calls this at the end; run it alone to re-render without re-measuring:
    python -m benchmarks.report

Every number in the analysis is computed from the results file, so the page
stays accurate after a re-run. Hand edits to docs/BENCHMARKS.md are overwritten.
"""

from typing import Any

from benchmarks.common import REPORT_PATH, load_results

VECTOR_CONFIGS = ("seq", "hnsw_40", "hnsw_100")


def _ms(x: float) -> str:
    return f"{x:,.1f}" if x >= 100 else f"{x:.2f}"


def _mb(n_bytes: float) -> str:
    return f"{n_bytes / 1024 ** 2:,.1f} MB"


def _ratio(a: float, b: float) -> str:
    return f"{a / b:,.1f}×" if b > 0 else "n/a"


def _faster(a_name: str, a_ms: float, b_name: str, b_ms: float) -> str:
    """'A is k× faster than B', whichever way round the numbers fall."""
    if a_ms <= b_ms:
        return f"{a_name} is {_ratio(b_ms, a_ms)} faster than {b_name}"
    return f"{b_name} is {_ratio(a_ms, b_ms)} faster than {a_name}"


def _sizes(section: dict[str, Any]) -> list[str]:
    return sorted(section, key=int)


def _environment(results: dict[str, Any]) -> list[str]:
    env = results.get("environment", {})
    cfg = results.get("config", {})
    rows = [
        ("PostgreSQL", env.get("server_version", "?")),
        ("pgvector", env.get("pgvector", "?")),
        ("shared_buffers / work_mem", f"{env.get('shared_buffers', '?')} / {env.get('work_mem', '?')}"),
        ("max_parallel_workers_per_gather", env.get("max_parallel_workers_per_gather", "?")),
        ("Neo4j", env.get("neo4j", "not measured")),
        ("Seed", cfg.get("seed", "?")),
        ("Last run (UTC)", results.get("updated_at", "?")),
    ]
    lines = ["| Setting | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    return lines


def _vector(vector: dict[str, Any]) -> list[str]:
    lines = [
        "## 1. Vector search: top-10 cosine",
        "",
        "`SELECT id FROM bench.problem_signals ORDER BY embedding <=> $q LIMIT 10` over N random",
        "unit vectors (384 dims). Latency is EXPLAIN ANALYZE execution time over the same 100 random",
        "query vectors at every N, after 5 warm-up queries. The sequential scan runs with",
        "`enable_indexscan = off` and is the exact answer that recall@10 is measured against.",
        "",
        "| N | Method | p50 (ms) | p95 (ms) | Mean recall@10 | Min recall@10 | Plan |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    skipped = []
    for n in _sizes(vector):
        entry = vector[n]
        if "skipped" in entry:
            skipped.append(f"- N = {int(n):,} was skipped: {entry['skipped']}")
            continue
        for key in VECTOR_CONFIGS:
            c = entry["configs"][key]
            recall = c.get("recall_at_10")
            mean_r = f"{recall['mean']:.3f}" if recall else "1 (exact)"
            min_r = f"{recall['min']:.1f}" if recall else "—"
            lines.append(
                f"| {int(n):,} | {c['label']} | {_ms(c['latency_ms']['p50'])} | {_ms(c['latency_ms']['p95'])}"
                f" | {mean_r} | {min_r} | `{c['plan']}` |"
            )
    lines += ["", "Index build (`m = 16, ef_construction = 64`, as in production):", ""]
    lines += ["| N | Rows load | Table size | HNSW index size | Index build |", "|---:|---:|---:|---:|---:|"]
    for n in _sizes(vector):
        entry = vector[n]
        if "skipped" in entry:
            continue
        idx = entry["index"]
        lines.append(
            f"| {int(n):,} | {entry['load_s']:.1f} s | {_mb(idx['table_bytes'])}"
            f" | {_mb(idx['index_bytes'])} | {idx['build_s']:.1f} s |"
        )
    if skipped:
        lines += [""] + skipped
    return lines + [""]


def _feasibility(f: dict[str, Any]) -> list[str]:
    lines = [
        f"## 2. Feasibility scoring: {f['candidates']} candidates",
        "",
        f"{f['trials']} trials, each a random user and {f['candidates']} random signals out of",
        f"{f['signals']:,} ({f['users']:,} users). All three variants returned identical scores in every trial.",
        "",
        "| Variant | Round trips | Server p50 (ms) | Server p95 (ms) | Wall p50 (ms) | Wall p95 (ms) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "loop_client": "`compute_feasibility_score` in an application loop",
        "loop_server": "`compute_feasibility_score` per row, one query",
        "set_based": "`score_candidates` (set-based)",
    }
    for key, label in labels.items():
        v = f[key]
        server = v.get("server_ms")
        s50, s95 = (_ms(server["p50"]), _ms(server["p95"])) if server else ("—", "—")
        lines.append(
            f"| {label} | {v['round_trips']} | {s50} | {s95} | {_ms(v['wall_ms']['p50'])} | {_ms(v['wall_ms']['p95'])} |"
        )
    lines += ["", f"Round trip (`SELECT 1`) from the benchmark machine: p50 {_ms(f['rtt_ms']['p50'])} ms.", ""]
    return lines


def _teammates(t: dict[str, Any]) -> list[str]:
    lines = [
        "## 3. Teammate recommendations: 2-hop Cypher vs SQL",
        "",
        "`db/neo4j/queries/teammates.cypher` (labels renamed to the Bench* namespace) against an",
        "equivalent SQL query on the same synthetic users, skills, interests and collaborations. Neo4j",
        "server time is `result_available_after + result_consumed_after` (whole ms); Postgres server time",
        "is EXPLAIN ANALYZE execution time. *Agreement* counts users whose top-10 (ids, scores, and",
        "explanation lists) were identical in both engines.",
        "",
        "| Users | Collaborations | Engine | Server p50 (ms) | Server p95 (ms) | Wall p50 (ms) | Wall p95 (ms) | Agreement |",
        "|---:|---:|---|---:|---:|---:|---:|---:|",
    ]
    for n in _sizes(t):
        e = t[n]
        for key, label in (("neo4j", "Neo4j (Cypher)"), ("postgres", "Postgres (SQL)")):
            v = e[key]
            lines.append(
                f"| {e['users']:,} | {e['collaborations']:,} | {label} | {_ms(v['server_ms']['p50'])}"
                f" | {_ms(v['server_ms']['p95'])} | {_ms(v['wall_ms']['p50'])} | {_ms(v['wall_ms']['p95'])}"
                f" | {e['agreement']} |"
            )
    return lines + [""]


def _analysis(results: dict[str, Any]) -> list[str]:
    out = ["## Analysis", ""]
    vector = {n: e for n, e in results.get("vector", {}).items() if "configs" in e}
    if vector:
        sizes = _sizes(vector)
        top = vector[sizes[-1]]["configs"]
        seq, h40, h100 = (top[k] for k in VECTOR_CONFIGS)
        out.append(
            f"- **HNSW vs exact search.** At N = {int(sizes[-1]):,}, HNSW with ef_search = 40 answers in"
            f" {_ms(h40['latency_ms']['p50'])} ms p50 against {_ms(seq['latency_ms']['p50'])} ms for the"
            f" sequential scan ({_faster('HNSW', h40['latency_ms']['p50'], 'the scan', seq['latency_ms']['p50'])}), at a mean"
            f" recall@10 of {h40['recall_at_10']['mean']:.3f}. ef_search = 100 costs"
            f" {_ratio(h100['latency_ms']['p50'], h40['latency_ms']['p50'])} the ef_search = 40 latency and"
            f" raises recall to {h100['recall_at_10']['mean']:.3f}."
        )
        if len(sizes) > 1:
            lo = vector[sizes[0]]["configs"]
            out.append(
                f"- **Scaling.** From {int(sizes[0]):,} to {int(sizes[-1]):,} rows"
                f" ({_ratio(int(sizes[-1]), int(sizes[0]))} the data), sequential-scan p50 grew"
                f" {_ratio(seq['latency_ms']['p50'], lo['seq']['latency_ms']['p50'])} and HNSW (ef_search = 40)"
                f" p50 grew {_ratio(h40['latency_ms']['p50'], lo['hnsw_40']['latency_ms']['p50'])}, while its"
                f" recall went from {lo['hnsw_40']['recall_at_10']['mean']:.3f} to"
                f" {h40['recall_at_10']['mean']:.3f}. A scan's cost is linear in N; an HNSW search visits a"
                " number of nodes that grows roughly logarithmically."
            )
        out.append(
            "- **Recall here is a pessimistic bound.** Uniform random vectors in 384 dimensions have no"
            " cluster structure: every point is almost equally far from every other, which is the hardest"
            " case for a proximity graph. Real all-MiniLM-L6-v2 embeddings cluster by topic, so recall at"
            " the same ef_search should be higher on production data. The suggestions API already runs"
            " with ef_search = 100 because it needs 50 candidates that survive post-scan filters."
        )
    f = results.get("feasibility")
    if f:
        loop_srv, set_srv = f["loop_server"]["server_ms"]["p50"], f["set_based"]["server_ms"]["p50"]
        loop_wall, set_wall = f["loop_client"]["wall_ms"]["p50"], f["set_based"]["wall_ms"]["p50"]
        line = (
            f"- **Feasibility, server side.** One `score_candidates` call scores {f['candidates']} candidates in"
            f" {_ms(set_srv)} ms p50; calling `compute_feasibility_score` once per row inside a single query"
            f" takes {_ms(loop_srv)} ms ({_faster('set-based', set_srv, 'per-row', loop_srv)})."
        )
        if loop_srv > set_srv:
            line += (
                " Each per-row call repeats the constraints lookup and runs its own one-signal join, where"
                " the set-based call does one grouped join over all candidates."
            )
        out.append(line)
        network_ms = f["candidates"] * f["rtt_ms"]["p50"]
        line = (
            f"- **Feasibility, end to end.** The application-side loop costs {_ms(loop_wall)} ms p50 wall clock"
            f" against {_ms(set_wall)} ms for the set-based call"
            f" ({_faster('set-based', set_wall, 'the loop', loop_wall)}). With a {_ms(f['rtt_ms']['p50'])} ms"
            f" round trip, {f['candidates']} round trips alone account for about {_ms(network_ms)} ms"
        )
        line += (
            ", so the N+1 pattern's cost is mostly network, not scoring."
            if network_ms > loop_wall / 2
            else " of it."
        )
        out.append(line)
    t = results.get("teammates")
    if t:
        for n in _sizes(t):
            e = t[n]
            neo, pg = e["neo4j"]["server_ms"]["p50"], e["postgres"]["server_ms"]["p50"]
            out.append(
                f"- **Teammates at {e['users']:,} users.** Server p50: Neo4j {_ms(neo)} ms, Postgres {_ms(pg)} ms;"
                f" {_faster('Postgres', pg, 'Neo4j', neo)}. Both returned the"
                f" same recommendations for {e['agreement']} users."
            )
        out.append(
            "- **Reading the teammate numbers.** Both queries score every candidate user, so both grow"
            " with the user count; the 2-hop part only touches the user's collaborators' neighbours. The"
            " Cypher stays a direct transcription of the scoring rules, while the SQL needs a"
            " both-directions edge CTE and four grouped CTEs to express the same thing. The engines also run"
            " on different hosted hardware (Aura vs Supabase), so compare the trend across sizes more than"
            " the absolute gap."
        )
    return out + [""]


CAVEATS = [
    "## Caveats",
    "",
    "- Both databases are shared, network-attached hosted instances; expect run-to-run variance.",
    "  Server times exclude the network; wall-clock times include the round trip from the machine",
    "  that ran the benchmark.",
    "- Queries are sent with client-side parameter binding, so every execution is planned with its",
    "  actual values. The app uses server-side parameters and may switch to a generic plan.",
    "- Signals are synthetic. The vector benchmark runs the bare kNN query; the production query",
    "  also filters stale signals, seed rows and disliked suggestions after the index scan.",
    "- Neo4j reports server time in whole milliseconds, so sub-millisecond differences are lost.",
    "",
    "## Reproducing",
    "",
    "From the repository root, with `DATABASE_URL` (session pooler) and `NEO4J_*` set:",
    "",
    "```powershell",
    "pip install -r benchmarks\\requirements.txt",
    "python -m benchmarks.run_all",
    "```",
    "",
    "Everything runs in the `bench` Postgres schema and on `Bench*`-labelled Neo4j nodes, and is",
    "dropped at the end unless `--keep-data` is passed. See [benchmarks/README.md](../benchmarks/README.md).",
    "",
]


def render(results: dict[str, Any]) -> str:
    lines = [
        "# Brew — Benchmarks",
        "",
        "> Generated by `python -m benchmarks.report` from `benchmarks/results/latest.json`.",
        "> Re-run the benchmarks to refresh it; hand edits are overwritten.",
        "",
        "## Setup",
        "",
        *_environment(results),
        "",
    ]
    if results.get("vector"):
        lines += _vector(results["vector"])
    if results.get("feasibility"):
        lines += _feasibility(results["feasibility"])
    if results.get("teammates"):
        lines += _teammates(results["teammates"])
    lines += _analysis(results)
    lines += CAVEATS
    return "\n".join(lines)


def write_report(results: dict[str, Any]) -> None:
    REPORT_PATH.write_text(render(results), encoding="utf-8")


def main() -> None:
    results = load_results()
    if not results:
        raise SystemExit("No results yet: run python -m benchmarks.run_all first")
    write_report(results)
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
