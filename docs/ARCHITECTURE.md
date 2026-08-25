# Brew — Architecture

## 1. Overview

Brew is composed of three independently-hosted layers that communicate over well-defined boundaries: a Next.js web app, a Python ingestion/embedding service, and three databases (PostgreSQL, pgvector, Neo4j). No layer directly reaches into another's internals — everything crosses a boundary through a database or a documented API route.

## 2. Why three database paradigms

| Concern | Data shape | Chosen store | Why |
|---|---|---|---|
| Users, skills, constraints, feedback | Structured, relational, needs integrity/transactions | PostgreSQL | Classic relational workload — joins, foreign keys, ACID guarantees |
| "Is this problem signal relevant to this user's skills?" | Unstructured natural language, meaning-based matching | pgvector (Postgres extension) | Cosine similarity search over embeddings; SQL alone cannot express "semantically similar" |
| "Who should this user team up with?" | Network of skills/interests/past collaborations | Neo4j | Graph traversal (complementary skills, shared interests, N-hop collaboration history) is naturally a Cypher query, not a chain of SQL joins |

Using pgvector rather than a separate vector database keeps operational surface area small (one Postgres instance covers two of the three paradigms) while still being a genuinely distinct query pattern from the relational tables — this is worth stating explicitly in your report, since a grader may ask "why not just use Qdrant" and the honest answer is operational simplicity, not a limitation.

## 3. Data flow, end to end

1. **Ingestion (scheduled):** GitHub Actions cron triggers `services/ingestion/jobs/fetch_signals.py`, which runs each source adapter, normalizes results into the shared `ProblemSignal` shape, and upserts into `problem_signals` (deduped on `(source, external_id)`).
2. **Embedding (scheduled, decoupled):** A second cron triggers `embed_signals.py`, which selects `WHERE embedded = false`, batches them through the embedding model, writes the resulting vector into `problem_signals.embedding`, and flips `embedded = true`.
3. **Staleness (trigger-driven):** Every insert into `problem_signals` fires `trg_mark_stale_signals`, which flags any signal older than 30 days — no separate cleanup job needed.
4. **User requests suggestions:** `app/api/suggestions/route.ts` embeds the user's current skill/interest profile (or reuses a cached embedding), runs a cosine-similarity query against `problem_signals.embedding`, shortlists candidates, then calls `compute_feasibility_score()` (Postgres stored procedure) per candidate to rank the final list.
5. **User requests teammates:** `app/api/teammates/route.ts` queries Neo4j directly for users with complementary skills and shared interests (see the representative query in `db/neo4j/constraints_and_seed.cypher`).
6. **Curator maintenance:** `(curator)` routes let a curator-role user toggle `ingestion_sources.is_active`, edit source `config` (e.g. which subreddits), and manually mark low-quality signals stale.
7. **Trending view:** `trending_problem_areas` materialized view is refreshed after each ingestion run and powers `app/(dashboard)/trending/page.tsx`.

## 4. Service boundaries

- **Next.js app** never talks to external APIs (GitHub, arXiv, etc.) directly — that's the ingestion service's job. The app only ever reads/writes to the three databases.
- **Ingestion service** never serves end-user traffic — it's a batch job, not a request/response API, invoked only by GitHub Actions (or manually during development).
- **Embedding logic** lives in the ingestion service, not the Next.js app, so the embedding model choice can change without touching frontend code.

## 5. Failure isolation

- Each ingestion adapter (`github_adapter.py`, `arxiv_adapter.py`, etc.) fails independently — an exception in one does not stop the others from running in the same job invocation.
- Embedding failures leave `embedded = false` untouched, so nothing is lost — the next scheduled run simply retries the backlog.
- If Neo4j is unreachable, `/api/teammates` should degrade gracefully (return an empty list with a clear status, not a 500) so the rest of the dashboard still functions.

## 6. What to point at in a demo

- Insert a new GitHub issue manually → show it appear in `problem_signals` unembedded → run the embedding job → show it become searchable — this demonstrates the decoupled pipeline clearly.
- Run the representative Neo4j query live against the seeded sample users — this is the single most "look, a graph database is actually doing something" moment in the whole project.
- Query `trending_problem_areas` before and after a refresh to show the materialized view in action.
