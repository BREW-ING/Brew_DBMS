# Brew — Git & GitHub Workflow

How we set up the repository, structure commits and branches, and run CI.

## 1. One-time setup

```bash
cd brew
git init
git add .
git commit -m "chore: initial scaffolding (phase 0)"

# Create the repo on GitHub first (via github.com or `gh repo create`), then:
git remote add origin https://github.com/<your-username>/brew.git
git branch -M main
git push -u origin main
```

If you have the GitHub CLI installed, you can create + push in one step instead:
```bash
gh repo create brew --public --source=. --remote=origin --push
```

## 2. Commit cadence

Commit **after each build phase completes and runs**, not after every single file.

| Phase | Example commit message |
|---|---|
| 0 | `chore(phase-0): scaffold folder structure` |
| 1 | `feat(phase-1): postgres schema + neo4j constraints` |
| 2 | `feat(phase-2): github + arxiv ingestion adapters` |
| 3 | `feat(phase-3): frontend skeleton with notion design system` |
| 4 | `feat(phase-4): wire suggestions and teammates APIs to live data` |
| 5 | `feat(phase-5): triggers, stored procedure, materialized view` |
| 6 | `ci(phase-6): scheduled ingestion + deployment` |

Use `type(scope): description` ([Conventional Commits](https://www.conventionalcommits.org/)) throughout.

## 3. Branching

- `main` — always deployable
- One short-lived branch per feature/phase: `feat/ingestion-adapters`, `feat/teammate-matching`, etc.
- Merge into `main` through a pull request, even when there is no second reviewer, so every change has a reviewable record.

## 4. Automated workflows

1. **Scheduled ingestion and embedding** (`.github/workflows/ingest.yml`, `embed.yml`) run on a cron schedule and can be triggered manually from the Actions tab.
2. **CI** (below) runs lint and build checks on every push and pull request to `main`.

### `.github/workflows/ci.yml`
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm ci
      - run: npm run lint
      - run: npm run build

  ingestion:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: services/ingestion
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python -m compileall .
```

## 5. Secrets on GitHub (for the scheduled workflows)

Do **not** commit `.env` or `.env.local`. Instead, add each key listed in `services/ingestion/.env.example` and `apps/web/.env.local.example` under:

**Repo → Settings → Secrets and variables → Actions → New repository secret**

Then reference them in `ingest.yml`/`embed.yml` as `${{ secrets.GITHUB_TOKEN }}`, `${{ secrets.DATABASE_URL }}`, etc. — never as literal values in the YAML.

## 6. README checklist (what should be visible on the repo landing page)

- One-line description + the tagline
- Architecture diagram (copy from `ARCHITECTURE.md`, Section 3)
- Tech stack table
- Setup instructions (link to `.env.example` files)
- A short GIF or screenshot of the dashboard once Phase 3 is done
- Link to `docs/ARCHITECTURE.md` and `docs/API.md` for anyone who wants depth without cluttering the README itself
