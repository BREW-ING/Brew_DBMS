# What's new in Brew

Most project-idea tools fall into one of two groups. Some are lists people put together by hand, like old hackathon winners or "100 project ideas" posts. Others are chatbots that make up ideas when you ask. Both have the same weakness: the idea isn't connected to anyone who actually has the problem, and nothing checks whether *you* can build it in the time you have.

Brew starts from the other end. It collects problems that real people have written down, then works out which of those problems a particular person or team can realistically take on.

## 1. Every suggestion points back to a real problem

Brew doesn't make up ideas. Each suggestion is a row in `problem_signals`, collected from one of three public sources:

- **GitHub issues**: open feature requests and "help wanted" issues with enough reactions to show that several people want them
- **arXiv papers**: applied research (education, accessibility, healthcare, civic tech) whose abstracts describe a gap that hasn't been solved yet
- **Hacker News**: "Ask HN" posts where people say things like "is there a tool for…" or "how do you deal with…"

Each signal keeps its source URL, so a user can open the original post and see who asked for it.

We also found that collecting the data was easy and filtering it was the hard part. A first sample of GitHub issues was mostly internal tickets and one-line requests, so we added filters that drop ticket-style titles, very short bodies, bot accounts and chore titles. arXiv was full of pure method papers at first, so we limited it to applied categories and required both a real-world group (students, patients, developers and so on) and a problem phrase in the abstract. Hacker News gave us only about 2 usable posts a month at a 10-point minimum. Lowering it to 5 points gave about 11 a month, and the extra posts were still mostly good. All of these rules live in plain lists in the code, so they're easy to tune.

## 2. Feasibility is scored inside the database

A problem can be interesting and still be wrong for you. Brew scores each candidate problem against the user's profile using a Postgres function, `score_candidates(user_id, signal_ids[])`:

- **skill coverage**: how many of the skills the problem needs the user has, weighted by how good they are at each (proficiency 1–5)
- **team size**: a bigger team can cover more of the required skills
- **time budget**: tight deadlines (under 24 hours) lower the score

The function scores all candidates in a single set-based query instead of being called once per problem. The scoring logic therefore sits next to the data, can be tested with plain SQL, and is the same for every caller.

## 3. Three ways of querying, each used where it fits

| Question | Query style | Where it runs |
|---|---|---|
| Who is this user, what can they do, what did they rate? | Relational: joins, constraints, transactions | PostgreSQL |
| Which problems are *about* the same thing as this user's profile? | Vector similarity on 384-dimensional embeddings | pgvector (HNSW index) in the same Postgres |
| Who would make a good teammate for this user? | Graph traversal | Neo4j |

We kept vector search inside Postgres on purpose. One database handles both structured data and semantic search, so there's less to run and nothing extra to keep in sync. Neo4j is used for the one part that really is a network problem.

## 4. Teammates who fill your gaps

Most "find a teammate" features match people who are *similar*. For a small project that's often the wrong choice, because two backend developers end up with no frontend. Brew's teammate query looks for people who have the skills you **don't**, then ranks them higher if:

- you share an interest (both of you care about education, climate, and so on)
- you've worked together before
- you're **two steps apart**: you've both worked with the same person, but not with each other

The two-step case is short to write in Cypher and awkward to write as SQL joins, which is why this part lives in a graph database.

## 5. Keeping two databases consistent

Postgres is the source of truth, and Neo4j is a copy built for reading. Whenever a user, skill, interest or collaboration changes, triggers write a small event to an outbox table (`graph_sync_queue`). The sync worker doesn't replay each event as it was recorded. It reads the user's *current* state from Postgres and rewrites that part of the graph. Duplicate or out-of-order events therefore can't push the graph out of line, and running the sync twice does no harm.

A few smaller design choices back this up:

- `problem_signals.embedded` is a **generated column** (`embedding IS NOT NULL`), so it can never disagree with the data it describes
- each collaboration is stored **once**, with `user_a < user_b`, so the same pair can't appear twice in different orders
- **stale signals** (older than 180 days) are marked by triggers and a partial index, not by a separate cleanup job
- the trending view is a **materialized view** with a unique index, so it can be refreshed while people are reading it

## How Brew compares

| | Curated idea lists | Chatbot idea generators | Team-finder forums | **Brew** |
|---|---|---|---|---|
| Ideas come from real, linked problems | sometimes | no | n/a | **yes** |
| Considers the user's skills and time | no | only if you describe them every time | no | **yes, from a stored profile** |
| Gets new problems automatically | no | n/a | n/a | **yes, scheduled collection** |
| Suggests teammates who fill skill gaps | no | no | manual search | **yes, graph-based** |

## Current status

**Done**
- the database design: 13 tables, feasibility scoring, staleness triggers, the trending view and the sync outbox
- collection from GitHub and arXiv, with quality filters and tests
- the Neo4j teammate graph and query
- demo reports for both databases

**Next**
- Hacker News collection
- embeddings and automatic skill tagging for semantic search
- the web app (profile, suggestions feed, teammates, trending, curator tools)
