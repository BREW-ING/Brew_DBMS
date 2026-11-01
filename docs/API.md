# Brew — API Reference

All routes below live under `apps/web/app/api/`. All routes except `auth` require a signed-in session (Auth.js / NextAuth v5). Curator-only routes are marked.

## Auth

### `GET|POST /api/auth/[...nextauth]`
Handled entirely by Auth.js (`apps/web/lib/auth.ts`) with the Credentials provider: email + password checked against `users.password_hash` (bcrypt). Sessions are JWTs signed with `AUTH_SECRET`; the token carries only the user's `id` and `role` (plus name and email). `password_hash` is never selected into the session or sent to the client.

Sign-up and sign-in are server actions behind the `/register` and `/login` pages, not separate API routes. New accounts always get `role = 'user'`.

`apps/web/proxy.ts` (Next 16's replacement for `middleware.ts`) gates every route except `/login`, `/register`, and `/api/auth/*`:
- No session: pages redirect to `/login?callbackUrl=…`; API routes return `401`.
- `/review`, `/sources` (the `(curator)` pages) and `/api/curator/*` need `role = 'curator'`: pages redirect to `/`; API routes return `403`.

### Promoting a user to curator
There is no UI for this. Run in the Supabase SQL editor (emails are stored lowercase):

```sql
UPDATE users
SET role = 'curator'
WHERE email = lower('someone@example.com')
RETURNING id, email, role;
```

The role is copied into the JWT at sign-in, so the user must sign out and back in before curator routes open. Demoting (`SET role = 'user'`) likewise only takes effect on their next sign-in.

---

## Suggestions

### `GET /api/suggestions`
Returns ranked project-idea suggestions for the signed-in user, and records them in `suggestions` so they can be rated.

**Query params**
| Param | Type | Description |
|---|---|---|
| `limit` | integer (optional, default 10, max 50) | Max suggestions to return. Anything else → `400` |

**Response (`200`)**
```json
{
  "status": "ok",
  "suggestions": [
    {
      "id": "uuid (suggestions.id — pass this to /api/feedback)",
      "signalId": "uuid",
      "title": "string",
      "source": "github | arxiv | hn",
      "url": "string",
      "publishedAt": "2026-10-30T12:00:00.000Z",
      "ageDays": 3,
      "topicTags": ["climate"],
      "requiredSkills": [
        { "name": "python", "userHas": true },
        { "name": "geospatial", "userHas": false }
      ],
      "similarity": 0.62,
      "feasibility": 0.71,
      "score": 0.656
    }
  ]
}
```
- `publishedAt` is `COALESCE(published_at, fetched_at)`; `ageDays` is whole days since then.
- `requiredSkills` lists skills the user has first, then by tagger confidence.
- `score = 0.6 * similarity + 0.4 * feasibility`; results are sorted by it, highest first.

**Profile not ready (`200`):** if `users.profile_embedding` is NULL (no skills/interests saved yet, or the ingestion service hasn't embedded them):
```json
{ "status": "profile_incomplete", "message": "Add skills and interests to your profile to get suggestions.", "suggestions": [] }
```

**Headers:** `Server-Timing: db-profile;dur=…, db-suggestions;dur=…;desc="vector search + feasibility + upsert"` (milliseconds). Visible in the browser devtools Network → Timing tab.

**Errors:** `401` without a session, `400` for a bad `limit`, `500` if a query fails (the server log says which step: loading the profile embedding or ranking).

**Internal flow** (`apps/web/lib/suggestions.ts`):
1. Load `users.profile_embedding`. If NULL, return `profile_incomplete`.
2. Run **one** SQL statement (inside a transaction that does `SET LOCAL hnsw.ef_search = 100`):
   - `nearest`: `ORDER BY embedding <=> $profile LIMIT 50` over `problem_signals`, which uses the HNSW index `idx_problem_signals_embedding`. Filters: `NOT is_stale` (180-day window, see [DATABASE.md](DATABASE.md#5-functions)), `url IS NOT NULL` (seed rows are excluded), and `NOT EXISTS` a feedback row from this user with `rating <= 2` on a suggestion for that signal.
   - `scored`: join `score_candidates(user_id, ARRAY(nearest ids))` for feasibility. All 50 are scored in one call. Compute the final score and keep the top `limit`.
   - `upserted`: `INSERT INTO suggestions … ON CONFLICT (user_id, signal_id) DO UPDATE` the scores, `RETURNING id`.
   - Final select joins the signal and aggregates required skills (`signal_skills` × `user_skills`) as JSON.
3. `ef_search` is raised because HNSW returns at most `ef_search` rows (default 40) and the filters run after the index scan. If many nearby signals are stale or disliked, fewer than 50 candidates can come back. On pgvector 0.8+, `SET LOCAL hnsw.iterative_scan = relaxed_order` would remove that limit.

The dashboard (`app/(dashboard)/page.tsx`) calls the same library function directly instead of fetching this route. The detail page `/suggestions/[id]` reads one of the user's own `suggestions` rows (stored scores, the signal's `raw_text`, and the user's existing rating). Another user's suggestion id returns 404.

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
Records or updates the user's rating of one of their suggestions.

**Body**
```json
{
  "suggestionId": "uuid (suggestions.id from GET /api/suggestions)",
  "rating": 4,
  "comment": "optional string, max 2000 chars"
}
```

**Response:** the stored row, with `201 Created` on the first rating and `200 OK` when an existing rating is updated:
```json
{ "id": "uuid", "suggestionId": "uuid", "rating": 4, "comment": null, "createdAt": "2026-11-02T10:00:00.000Z" }
```
`user_id` comes from the session, never from the body.

**Upsert:** one row per `(user_id, suggestion_id)` (`UNIQUE`). Rating again overwrites `rating`. If `comment` is omitted, any earlier comment is kept. Ratings of 1-2 drop that signal from future `GET /api/suggestions` results.

**Errors**
- `400 Bad Request`: body isn't JSON, `suggestionId` isn't a UUID, or `rating` isn't an integer 1-5.
- `404 Not Found`: the suggestion doesn't exist or wasn't made to this user. The insert selects from `suggestions WHERE id = … AND user_id = <session user>`, so it finds nothing. The composite foreign key `feedback (suggestion_id, user_id) → suggestions (id, user_id)` also enforces this in the database.

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
