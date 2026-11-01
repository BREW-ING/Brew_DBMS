import { z } from "zod";

// Shared by the curator pages (client) and /api/curator/* (server).

// "Low-confidence tags only" on the review page keeps signals whose
// signal_skills average below this.
export const LOW_CONFIDENCE = 0.5;

// The adapters merge config over their defaults key by key, so it has to be
// a JSON object, not an array or a bare value.
const MAX_CONFIG_CHARS = 10_000;

// Generous for filters like repo lists and arXiv categories; keeps a pasted
// blob from landing in a row every ingestion run reads. Measured minified, so
// the editor's indentation doesn't count.
export const sourceConfigSchema = z
  .record(z.string(), z.json(), { error: 'Config must be a JSON object, e.g. { "min_points": 20 }' })
  .refine((c) => JSON.stringify(c).length <= MAX_CONFIG_CHARS, `Config must be under ${MAX_CONFIG_CHARS} characters`);

export type SourceConfig = z.infer<typeof sourceConfigSchema>;

export const sourceUpdateSchema = z
  .object({
    isActive: z.boolean().optional(),
    config: sourceConfigSchema.optional(),
  })
  .refine((v) => v.isActive !== undefined || v.config !== undefined, "Nothing to update");

export type SourceUpdate = z.infer<typeof sourceUpdateSchema>;

/** Parses the config editor's text, with a message fit to show under it. */
export function parseSourceConfig(text: string): { ok: true; config: SourceConfig } | { ok: false; error: string } {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Invalid JSON" };
  }
  const parsed = sourceConfigSchema.safeParse(value);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid config" };
  return { ok: true, config: parsed.data };
}

export const signalStaleSchema = z.object({
  // Staleness is one-way (see DATABASE.md), so the only valid edit is "stale".
  isStale: z.literal(true),
});

export const signalSkillsSchema = z.object({
  skills: z
    .array(z.string().trim().min(1, "Enter a skill name").max(40, "Keep it under 40 characters"))
    .max(20, "Up to 20 skills"),
});

export type SignalSkillsInput = z.infer<typeof signalSkillsSchema>;
