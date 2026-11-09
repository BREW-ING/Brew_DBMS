import "server-only";

import neo4j from "neo4j-driver";
import type { FieldDef } from "pg";

import { getPool } from "@/lib/db";
import { getDriver } from "@/lib/neo4j";
import { parseSections, readQueryFile, type QuerySection } from "@/lib/query-files";

export type Cell = string | number | null;

export interface ReportTable {
  columns: string[];
  rows: Cell[][];
}

export interface ChartSeries {
  column: string;
  name: string;
  /** CSS color, e.g. "var(--primary)" */
  color: string;
}

export interface ReportDef {
  id: string;
  source: "postgres" | "neo4j";
  /** One line on the SQL/graph feature the report shows. */
  note: string;
  chart?: { category: string; series: ChartSeries[] };
}

export type ReportResult =
  | { id: string; title: string; status: "ok"; table: ReportTable }
  | { id: string; title: string; status: "error"; message: string };

const SQL_FILE = "db/postgres/reports.sql";
const CYPHER_FILE = "db/neo4j/queries/reports.cypher";
const TIMEOUT_MS = 15_000;

// The queries themselves live in the files above; this list picks which
// sections the page shows and describes them. G5 (whole-graph picture) only
// makes sense in Aura's graph view, so it's left out.
export const REPORTS: ReportDef[] = [
  { id: "R1", source: "postgres", note: "COUNT with FILTER clauses for conditional aggregates, grouped by source." },
  {
    id: "R2",
    source: "postgres",
    note: "AVG and MAX over a JOIN, grouped by skill.",
    chart: { category: "skill", series: [{ column: "avg_proficiency", name: "Avg proficiency", color: "var(--primary)" }] },
  },
  {
    id: "R3",
    source: "postgres",
    note: "Two aggregated subqueries LEFT JOINed to skills, with COALESCE filling the missing side.",
    chart: {
      category: "skill",
      series: [
        { column: "users_who_have_it", name: "Users who have it", color: "var(--primary)" },
        { column: "problems_needing_it", name: "Problems needing it", color: "var(--chart-2)" },
      ],
    },
  },
  { id: "R4", source: "postgres", note: "LEFT JOIN, so interests nobody has picked still appear with 0." },
  { id: "R5", source: "postgres", note: "AVG over a JOIN with constraints, grouped by role." },
  { id: "R6", source: "postgres", note: "UNION ALL folds both sides of each collaboration pair into one column." },
  {
    id: "R7",
    source: "postgres",
    note: "Stored function in a LATERAL join, ranked with RANK() OVER (PARTITION BY user).",
  },
  { id: "R8", source: "postgres", note: "AVG and COUNT FILTER over a set-returning stored function's output." },
  {
    id: "R9",
    source: "postgres",
    note: "Reads the trending_problem_areas materialized view (read-only here: the REFRESH is skipped).",
  },
  { id: "R10", source: "postgres", note: "Pending rows in the graph_sync_queue outbox, grouped by entity and op." },
  { id: "R11", source: "postgres", note: "Recursive CTE (WITH RECURSIVE) walking the collaboration graph up to 3 hops." },
  { id: "R12", source: "postgres", note: "Correlated subquery: the inner MAX uses the outer row's skill." },
  { id: "R13", source: "postgres", note: "Nested subqueries: IN with a HAVING that compares to an average from a derived table." },
  { id: "G1", source: "neo4j", note: "Aggregates over a property stored on HAS_SKILL relationships." },
  { id: "G2", source: "neo4j", note: "OPTIONAL MATCH on an undirected relationship to get each user's degree." },
  { id: "G3", source: "neo4j", note: "Pattern match through a shared Interest node, excluding pairs joined by an edge." },
  { id: "G4", source: "neo4j", note: "Two-hop traversal through a mutual collaborator." },
];

// --- cell formatting ---------------------------------------------------------

