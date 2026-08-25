# Brew — Git & GitHub Workflow

This is the checklist for actually getting the project onto GitHub and keeping it looking actively maintained — this matters for a resume/SIE project, not just for submission.

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

Commit **after each build phase completes and runs**, not after every single file — matches the phase structure in `BREW_BUILD_SPEC.md` Section 6.

| Phase | Example commit message |
|---|---|
| 0 | `chore(phase-0): scaffold folder structure` |
| 1 | `feat(phase-1): postgres schema + neo4j constraints` |
| 2 | `feat(phase-2): github + arxiv ingestion adapters` |
| 3 | `feat(phase-3): frontend skeleton with notion design system` |
| 4 | `feat(phase-4): wire suggestions and teammates APIs to live data` |
| 5 | `feat(phase-5): triggers, stored procedure, materialized view` |
| 6 | `ci(phase-6): scheduled ingestion + deployment` |

Use `type(scope): description` (Conventional Commits) throughout — it's a small thing that reads as more professional to anyone browsing the repo's history.

## 3. Branching (keep it simple for a 2-person team)

- `main` — always deployable
- One short-lived branch per feature/phase: `feat/ingestion-adapters`, `feat/teammate-matching`, etc.
- Open a PR into `main` even if you're the only reviewer — it gives you a visible PR history, which is a small but real resume signal ("used PR-based workflow").

## 4. Keeping the repo visibly "alive"

A repo that hasn't been touched in months looks abandoned to a recruiter skimming GitHub. Two low-effort ways to keep commit activity honest and ongoing rather than padded:

1. **The scheduled ingestion/embedding jobs themselves** (`.github/workflows/ingest.yml`, `embed.yml`) run automatically — they don't create commits, but a green Actions history on the repo is itself a signal of an actively-running system, which is more convincing than commit padding.
2. **A lightweight CI workflow** (below) that runs lint/build checks on every push — shows the project has real automated checks, not just code dumped into a repo.

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

Do **not** commit `.env` or `.env.local`. Instead, add each key from Section 7 of `BREW_BUILD_SPEC.md` under:

**Repo → Settings → Secrets and variables → Actions → New repository secret**

Then reference them in `ingest.yml`/`embed.yml` as `${{ secrets.GITHUB_TOKEN }}`, `${{ secrets.DATABASE_URL }}`, etc. — never as literal values in the YAML.

## 6. README checklist (what should be visible on the repo landing page)

- One-line description + the tagline
- Architecture diagram (copy from `ARCHITECTURE.md`, Section 3)
- Tech stack table
- Setup instructions (link to `.env.example` files)
- A short GIF/screenshot of the dashboard once Phase 3 is done — this alone meaningfully improves how the repo reads to a visitor
- Link to `docs/ARCHITECTURE.md` and `docs/API.md` for anyone who wants depth without cluttering the README itself
