import "server-only";

import neo4j, { type ManagedTransaction } from "neo4j-driver";
import type { PoolClient } from "pg";

import { getPool } from "@/lib/db";
import { getDriver } from "@/lib/neo4j";

// Drains graph_sync_queue into Neo4j (docs/DATABASE.md section 7). Each user's
// part of the graph is rewritten from their *current* Postgres state, so events
// can be replayed, duplicated or collapsed without the graph drifting.

type UserState = {
  id: string;
  name: string;
  skills: { name: string; proficiency: number }[];
  interests: string[];
  // Canonical pair order (userA < userB), as stored in collaborations.
  collaborations: { userA: string; userB: string; otherName: string; projectName: string }[];
};

export type GraphSyncResult = {
  processedEvents: number;
  syncedUsers: number;
  /** Users whose sync failed; their events stay pending for the next run. */
  failedUsers: string[];
};

export type GraphSyncOptions = {
  batchSize?: number;
  maxBatches?: number;
  /** Only process events for these users (used right after a profile save). */
  userIds?: string[];
};

/** Null if the user no longer exists. */
async function readUserState(client: PoolClient, userId: string): Promise<UserState | null> {
  const user = await client.query<{ name: string }>("SELECT name FROM users WHERE id = $1", [userId]);
  const row = user.rows[0];
  if (!row) return null;

  const skills = await client.query<{ name: string; proficiency: number }>(
    `SELECT s.name, us.proficiency
     FROM user_skills us JOIN skills s ON s.id = us.skill_id
     WHERE us.user_id = $1`,
    [userId],
  );
  const interests = await client.query<{ name: string }>(
    `SELECT i.name
     FROM user_interests ui JOIN interests i ON i.id = ui.interest_id
     WHERE ui.user_id = $1`,
    [userId],
  );
  const collaborations = await client.query<{
    user_a: string;
    user_b: string;
    other_name: string;
    project_name: string;
  }>(
    `SELECT c.user_a, c.user_b, o.name AS other_name, c.project_name
     FROM collaborations c
     JOIN users o ON o.id = CASE WHEN c.user_a = $1 THEN c.user_b ELSE c.user_a END
     WHERE c.user_a = $1 OR c.user_b = $1`,
    [userId],
  );

  return {
    id: userId,
    name: row.name,
    skills: skills.rows,
    interests: interests.rows.map((i) => i.name),
    collaborations: collaborations.rows.map((c) => ({
      userA: c.user_a,
      userB: c.user_b,
      otherName: c.other_name,
      projectName: c.project_name,
    })),
  };
}

// Separate statements rather than one query: an UNWIND over an empty list
// yields no rows and would silently skip whatever follows it.
async function writeUserState(tx: ManagedTransaction, state: UserState): Promise<void> {
  const { id } = state;
  await tx.run("MERGE (u:User {id: $id}) SET u.name = $name", { id, name: state.name });
  await tx.run("MATCH (:User {id: $id})-[r:HAS_SKILL|INTERESTED_IN]->() DELETE r", { id });
  await tx.run("MATCH (:User {id: $id})-[r:COLLABORATED_WITH]-() DELETE r", { id });

  await tx.run(
    `MATCH (u:User {id: $id})
     UNWIND $skills AS skill
     MERGE (s:Skill {name: skill.name})
     CREATE (u)-[:HAS_SKILL {proficiency: skill.proficiency}]->(s)`,
    { id, skills: state.skills.map((s) => ({ name: s.name, proficiency: neo4j.int(s.proficiency) })) },
  );
  await tx.run(
    `MATCH (u:User {id: $id})
     UNWIND $interests AS name
     MERGE (i:Interest {name: name})
     CREATE (u)-[:INTERESTED_IN]->(i)`,
    { id, interests: state.interests },
  );
  // The collaborator may not be in the graph yet; its own queued event fills in
  // the rest. One edge per pair, directed userA -> userB.
  await tx.run(
    `UNWIND $collaborations AS c
     WITH c, CASE WHEN c.userA = $id THEN c.userB ELSE c.userA END AS otherId
     MERGE (o:User {id: otherId}) ON CREATE SET o.name = c.otherName
     WITH c
     MATCH (a:User {id: c.userA}), (b:User {id: c.userB})
     CREATE (a)-[:COLLABORATED_WITH {project_name: c.projectName}]->(b)`,
    { id, collaborations: state.collaborations },
  );
}

async function writeUser(userId: string, state: UserState | null): Promise<void> {
  const session = getDriver().session({ defaultAccessMode: neo4j.session.WRITE });
  try {
    await session.executeWrite(async (tx) => {
      if (state) await writeUserState(tx, state);
      else await tx.run("MATCH (u:User {id: $id}) DETACH DELETE u", { id: userId });
    });
  } finally {
    await session.close();
  }
}

/**
 * Processes pending graph_sync_queue events in batches. Throws if Neo4j is
 * unreachable; nothing is marked processed for the batch in flight.
 */
export async function processGraphSyncQueue(options: GraphSyncOptions = {}): Promise<GraphSyncResult> {
  const { batchSize = 100, maxBatches = 10, userIds } = options;
  const result: GraphSyncResult = { processedEvents: 0, syncedUsers: 0, failedUsers: [] };

  for (let batch = 0; batch < maxBatches; batch++) {
    const client = await getPool().connect();
    try {
      await client.query("BEGIN");
      // SKIP LOCKED lets concurrent runs (cron + post-save) split the queue.
      // Users that already failed this run are skipped so the loop can't spin.
      const events = await client.query<{ id: string; entity_id: string }>(
        `SELECT id, entity_id FROM graph_sync_queue
         WHERE processed_at IS NULL
           AND ($2::uuid[] IS NULL OR entity_id = ANY($2::uuid[]))
           AND NOT (entity_id = ANY($3::uuid[]))
         ORDER BY id
         LIMIT $1
         FOR UPDATE SKIP LOCKED`,
        [batchSize, userIds ?? null, result.failedUsers],
      );
      if (events.rows.length === 0) {
        await client.query("COMMIT");
        break;
      }

      const eventsByUser = new Map<string, string[]>();
      for (const e of events.rows) {
        eventsByUser.set(e.entity_id, [...(eventsByUser.get(e.entity_id) ?? []), e.id]);
      }

      const done: string[] = [];
      for (const [userId, eventIds] of eventsByUser) {
        // Read inside the batch transaction; a Postgres error fails the whole batch.
        const state = await readUserState(client, userId);
        try {
          await writeUser(userId, state);
          done.push(...eventIds);
          result.syncedUsers++;
        } catch (err) {
          // Connectivity problems affect every user: stop and leave the batch pending.
          if (neo4j.isRetriableError(err)) throw err;
          console.warn("graph-sync: failed to sync user", userId, err instanceof Error ? err.message : err);
          result.failedUsers.push(userId);
        }
      }

      await client.query("UPDATE graph_sync_queue SET processed_at = now() WHERE id = ANY($1::bigint[])", [done]);
      await client.query("COMMIT");
      result.processedEvents += done.length;
    } catch (err) {
      await client.query("ROLLBACK").catch(() => {});
      throw err;
    } finally {
      client.release();
    }
  }

  return result;
}
