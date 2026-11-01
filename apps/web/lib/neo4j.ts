import "server-only";

import neo4j, { type Driver } from "neo4j-driver";

// Reuse one driver across dev hot reloads instead of leaking a new one per edit.
const globalForNeo4j = globalThis as unknown as { neo4jDriver?: Driver };

/** Shared Neo4j driver. Created on first use so builds don't need NEO4J_* vars. */
export function getDriver(): Driver {
  if (globalForNeo4j.neo4jDriver) return globalForNeo4j.neo4jDriver;

  const uri = process.env.NEO4J_URI;
  const user = process.env.NEO4J_USER;
  const password = process.env.NEO4J_PASSWORD;
  if (!uri || !user || !password) throw new Error("NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD must be set");

  const driver = neo4j.driver(uri, neo4j.auth.basic(user, password), {
    maxConnectionPoolSize: 10,
    // Fail fast when Aura is unreachable; callers treat Neo4j as optional.
    connectionTimeout: 5_000,
    connectionAcquisitionTimeout: 10_000,
    maxTransactionRetryTime: 5_000,
  });
  globalForNeo4j.neo4jDriver = driver;
  return driver;
}
