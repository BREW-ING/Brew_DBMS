import "server-only";

import type { SourceConfig, SourceUpdate } from "@/lib/curator-schema";
import { getPool } from "@/lib/db";
import type { SignalSource } from "@/lib/suggestions";

export interface IngestionSource {
  id: number;
  sourceType: SignalSource;
  config: SourceConfig;
  isActive: boolean;
  /** ISO 8601; null until fetch_signals has run this source once. */
  lastFetchedAt: string | null;
}

type SourceRow = {
  id: number;
  source_type: SignalSource;
  config: SourceConfig;
  is_active: boolean;
  last_fetched_at: Date | null;
};

const COLUMNS = "id, source_type, config, is_active, last_fetched_at";

function toSource(row: SourceRow): IngestionSource {
  return {
    id: row.id,
    sourceType: row.source_type,
    config: row.config,
    isActive: row.is_active,
    lastFetchedAt: row.last_fetched_at?.toISOString() ?? null,
  };
}

export async function listSources(): Promise<IngestionSource[]> {
  const { rows } = await getPool().query<SourceRow>(
    `SELECT ${COLUMNS} FROM ingestion_sources ORDER BY source_type, id`,
  );
  return rows.map(toSource);
}

/** Applies whichever fields are set. Null if the source doesn't exist. */
export async function updateSource(id: number, update: SourceUpdate): Promise<IngestionSource | null> {
  const { rows } = await getPool().query<SourceRow>(
    `UPDATE ingestion_sources
     SET is_active = COALESCE($2::boolean, is_active),
         config    = COALESCE($3::jsonb, config)
     WHERE id = $1
     RETURNING ${COLUMNS}`,
    [id, update.isActive ?? null, update.config === undefined ? null : JSON.stringify(update.config)],
  );
  const row = rows[0];
  return row ? toSource(row) : null;
}
