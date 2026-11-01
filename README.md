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

## Deployment

Brew runs on four hosted services, plus GitHub Actions for the scheduled jobs:

| Piece | Host | Source |
|---|---|---|
| Postgres + pgvector | Supabase | `db/postgres/`, `db/migrations/` |
| Teammate graph | Neo4j AuraDB | `db/neo4j/` |
| Ingestion HTTP API (FastAPI) | Render | `services/ingestion/main.py`, `render.yaml` |
| Web app (Next.js) | Vercel | `apps/web/` |
| Ingest, embed, graph sync (cron) | GitHub Actions | `.github/workflows/ingest.yml`, `embed.yml` |

Set them up in this order, because each step produces a value the next one needs.

### 1. Supabase

1. Create a project. Under **Connect > Session pooler**, copy the connection string. This is `DATABASE_URL` everywhere below. Don't use the direct `db.<ref>.supabase.co` form: it only resolves over IPv6, so GitHub Actions runners can't reach it.
2. In the SQL Editor, run `db/postgres/schema.sql`. It enables `pgvector` itself. Then run every file in `db/migrations/` in filename order.
3. Optional: run `db/postgres/seed.sql` to load demo data.

### 2. Neo4j AuraDB

1. Create a free instance and save the credentials file it offers. It holds the URI (`neo4j+s://<id>.databases.neo4j.io`), the username (usually `neo4j`) and the password.
2. In the Aura query console, run `db/neo4j/constraints_and_seed.cypher`.

### 3. Render (ingestion API)

1. Pick one `SERVICE_KEY` value and use it everywhere below. Generate it with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. In Render, choose **New > Blueprint** and select this repo. Render reads `render.yaml` and asks for the two secrets.
3. Once deployed, check `https://<service>.onrender.com/health`. That URL, without `/health`, is `INGESTION_URL`.

The Blueprint sets `autoDeploy: false`, so redeploy from the Render dashboard after you push. The build downloads the embedding model so cold starts don't have to. The free plan spins down when idle, so the first request after a pause is slow.

### 4. Vercel (web app)

1. Import the repo and set **Root Directory** to `apps/web`. The framework preset is Next.js.
2. Add the environment variables from the table below, then deploy. The production URL, for example `https://brew.vercel.app`, is `APP_URL`.

### 5. GitHub Actions secrets

Under **Settings > Secrets and variables > Actions**, add the secrets from the table below. Then run **Ingest Signals** and **Embed Signals** once from the Actions tab rather than waiting for the cron.

GitHub doesn't allow secret names that start with `GITHUB_`. The GitHub token is therefore stored as `GH_TOKEN`, and `ingest.yml` passes it to the job as `GITHUB_TOKEN`, the name `fetch_signals` reads. The token is a personal access token with no scopes. It is optional, but without it GitHub limits requests to 60 an hour.

### Where each variable goes

| Variable | Vercel | Render | GitHub secret | Value |
|---|:-:|:-:|:-:|---|
| `DATABASE_URL` | ✓ | ✓ | ✓ | Supabase session pooler string |
| `SERVICE_KEY` | ✓ | ✓ | ✓ | The shared key from step 3 |
| `AUTH_SECRET` | ✓ | | | `npx auth secret` |
| `AUTH_URL` | optional | | | Only needed if not on a Vercel domain (custom domain or self-hosted) |
| `NEO4J_URI` | ✓ | | | From the Aura credentials file |
| `NEO4J_USER` | ✓ | | | From the Aura credentials file |
| `NEO4J_PASSWORD` | ✓ | | | From the Aura credentials file |
| `INGESTION_URL` | ✓ | | | Render service URL |
| `APP_URL` | | | ✓ | Vercel production URL |
| `GH_TOKEN` | | | ✓ | GitHub token (no scopes) |

`render.yaml` sets `PYTHON_VERSION` and `FASTEMBED_CACHE_PATH` itself. CI (`ci.yml`) uses no secrets: lint, typecheck, `next build` and `pytest` all run without them.

### Scheduled jobs

- **Ingest Signals** (every 6 hours): `python -m jobs.fetch_signals`. Afterwards it calls `POST $APP_URL/api/internal/graph-sync` with `X-Service-Key`, which drains `graph_sync_queue` into Neo4j. The sync runs even if a source failed, and either failure turns the run red.
- **Embed Signals** (30 minutes later): `python -m jobs.embed_signals`. The pip cache and the fastembed model are cached between runs.

## Authors

- **Pranav Kalla**: [@PRANAVKALLA230106](https://github.com/PRANAVKALLA230106)
- **Pavitra Jain**: [@pavitragit09](https://github.com/pavitragit09)
