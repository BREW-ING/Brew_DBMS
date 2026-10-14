// =========================================================
// Brew — teammate recommendations
// =========================================================
// Used by apps/web/app/api/teammates/route.ts.
//
// Parameters:
//   $userId  users.id (UUID string) of the person looking for teammates
//   $limit   maximum number of recommendations (integer, e.g. 10)
//
// A candidate must bring at least one skill the user lacks; that is the
// only filter. Everything else adjusts the score:
//   +2.0  per complementary skill   (they have it, the user doesn't)
//   -0.5  per overlapping skill     (a second person with the same skill adds less)
//   +1.5  per shared interest       (a boost, not a requirement)
//   +1.0  per mutual collaborator, capped at 3
//         (2-hop: someone the user has worked with has worked with them)
//   +1.0  if the user and candidate have collaborated directly
//
// COLLABORATED_WITH is stored once per pair (lower id -> higher id, mirroring
// Postgres collaborations) and matched here as undirected.

MATCH (me:User {id: $userId})
MATCH (other:User)
WHERE other <> me
WITH me, other,
     [(other)-[:HAS_SKILL]->(s:Skill) WHERE NOT EXISTS { (me)-[:HAS_SKILL]->(s) } | s.name]
         AS complementarySkills,
     [(other)-[:HAS_SKILL]->(s:Skill)<-[:HAS_SKILL]-(me) | s.name]
         AS overlappingSkills,
     [(me)-[:INTERESTED_IN]->(i:Interest)<-[:INTERESTED_IN]-(other) | i.name]
         AS sharedInterests,
     // One entry per 2-hop path. With one edge per pair each intermediary
     // appears once, but dedupe anyway so stray duplicate edges in the
     // graph can't inflate the score.
     [(me)-[:COLLABORATED_WITH]-(mid:User)-[:COLLABORATED_WITH]-(other) | mid]
         AS viaPaths,
     EXISTS { (me)-[:COLLABORATED_WITH]-(other) }
         AS pastCollaborator
WHERE size(complementarySkills) > 0
WITH other, complementarySkills, overlappingSkills, sharedInterests, pastCollaborator,
     reduce(acc = [], m IN viaPaths | CASE WHEN m IN acc THEN acc ELSE acc + m END)
         AS mutualCollaborators
WITH other, complementarySkills, sharedInterests, pastCollaborator, mutualCollaborators,
       2.0 * size(complementarySkills)
     - 0.5 * size(overlappingSkills)
     + 1.5 * size(sharedInterests)
     + 1.0 * CASE WHEN size(mutualCollaborators) > 3 THEN 3 ELSE size(mutualCollaborators) END
     + CASE WHEN pastCollaborator THEN 1.0 ELSE 0.0 END
         AS score
RETURN other.id                             AS userId,
       other.name                           AS name,
       score,
       complementarySkills,
       sharedInterests,
       [m IN mutualCollaborators | m.name]  AS mutualCollaborators,
       pastCollaborator
ORDER BY score DESC, name
LIMIT $limit;
