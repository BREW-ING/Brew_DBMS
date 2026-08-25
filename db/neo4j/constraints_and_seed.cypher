// =========================================================
// Brew — Neo4j Graph Schema (teammate matching)
// =========================================================
// Run against a fresh Neo4j AuraDB instance.

// ---------------------------------------------------------
// 1. Constraints (uniqueness + existence)
// ---------------------------------------------------------
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;

CREATE CONSTRAINT skill_name_unique IF NOT EXISTS
FOR (s:Skill) REQUIRE s.name IS UNIQUE;

CREATE CONSTRAINT interest_name_unique IF NOT EXISTS
FOR (i:Interest) REQUIRE i.name IS UNIQUE;

// ---------------------------------------------------------
// 2. Indexes (query performance)
// ---------------------------------------------------------
CREATE INDEX user_id_index IF NOT EXISTS FOR (u:User) ON (u.id);

// ---------------------------------------------------------
// 3. Seed skills & interests (should mirror Postgres `skills` table)
// ---------------------------------------------------------
UNWIND ['javascript','typescript','python','react','nextjs',
        'machine-learning','computer-vision','nlp','postgresql',
        'neo4j','vector-search','ui-design','mobile','devops'] AS skillName
MERGE (:Skill {name: skillName});

UNWIND ['climate','healthtech','accessibility','fintech-alt',
        'education','security','conservation','civic-tech'] AS interestName
MERGE (:Interest {name: interestName});

// ---------------------------------------------------------
// 4. Sample seed users (replace with real sync from Postgres `users`)
// ---------------------------------------------------------
MERGE (u1:User {id: 'sample-user-1', name: 'Sample User A'})
MERGE (u2:User {id: 'sample-user-2', name: 'Sample User B'})

WITH u1, u2
MATCH (s1:Skill {name: 'react'}), (s2:Skill {name: 'python'}),
      (s3:Skill {name: 'machine-learning'}), (s4:Skill {name: 'ui-design'})
MERGE (u1)-[:HAS_SKILL {proficiency: 4}]->(s1)
MERGE (u1)-[:HAS_SKILL {proficiency: 3}]->(s4)
MERGE (u2)-[:HAS_SKILL {proficiency: 5}]->(s2)
MERGE (u2)-[:HAS_SKILL {proficiency: 4}]->(s3)

WITH u1, u2
MATCH (i1:Interest {name: 'climate'})
MERGE (u1)-[:INTERESTED_IN]->(i1)
MERGE (u2)-[:INTERESTED_IN]->(i1)

MERGE (u1)-[:COLLABORATED_WITH {project: 'sample-past-hackathon'}]->(u2);

// ---------------------------------------------------------
// 5. Representative teammate-matching query (advanced feature)
// ---------------------------------------------------------
// Given a user, find others whose skills are complementary (little overlap)
// but who share at least one interest — this is the core "why Neo4j" query.
//
// MATCH (me:User {id: $userId})-[:HAS_SKILL]->(mySkill:Skill)
// MATCH (me)-[:INTERESTED_IN]->(sharedInterest:Interest)<-[:INTERESTED_IN]-(other:User)
// WHERE other <> me
// OPTIONAL MATCH (other)-[:HAS_SKILL]->(theirSkill:Skill)
// WITH me, other, sharedInterest,
//      collect(DISTINCT mySkill.name) AS mySkills,
//      collect(DISTINCT theirSkill.name) AS theirSkills
// WITH other,
//      count(DISTINCT sharedInterest) AS sharedInterestCount,
//      size([s IN theirSkills WHERE NOT s IN mySkills]) AS complementarySkillCount
// RETURN other.id, other.name, sharedInterestCount, complementarySkillCount
// ORDER BY complementarySkillCount DESC, sharedInterestCount DESC
// LIMIT 10;
