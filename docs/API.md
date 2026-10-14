# Brew — API Reference

All routes below live under `apps/web/app/api/`. All routes except `auth` require a signed-in session (NextAuth). Curator-only routes are marked.

## Auth

### `POST /api/auth/[...nextauth]`
Handled entirely by NextAuth.js. Roles: `user` (default), `curator`.

---

## Suggestions

### `GET /api/suggestions`
Returns ranked project-idea suggestions for the signed-in user.

**Query params**
| Param | Type | Description |
|---|---|---|
| `limit` | number (optional, default 10) | Max suggestions to return |

**Response**
```json
{
  "suggestions": [
    {
      "id": "uuid",
      "signal": {
        "title": "string",
        "source": "github | arxiv | hn",
        "url": "string",
        "category_tags": ["string"]
      },
      "similarity_score": 0.83,
      "feasibility_score": 0.71
    }
  ]
}
```

**Internal flow:** embeds the user's current skill profile → cosine-similarity query against `problem_signals.embedding` (top-N candidates) → calls Postgres function `compute_feasibility_score(user_id, signal_id)` per candidate → sorts by a weighted combination of both scores.

---

## Teammates

### `GET /api/teammates`
Returns recommended teammates for the signed-in user from the Neo4j graph.

**Response**
```json
{
  "teammates": [
    {
      "id": "string",
      "name": "string",
      "shared_interest_count": 2,
      "complementary_skill_count": 3
    }
  ]
}
```

**Internal flow:** runs the representative Cypher query (see `db/neo4j/constraints_and_seed.cypher`, Section 5) with `$userId` bound to the session user.

**Failure mode:** if Neo4j is unreachable, return `{ "teammates": [], "status": "unavailable" }` with HTTP 200 — do not surface a 500 to the dashboard for a non-critical feature.

---

## Feedback

### `POST /api/feedback`
Records a user's rating on a suggestion.

**Body**
```json
{
  "suggestion_id": "uuid",
  "rating": 4,
  "comment": "optional string"
}
```

**Response:** `201 Created`, echoes the stored row.

---

## Curator-only routes

### `GET /api/curator/sources`
Lists all rows in `ingestion_sources`. Requires `role = curator`.

### `PATCH /api/curator/sources/:id`
Updates `is_active` or `config` for a source. Requires `role = curator`.

**Body**
```json
{
  "is_active": true,
  "config": { "categories": ["cs.LG", "cs.HC"] }
}
```

### `PATCH /api/curator/signals/:id`
Manually marks a `problem_signals` row as stale (removing it from suggestion candidates without deleting it). Requires `role = curator`.

**Body**
```json
{ "is_stale": true }
```

---

## Conventions for every route

- Auth failures → `401`. Wrong role on a curator route → `403`, not a silent empty response.
- Validate all request bodies (e.g. with `zod`) before touching the database — reject with `400` and a clear message on bad input.
- Every route that touches more than one database (e.g. `/api/suggestions` touches both Postgres and the vector index) should log which step failed if an error occurs, to make debugging during development easier.
