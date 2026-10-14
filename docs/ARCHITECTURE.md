# Brew — Architecture

## 1. Overview

Brew is composed of three independently-hosted layers that communicate over well-defined boundaries: a Next.js web app, a Python ingestion/embedding service, and three databases (PostgreSQL, pgvector, Neo4j). No layer directly reaches into another's internals — everything crosses a boundary through a database or a documented API route.

## 2. Why three database paradigms

| Concern | Data shape | Chosen store | Why |
|---|---|---|---|
| Users, skills, interests, collaborations, constraints, feedback | Structured, relational, needs integrity/transactions | PostgreSQL | Classic relational workload — joins, foreign keys, ACID guarantees. Postgres is the source of truth for everything Neo4j mirrors |
| "Is this problem signal relevant to this user's skills?" | Unstructured natural language, meaning-based matching | pgvector (Postgres extension) | Cosine similarity search over embeddings; SQL alone cannot express "semantically similar" |
| "Who should this user team up with?" | Network of skills/interests/past collaborations | Neo4j (read-optimized mirror, synced from Postgres) | Graph traversal (complementary skills, shared interests, N-hop collaboration history) is naturally a Cypher query, not a chain of SQL joins |

Using pgvector rather than a separate vector database keeps operational surface area small (one Postgres instance covers two of the three paradigms) while still being a genuinely distinct query pattern from the relational tables. Choosing pgvector over a dedicated vector store such as Qdrant is a decision driven by operational simplicity, not by a limitation of either option.

## 3. Data flow, end to end

1. **Ingestion (scheduled):** GitHub Actions cron triggers `services/ingestion/jobs/fetch_signals.py`, which runs each source adapter, normalizes results into the shared `ProblemSignal` shape, and upserts into `problem_signals` (deduped on `(source, external_id)`).
2. **Embedding (scheduled, decoupled):** A second cron triggers `embed_signals.py`, which selects `WHERE NOT embedded` (oldest first), batches them through the embedding model, and writes the resulting vector into `problem_signals.embedding`. `embedded` is a generated column (`embedding IS NOT NULL`), so it flips automatically.
3. **Staleness (trigger-driven + scheduled):** A signal is stale once `COALESCE(published_at, fetched_at)` is more than 30 days old.
   - `trg_set_signal_staleness` marks an incoming row stale before it is written if it is already old.
   - `trg_sweep_stale_signals` runs after each insert statement and calls `expire_stale_signals()` to catch existing rows that have aged out.
   - A scheduled job can also call `SELECT expire_stale_signals();` to cover quiet periods with no inserts.
4. **User requests suggestions:** `app/api/suggestions/route.ts` embeds the user's current skill/interest profile (or reuses `users.profile_embedding`) and runs a cosine-similarity query against `problem_signals.embedding` to shortlist candidates. It then ranks the whole shortlist in a single call to `score_candidates(user_id, signal_ids[])`, which scores skill coverage (via `signal_skills`), team size, and time budget in one set-based query.
5. **User requests teammates:** `app/api/teammates/route.ts` runs `db/neo4j/queries/teammates.cypher` against Neo4j. The query scores complementary skills, shared interests, and direct and 2-hop collaboration history.
6. **Graph sync (outbox):** Changes to `users`, `user_skills`, `user_interests`, and `collaborations` fire triggers that write to `graph_sync_queue` in the same transaction. A sync worker drains the queue, re-reads each affected user's current state from Postgres, and updates Neo4j to match. See [DATABASE.md](DATABASE.md#7-graph-sync-outbox).
7. **Curator maintenance:** `(curator)` routes let a curator-role user toggle `ingestion_sources.is_active`, edit source `config` (e.g. which repositories or arXiv categories to watch), and manually mark low-quality signals stale.
8. **Trending view:** `trending_problem_areas` materialized view is refreshed (`REFRESH MATERIALIZED VIEW CONCURRENTLY`, so readers are never blocked) after each ingestion run and powers `app/(dashboard)/trending/page.tsx`.

## 4. Service boundaries

- **Next.js app** never talks to external APIs (GitHub, arXiv, etc.) directly — that's the ingestion service's job. The app only ever reads/writes to the three databases.
- **Ingestion service** never serves end-user traffic — it's a batch job, not a request/response API, invoked only by GitHub Actions (or manually during development).
- **Embedding logic** lives in the ingestion service, not the Next.js app, so the embedding model choice can change without touching frontend code.

## 5. Failure isolation

- Each ingestion adapter (`github_adapter.py`, `arxiv_adapter.py`, etc.) fails independently — an exception in one does not stop the others from running in the same job invocation.
- Embedding failures leave `embedding` NULL (and therefore `embedded = false`), so nothing is lost — the next scheduled run simply retries the backlog.
- If the graph sync worker is down, Neo4j falls behind but nothing is lost: events wait in `graph_sync_queue` until the worker catches up.
- If Neo4j is unreachable, `/api/teammates` should degrade gracefully (return an empty list with a clear status, not a 500) so the rest of the dashboard still functions.

## 6. Demo walkthrough

1. **Ingestion and embedding pipeline:** Insert a new GitHub issue into `problem_signals`. It appears with `embedded = false`. Run the embedding job, after which the signal has a vector and is returned by similarity search.
2. **Teammate matching:** Run `db/neo4j/queries/teammates.cypher` against the seeded sample users. For example, Hana is recommended to Aisha through their mutual collaborator Sofia, a 2-hop match found by graph traversal.
3. **Trending view:** Query `trending_problem_areas`, ingest new signals, refresh the materialized view, and query it again to see the updated aggregates.
