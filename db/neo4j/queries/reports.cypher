// =========================================================
// Brew — graph reports (run in Neo4j Aura → Query, one at a time)
// =========================================================

// G1. Average proficiency per skill (graph version of the SQL report)
MATCH (u:User)-[r:HAS_SKILL]->(s:Skill)
RETURN s.name AS skill,
       count(u) AS users,
       round(avg(r.proficiency), 2) AS avg_proficiency
ORDER BY users DESC, avg_proficiency DESC;

// G2. Most connected people (degree of each user in the collaboration graph)
MATCH (u:User)
OPTIONAL MATCH (u)-[c:COLLABORATED_WITH]-(:User)
RETURN u.name AS user, count(c) AS collaborators
ORDER BY collaborators DESC, user;

// G3. Pairs of users who share an interest but have never worked together
//     (hard to express as SQL joins — natural as a graph pattern)
MATCH (a:User)-[:INTERESTED_IN]->(i:Interest)<-[:INTERESTED_IN]-(b:User)
WHERE a.id < b.id AND NOT (a)-[:COLLABORATED_WITH]-(b)
RETURN a.name AS user_a, b.name AS user_b, collect(i.name) AS shared_interests
ORDER BY size(shared_interests) DESC, user_a;

// G4. Two-hop collaboration: people reachable through one shared collaborator
MATCH (a:User)-[:COLLABORATED_WITH]-(mid:User)-[:COLLABORATED_WITH]-(b:User)
WHERE a.id < b.id AND NOT (a)-[:COLLABORATED_WITH]-(b)
RETURN a.name AS user_a, mid.name AS via, b.name AS user_b
ORDER BY user_a;

// G5. Picture of the whole graph (switch the result to Graph view)
MATCH (u:User)-[r]->(x)
RETURN u, r, x;