function formatValue(value: unknown): Cell {
  if (value === null || value === undefined) return null;
  if (typeof value === "number" || typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (neo4j.isInt(value)) return value.toNumber();
  if (value instanceof Date) return `${value.toISOString().slice(0, 16).replace("T", " ")} UTC`;
  if (Array.isArray(value)) return value.map((v) => String(formatValue(v) ?? "")).join(", ");
  return JSON.stringify(value);
}

// pg returns bigint (COUNT) and numeric (ROUND) as strings, and DATE as a
// Date at local midnight.
const PG_INT8 = 20;
const PG_NUMERIC = 1700;
const PG_DATE = 1082;

function pgCell(value: unknown, field: FieldDef | undefined): Cell {
  if (value === null || value === undefined) return null;
  if (field?.dataTypeID === PG_INT8 || field?.dataTypeID === PG_NUMERIC) return Number(value);
  if (field?.dataTypeID === PG_DATE && value instanceof Date) {
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
  }
  return formatValue(value);
}

// --- running -------------------------------------------------------------------

async function runPostgres(sql: string): Promise<ReportTable> {
  const client = await getPool().connect();
  try {
    // READ ONLY makes the page unable to write, whatever the file contains.
    await client.query("BEGIN READ ONLY");
    await client.query(`SET LOCAL statement_timeout = ${TIMEOUT_MS}`);
    const result = await client.query<unknown[]>({ text: sql, rowMode: "array" });
    await client.query("ROLLBACK");
    return {
      columns: result.fields.map((f) => f.name),
      rows: result.rows.map((row) => row.map((v, i) => pgCell(v, result.fields[i]))),
    };
  } catch (err) {
    await client.query("ROLLBACK").catch(() => {});
    throw err;
  } finally {
    client.release();
  }
}

async function runNeo4j(cypher: string): Promise<ReportTable> {
  const session = getDriver().session({ defaultAccessMode: neo4j.session.READ });
  try {
    const result = await session.executeRead((tx) => tx.run(cypher), { timeout: TIMEOUT_MS });
    const columns = result.records[0]?.keys.map(String) ?? [];
    return { columns, rows: result.records.map((r) => columns.map((c) => formatValue(r.get(c)))) };
  } finally {
    await session.close();
  }
}

/** Message safe to show in the card. SQL/Cypher errors are shown; connection details are not. */
function errorMessage(def: ReportDef, err: unknown): string {
  if (def.source === "neo4j") {
    const code = err instanceof neo4j.Neo4jError ? err.code : "";
    return code.startsWith("Neo.ClientError.Statement")
      ? `Query failed: ${(err as Error).message}`
      : "The graph database is unavailable right now.";
  }
  // pg's DatabaseError carries a five-character SQLSTATE; connection errors don't.
  const sqlState = (err as { code?: unknown }).code;
  return typeof sqlState === "string" && /^[0-9A-Z]{5}$/.test(sqlState)
    ? `Query failed: ${(err as Error).message}`
    : "The database is unavailable right now.";
}

async function loadSections(relPath: string): Promise<Map<string, QuerySection>> {
  const sections = parseSections(await readQueryFile(relPath));
  return new Map(sections.map((s) => [s.id, s]));
}

/** Runs one report. Never throws: failures come back as status "error". */
export async function runReport(def: ReportDef): Promise<ReportResult> {
  const file = def.source === "postgres" ? SQL_FILE : CYPHER_FILE;
  let title = def.id;
  try {
    const section = (await loadSections(file)).get(def.id);
    if (!section) return { id: def.id, title, status: "error", message: `${def.id} was not found in ${file}.` };
    title = `${section.id}. ${section.title}`;

    // R9 refreshes the view before reading it; the page only reads.
    const [query, ...rest] = section.statements.filter((s) => !/^REFRESH\b/i.test(s));
    if (!query || rest.length > 0) {
      return { id: def.id, title, status: "error", message: `Expected one read query in ${def.id}.` };
    }

    const table = def.source === "postgres" ? await runPostgres(query) : await runNeo4j(query);
    return { id: def.id, title, status: "ok", table };
  } catch (err) {
    console.warn(`reports: ${def.id} failed`, err instanceof Error ? err.message : err);
    return { id: def.id, title, status: "error", message: errorMessage(def, err) };
  }
}
