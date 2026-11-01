import { z } from "zod";

// Shared by the profile form (client) and PUT /api/profile (server).
// Bounds mirror the DB: user_skills.proficiency is CHECK (1..5).
export const profileSchema = z.object({
  skills: z
    .array(
      z.object({
        name: z.string().trim().min(1, "Enter a skill name").max(40, "Keep it under 40 characters"),
        proficiency: z.number().int().min(1).max(5),
      }),
    )
    .min(1, "Add at least one skill")
    .max(30, "Up to 30 skills")
    .refine(
      (skills) => new Set(skills.map((s) => s.name.trim().toLowerCase())).size === skills.length,
      "Each skill can only be listed once",
    ),
  interests: z.array(z.string().trim().min(1).max(40)).max(10, "Up to 10 interests"),
  teamSize: z
    .number({ error: "Enter a team size" })
    .int("Whole people only")
    .min(1, "At least 1")
    .max(10, "At most 10"),
  hoursAvailable: z
    .number({ error: "Enter your available hours" })
    .int("Whole hours only")
    .min(1, "At least 1 hour")
    .max(168, "There are only 168 hours in a week"),
});

export type ProfileFormValues = z.infer<typeof profileSchema>;
