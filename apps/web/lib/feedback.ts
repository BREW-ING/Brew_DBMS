import "server-only";

import { z } from "zod";

import { getPool } from "@/lib/db";

// Bounds mirror the DB: feedback.rating is CHECK (1..5).
export const feedbackSchema = z.object({
  // guid, not uuid: seed rows can have hand-written ids that aren't RFC 4122.
  suggestionId: z.guid(),
  rating: z.number().int().min(1).max(5),
  comment: z.string().trim().max(2000).optional(),
});

export type FeedbackInput = z.infer<typeof feedbackSchema>;

export interface Feedback {
  id: string;
  suggestionId: string;
  rating: number;
  comment: string | null;
  createdAt: string;
}

type FeedbackRow = {
  id: string;
  suggestion_id: string;
  rating: number;
  comment: string | null;
  created_at: Date;
  inserted: boolean;
};

/**
 * Inserts or updates the user's rating of one of their own suggestions. The
 * INSERT ... SELECT only finds the suggestion if it belongs to the user, so
 * null means "not found or not yours". Omitting comment keeps any earlier one.
 */
export async function saveFeedback(
  userId: string,
  input: FeedbackInput,
): Promise<{ feedback: Feedback; created: boolean } | null> {
  const { rows } = await getPool().query<FeedbackRow>(
    `INSERT INTO feedback (suggestion_id, user_id, rating, comment)
     SELECT s.id, s.user_id, $3::smallint, $4::text
     FROM suggestions s
     WHERE s.id = $1::uuid AND s.user_id = $2::uuid
     ON CONFLICT (user_id, suggestion_id) DO UPDATE
       SET rating = EXCLUDED.rating,
           comment = COALESCE(EXCLUDED.comment, feedback.comment)
     RETURNING id, suggestion_id, rating, comment, created_at, (xmax = 0) AS inserted`,
    [input.suggestionId, userId, input.rating, input.comment ?? null],
  );
  const row = rows[0];
  if (!row) return null;
  return {
    feedback: {
      id: row.id,
      suggestionId: row.suggestion_id,
      rating: row.rating,
      comment: row.comment,
      createdAt: row.created_at.toISOString(),
    },
    created: row.inserted,
  };
}
