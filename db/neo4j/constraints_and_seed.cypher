// =========================================================
// Brew — Neo4j Graph Schema (teammate matching)
// =========================================================
// Run against a fresh Neo4j AuraDB instance (Neo4j 5).
//
// Postgres is the source of truth for users, skills, and interests; this
// graph mirrors them (kept current by the graph_sync_queue worker — see
// db/postgres/schema.sql section 7). COLLABORATED_WITH edges currently live
// only here: Postgres has no collaborations table yet.
//
// Graph model:
//   (:User {id, name})-[:HAS_SKILL {proficiency}]->(:Skill {name})
//   (:User)-[:INTERESTED_IN]->(:Interest {name})
//   (:User)-[:COLLABORATED_WITH {project}]->(:User)   // treat as undirected
//
// The teammate query lives in db/neo4j/queries/teammates.cypher.

// ---------------------------------------------------------
// 1. Constraints
// ---------------------------------------------------------
// Each uniqueness constraint is backed by its own range index, so lookups
// such as MATCH (u:User {id: $userId}) are already index-backed. There is
// deliberately no separate CREATE INDEX on User.id: it would only duplicate
// the index the constraint already maintains.
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;

CREATE CONSTRAINT skill_name_unique IF NOT EXISTS
FOR (s:Skill) REQUIRE s.name IS UNIQUE;

CREATE CONSTRAINT interest_name_unique IF NOT EXISTS
FOR (i:Interest) REQUIRE i.name IS UNIQUE;

// ---------------------------------------------------------
// 2. Skills & interests (mirror the Postgres reference data)
// ---------------------------------------------------------
UNWIND ['javascript','typescript','python','react','nextjs',
        'machine-learning','computer-vision','nlp','postgresql',
        'neo4j','vector-search','ui-design','mobile','devops',
        'rust','go','data-engineering','geospatial','iot','llm'] AS skillName
MERGE (:Skill {name: skillName});

UNWIND ['climate','healthtech','accessibility','fintech-alt',
        'education','security','conservation','civic-tech',
        'developer-tools','research-tools'] AS interestName
MERGE (:Interest {name: interestName});

// ---------------------------------------------------------
// 3. Seed users — same IDs, skills, and interests as db/postgres/seed.sql
// ---------------------------------------------------------
UNWIND [
  ['00000000-0000-4000-8000-000000000001', 'Aisha Rahman'],
  ['00000000-0000-4000-8000-000000000002', 'Mateo Alvarez'],
  ['00000000-0000-4000-8000-000000000003', 'Priya Nair'],
  ['00000000-0000-4000-8000-000000000004', 'Jonas Becker'],
  ['00000000-0000-4000-8000-000000000005', 'Mei Lin'],
  ['00000000-0000-4000-8000-000000000006', 'Kwame Mensah'],
  ['00000000-0000-4000-8000-000000000007', 'Sofia Rossi'],
  ['00000000-0000-4000-8000-000000000008', 'Arjun Mehta'],
  ['00000000-0000-4000-8000-000000000009', 'Hana Sato'],
  ['00000000-0000-4000-8000-000000000010', "Liam O'Connor"]
] AS row
MERGE (u:User {id: row[0]})
SET u.name = row[1];

