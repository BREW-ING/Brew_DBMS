import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";

// The .sql/.cypher files live in db/ at the repo root so they stay runnable
// as-is in the Supabase SQL Editor and the Aura console. `next dev` and
// `next start` run from apps/web, two levels below the root.
const REPO_ROOT = path.resolve(process.cwd(), "..", "..");

export interface QuerySection {
  /** e.g. "R3" or "G1" */
  id: string;
  /** Header text after the id, e.g. "Skill supply vs demand (gap analysis)" */
  title: string;
  /** Statements in the section, comments removed, without trailing semicolons. */
  statements: string[];
}

/** Reads a query file by repo-relative path, e.g. "db/neo4j/queries/teammates.cypher". */
export async function readQueryFile(relPath: string): Promise<string> {
  return readFile(path.join(REPO_ROOT, relPath), "utf8");
}

function isComment(line: string): boolean {
  const trimmed = line.trimStart();
  return trimmed.startsWith("--") || trimmed.startsWith("//");
}

/** Splits code on `;`. Fine for these files: no semicolons inside strings. */
export function splitStatements(text: string): string[] {
  return text
    .split("\n")
    .filter((line) => !isComment(line))
    .join("\n")
    .split(";")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

// Matches report headers like "-- R1. Problem signals ..." or "// G2. Most connected ...".
const HEADER = /^\s*(?:--|\/\/)\s*([A-Z]\d+)\.\s+(.+?)\s*$/;

/** Splits a reports file into its numbered sections (R1, R2, ... / G1, G2, ...). */
export function parseSections(text: string): QuerySection[] {
  const sections: { id: string; title: string; lines: string[] }[] = [];
  for (const line of text.split(/\r?\n/)) {
    const [, id, title] = HEADER.exec(line) ?? [];
    if (id && title) {
      sections.push({ id, title, lines: [] });
    } else {
      sections.at(-1)?.lines.push(line);
    }
  }
  return sections.map(({ id, title, lines }) => ({ id, title, statements: splitStatements(lines.join("\n")) }));
}
