# Brew — project context for Claude

Brew recommends hackathon/side-project ideas grounded in real "problem signals"
(GitHub issues, arXiv abstracts, Hacker News posts), matched to a user's skills,
team size, and time budget. It also recommends teammates via a graph database.

## Stack
- apps/web: Next.js (App Router) + TypeScript (strict) + Tailwind + shadcn/ui
- services/ingestion: Python 3.11, FastAPI, psycopg 3, fastembed
- Postgres (Supabase) with pgvector — relational data + embeddings
- Neo4j AuraDB — teammate graph
- GitHub Actions cron for scheduled ingestion

## Rules
- Never hardcode secrets. Read from env vars. Never print secrets in logs.
- Schema changes after the initial schema go in db/migrations/ as
  YYYYMMDDHHMM_description.sql. Never edit an already-applied migration.
- Python: type hints on all functions; each adapter must fail independently.
- TypeScript: strict mode, avoid `any`.
- Keep changes scoped to the current task. Don't refactor unrelated files.
- After making changes, tell me exactly how to run/verify them.
- Embedding model: sentence-transformers/all-MiniLM-L6-v2 (384 dims) everywhere.

## How I work
- I'm on Windows PowerShell. Give PowerShell commands.
- Python jobs and scripts run as `python -m <module>` from services/ingestion
  (e.g. `python -m jobs.fetch_signals`), never `python jobs/fetch_signals.py`.
  The venv is activated with `.venv\Scripts\Activate.ps1`.
- Read the existing code first and follow its patterns. Don't rewrite working
  files unless something is actually broken.
- Don't commit, push, or create branches. I commit myself after checking.
- Don't install databases or other heavy tools locally. Postgres is Supabase and
  Neo4j is Aura; if you need to see real output, give me a query to run there.
- problem_signals.embedded is a GENERATED column (embedding IS NOT NULL):
  only ever write `embedding`, never `embedded`.
- Rows in problem_signals with url IS NULL are seed data, not real signals.

## Layout
See docs/ARCHITECTURE.md. Do not restructure top-level folders.