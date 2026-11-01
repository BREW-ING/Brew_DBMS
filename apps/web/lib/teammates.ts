import "server-only";

import neo4j from "neo4j-driver";

import { getDriver } from "@/lib/neo4j";
import { readQueryFile, splitStatements } from "@/lib/query-files";

export interface Teammate {
  userId: string;
  name: string;
  score: number;
  complementarySkills: string[];
  sharedInterests: string[];
  /** People who've worked with both the user and this teammate. */
  mutualCollaborators: string[];
  /** True if reachable through a mutual collaborator (a 2-hop path). */
  twoHop: boolean;
  /** True if the user and this teammate have collaborated directly. */
  pastCollaborator: boolean;
}

export type TeammatesResult =
  | { status: "ok"; teammates: Teammate[] }
  | { status: "graph_unavailable"; teammates: [] };

export const DEFAULT_LIMIT = 10;

const QUERY_FILE = "db/neo4j/queries/teammates.cypher";

async function loadQuery(): Promise<string> {
  const [query, ...rest] = splitStatements(await readQueryFile(QUERY_FILE));
  if (!query || rest.length > 0) throw new Error(`${QUERY_FILE} should contain exactly one statement`);
  return query;
}

/**
 * Runs teammates.cypher for the user. Neo4j is optional: any failure (Aura
 * down, NEO4J_* unset, query error) is logged and reported as graph_unavailable.
 */
export async function getTeammatesForUser(userId: string, limit = DEFAULT_LIMIT): Promise<TeammatesResult> {
  try {
    const query = await loadQuery();
    const session = getDriver().session({ defaultAccessMode: neo4j.session.READ });
    try {
      const result = await session.executeRead((tx) => tx.run(query, { userId, limit: neo4j.int(limit) }), {
        timeout: 10_000,
      });
      const teammates = result.records.map((r): Teammate => {
        const mutualCollaborators = r.get("mutualCollaborators") as string[];
        return {
          userId: r.get("userId") as string,
          name: r.get("name") as string,
          score: Number(r.get("score")),
          complementarySkills: r.get("complementarySkills") as string[],
          sharedInterests: r.get("sharedInterests") as string[],
          mutualCollaborators,
          twoHop: mutualCollaborators.length > 0,
          pastCollaborator: r.get("pastCollaborator") as boolean,
        };
      });
      return { status: "ok", teammates };
    } finally {
      await session.close();
    }
  } catch (err) {
    console.warn("teammates: graph query failed", { userId, error: err instanceof Error ? err.message : err });
    return { status: "graph_unavailable", teammates: [] };
  }
}