// [userId, skill, proficiency]
UNWIND [
  ['00000000-0000-4000-8000-000000000001', 'python', 5],
  ['00000000-0000-4000-8000-000000000001', 'machine-learning', 4],
  ['00000000-0000-4000-8000-000000000001', 'nlp', 4],
  ['00000000-0000-4000-8000-000000000001', 'postgresql', 3],
  ['00000000-0000-4000-8000-000000000002', 'typescript', 5],
  ['00000000-0000-4000-8000-000000000002', 'react', 5],
  ['00000000-0000-4000-8000-000000000002', 'nextjs', 4],
  ['00000000-0000-4000-8000-000000000002', 'ui-design', 3],
  ['00000000-0000-4000-8000-000000000003', 'python', 4],
  ['00000000-0000-4000-8000-000000000003', 'computer-vision', 5],
  ['00000000-0000-4000-8000-000000000003', 'machine-learning', 4],
  ['00000000-0000-4000-8000-000000000003', 'iot', 3],
  ['00000000-0000-4000-8000-000000000004', 'go', 5],
  ['00000000-0000-4000-8000-000000000004', 'devops', 5],
  ['00000000-0000-4000-8000-000000000004', 'postgresql', 4],
  ['00000000-0000-4000-8000-000000000004', 'rust', 3],
  ['00000000-0000-4000-8000-000000000005', 'ui-design', 5],
  ['00000000-0000-4000-8000-000000000005', 'react', 4],
  ['00000000-0000-4000-8000-000000000005', 'mobile', 4],
  ['00000000-0000-4000-8000-000000000005', 'javascript', 4],
  ['00000000-0000-4000-8000-000000000006', 'data-engineering', 5],
  ['00000000-0000-4000-8000-000000000006', 'python', 4],
  ['00000000-0000-4000-8000-000000000006', 'postgresql', 4],
  ['00000000-0000-4000-8000-000000000006', 'geospatial', 4],
  ['00000000-0000-4000-8000-000000000007', 'llm', 5],
  ['00000000-0000-4000-8000-000000000007', 'nlp', 5],
  ['00000000-0000-4000-8000-000000000007', 'vector-search', 4],
  ['00000000-0000-4000-8000-000000000007', 'python', 4],
  ['00000000-0000-4000-8000-000000000008', 'mobile', 5],
  ['00000000-0000-4000-8000-000000000008', 'typescript', 4],
  ['00000000-0000-4000-8000-000000000008', 'react', 4],
  ['00000000-0000-4000-8000-000000000008', 'devops', 2],
  ['00000000-0000-4000-8000-000000000009', 'neo4j', 4],
  ['00000000-0000-4000-8000-000000000009', 'data-engineering', 3],
  ['00000000-0000-4000-8000-000000000009', 'python', 3],
  ['00000000-0000-4000-8000-000000000009', 'vector-search', 3],
  ['00000000-0000-4000-8000-000000000010', 'rust', 5],
  ['00000000-0000-4000-8000-000000000010', 'iot', 4],
  ['00000000-0000-4000-8000-000000000010', 'go', 3],
  ['00000000-0000-4000-8000-000000000010', 'devops', 3]
] AS row
MATCH (u:User {id: row[0]}), (s:Skill {name: row[1]})
MERGE (u)-[r:HAS_SKILL]->(s)
SET r.proficiency = row[2];

// [userId, interest]
UNWIND [
  ['00000000-0000-4000-8000-000000000001', 'healthtech'],
  ['00000000-0000-4000-8000-000000000001', 'education'],
  ['00000000-0000-4000-8000-000000000002', 'climate'],
  ['00000000-0000-4000-8000-000000000002', 'civic-tech'],
  ['00000000-0000-4000-8000-000000000003', 'conservation'],
  ['00000000-0000-4000-8000-000000000003', 'climate'],
  ['00000000-0000-4000-8000-000000000004', 'security'],
  ['00000000-0000-4000-8000-000000000004', 'developer-tools'],
  ['00000000-0000-4000-8000-000000000005', 'accessibility'],
  ['00000000-0000-4000-8000-000000000005', 'education'],
  ['00000000-0000-4000-8000-000000000006', 'climate'],
  ['00000000-0000-4000-8000-000000000006', 'civic-tech'],
  ['00000000-0000-4000-8000-000000000007', 'research-tools'],
  ['00000000-0000-4000-8000-000000000007', 'education'],
  ['00000000-0000-4000-8000-000000000008', 'fintech-alt'],
  ['00000000-0000-4000-8000-000000000008', 'accessibility'],
  ['00000000-0000-4000-8000-000000000009', 'research-tools'],
  ['00000000-0000-4000-8000-000000000009', 'developer-tools'],
  ['00000000-0000-4000-8000-000000000010', 'conservation'],
  ['00000000-0000-4000-8000-000000000010', 'security']
] AS row
MATCH (u:User {id: row[0]}), (i:Interest {name: row[1]})
MERGE (u)-[:INTERESTED_IN]->(i);

// ---------------------------------------------------------
// 4. Past collaborations (graph-only for now)
// ---------------------------------------------------------
// Chosen so the 2-hop part of the teammate query has something to find,
// e.g. Aisha -> Sofia -> Hana, and Mateo -> Kwame -> Priya -> Liam.
// [userA, userB, project]
UNWIND [
  ['00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000007', 'clinic-faq-bot'],
  ['00000000-0000-4000-8000-000000000007', '00000000-0000-4000-8000-000000000009', 'paper-graph-explorer'],
  ['00000000-0000-4000-8000-000000000002', '00000000-0000-4000-8000-000000000006', 'bike-lane-tracker'],
  ['00000000-0000-4000-8000-000000000006', '00000000-0000-4000-8000-000000000003', 'canopy-cover-map'],
  ['00000000-0000-4000-8000-000000000003', '00000000-0000-4000-8000-000000000010', 'river-sensor-net'],
  ['00000000-0000-4000-8000-000000000004', '00000000-0000-4000-8000-000000000010', 'edge-log-agent'],
  ['00000000-0000-4000-8000-000000000005', '00000000-0000-4000-8000-000000000008', 'accessible-budget-app']
] AS row
MATCH (a:User {id: row[0]}), (b:User {id: row[1]})
MERGE (a)-[:COLLABORATED_WITH {project: row[2]}]->(b);
