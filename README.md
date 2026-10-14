# Brew

Brew recommends hackathon and side-project ideas grounded in real-world "problem signals": open GitHub issues, arXiv abstracts, and Hacker News posts. It embeds these signals, matches them against a user's skills, team size, and time budget, and ranks ideas that are actually feasible rather than generic. It also recommends teammates whose skills complement the user's own.

## Features

- **Grounded idea suggestions:** every suggestion traces back to a real ingested signal from GitHub, arXiv, or Hacker News.
- **Semantic matching:** signals and user profiles are embedded and compared with cosine similarity.
- **Feasibility scoring:** candidates are ranked by a Postgres stored procedure that accounts for team size and time budget.
- **Teammate recommendations:** a graph database finds users with complementary skills and shared interests.
- **Trending problem areas:** a materialized view surfaces the topics with the most recent activity.
- **Curator tools:** curators can enable or disable sources, tune source configuration, and retire low-quality signals.
- **Scheduled ingestion:** GitHub Actions cron jobs fetch and embed new signals automatically.

## Tech stack

| Layer | Technology |
|---|---|
| Web app | Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui |
| Ingestion service | Python 3.11, FastAPI, psycopg 3, fastembed |
| Relational data and embeddings | PostgreSQL (Supabase) with pgvector |
| Teammate graph | Neo4j AuraDB |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions) |
| Scheduling | GitHub Actions |

## Architecture

Brew uses three database paradigms: relational (PostgreSQL), vector (pgvector), and graph (Neo4j). A Next.js app reads from all three, and a separate Python service handles ingestion and embedding as scheduled batch jobs.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the end-to-end data flow, service boundaries, and failure isolation. The HTTP API is documented in [docs/API.md](docs/API.md).

## Local setup

_Coming soon._

## Authors

- **Author Name**: [@github-handle](https://github.com/github-handle)
- **Author Name**: [@github-handle](https://github.com/github-handle)
