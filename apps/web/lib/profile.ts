import "server-only";

import { getPool } from "@/lib/db";
import type { ProfileFormValues } from "@/lib/profile-schema";

// Mirror the column defaults on constraints, for users without a row yet.
const DEFAULT_TEAM_SIZE = 1;
const DEFAULT_TIMEFRAME_HOURS = 48;

/**
 * Skill and interest names are stored as lowercase slugs ("machine-learning"),
 * matching the seeded vocabulary that signal tagging and Neo4j matching key on.
 */
export function toSlug(name: string): string {
  return name.trim().toLowerCase().replace(/[\s_]+/g, "-");
}

/** The user's profile, or null if the user doesn't exist. */
export async function getProfile(userId: string): Promise<ProfileFormValues | null> {
  const pool = getPool();
  const [user, skills, interests] = await Promise.all([
    pool.query<{ team_size: number | null; timeframe_hours: number | null }>(
      `SELECT c.team_size, c.timeframe_hours
       FROM users u LEFT JOIN constraints c ON c.user_id = u.id
       WHERE u.id = $1`,
      [userId],
    ),
    pool.query<{ name: string; proficiency: number }>(
      `SELECT s.name, us.proficiency
       FROM user_skills us JOIN skills s ON s.id = us.skill_id
       WHERE us.user_id = $1
       ORDER BY us.proficiency DESC, s.name`,
      [userId],
    ),
    pool.query<{ name: string }>(
      `SELECT i.name
       FROM user_interests ui JOIN interests i ON i.id = ui.interest_id
       WHERE ui.user_id = $1
       ORDER BY i.name`,
      [userId],
    ),
  ]);
  const row = user.rows[0];
  if (!row) return null;

  return {
    skills: skills.rows.map((s) => ({ name: s.name, proficiency: s.proficiency })),
    interests: interests.rows.map((i) => i.name),
    teamSize: row.team_size ?? DEFAULT_TEAM_SIZE,
    hoursAvailable: row.timeframe_hours ?? DEFAULT_TIMEFRAME_HOURS,
  };
}

/**
 * Replaces the user's skills and interests and upserts their constraints in one
 * transaction. The graph-sync triggers enqueue Neo4j events in that same
 * transaction. Returns false if the user doesn't exist.
 */
export async function saveProfile(userId: string, values: ProfileFormValues): Promise<boolean> {
  // Slugging can merge entries the form saw as distinct ("Machine learning" vs
  // "machine-learning"); keep the higher proficiency.
  const skills = new Map<string, number>();
  for (const s of values.skills) {
    const name = toSlug(s.name);
    skills.set(name, Math.max(skills.get(name) ?? 0, s.proficiency));
  }
  const skillNames = [...skills.keys()];
  const proficiencies = [...skills.values()];
  const interestNames = [...new Set(values.interests.map(toSlug))];

  const client = await getPool().connect();
  try {
    await client.query("BEGIN");

    // Row lock serializes concurrent saves for the same user.
    const user = await client.query("SELECT 1 FROM users WHERE id = $1 FOR UPDATE", [userId]);
    if (user.rowCount === 0) {
      await client.query("ROLLBACK");
      return false;
    }

    // Names the vocabulary doesn't have yet become new rows.
    await client.query(
      "INSERT INTO skills (name) SELECT unnest($1::text[]) ON CONFLICT (name) DO NOTHING",
      [skillNames],
    );
    await client.query("DELETE FROM user_skills WHERE user_id = $1", [userId]);
    await client.query(
      `INSERT INTO user_skills (user_id, skill_id, proficiency)
       SELECT $1, s.id, x.proficiency
       FROM unnest($2::text[], $3::smallint[]) AS x(name, proficiency)
       JOIN skills s ON s.name = x.name`,
      [userId, skillNames, proficiencies],
    );

    await client.query(
      "INSERT INTO interests (name) SELECT unnest($1::text[]) ON CONFLICT (name) DO NOTHING",
      [interestNames],
    );
    await client.query("DELETE FROM user_interests WHERE user_id = $1", [userId]);
    await client.query(
      `INSERT INTO user_interests (user_id, interest_id)
       SELECT $1, i.id FROM interests i WHERE i.name = ANY($2::text[])`,
      [userId, interestNames],
    );

    // preferred_stack isn't on the form, so an update leaves it alone.
    await client.query(
      `INSERT INTO constraints (user_id, team_size, timeframe_hours)
       VALUES ($1, $2, $3)
       ON CONFLICT (user_id) DO UPDATE
         SET team_size = EXCLUDED.team_size, timeframe_hours = EXCLUDED.timeframe_hours`,
      [userId, values.teamSize, values.hoursAvailable],
    );

    await client.query("COMMIT");
    return true;
  } catch (err) {
    await client.query("ROLLBACK").catch(() => {});
    throw err;
  } finally {
    client.release();
  }
}
