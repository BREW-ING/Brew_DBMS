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

**Internal flow:**
1. Embed the user's current skill profile, or reuse `users.profile_embedding`.
2. Run a cosine-similarity query against `problem_signals.embedding` for the top-N non-stale candidates.
3. Score the whole shortlist in one call: `SELECT * FROM score_candidates($userId, $signalIds::uuid[])`.
4. Sort by a weighted combination of similarity and feasibility.
5. Upsert into `suggestions`. `UNIQUE (user_id, signal_id)` means re-scoring updates the existing row rather than adding a duplicate.

`compute_feasibility_score(user_id, signal_id)` still exists as a single-signal wrapper for ad-hoc queries; don't call it in a loop. See [DATABASE.md](DATABASE.md#5-functions) for the scoring formula.

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
      "score": 7.5,
      "complementary_skills": ["string"],
      "shared_interests": ["string"],
      "mutual_collaborators": ["string"],
      "past_collaborator": false
    }
  ]
}
```

The skill, interest, and collaborator lists explain *why* someone was recommended, so the UI can show reasons rather than only a number.

**Internal flow:** runs `db/neo4j/queries/teammates.cypher` with `$userId` bound to the session user and `$limit` (default 10). Candidates must have at least one skill the user lacks. Shared interests and direct or 2-hop collaborations raise the score but are not required.

Collaboration history comes from the Postgres `collaborations` table, mirrored into Neo4j through `graph_sync_queue`. Recent profile changes can take until the next sync run to show up.

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

**Response:** `201 Created`, echoes the stored row. `user_id` comes from the session, never from the body.

**Errors**
- `404 Not Found`: the suggestion doesn't exist or wasn't made to this user. This is enforced by the composite foreign key `feedback (suggestion_id, user_id) → suggestions (id, user_id)`.
- `409 Conflict`: the user already rated this suggestion (`UNIQUE (user_id, suggestion_id)`).

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
