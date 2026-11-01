// Mock data for the UI until the API routes are wired to Postgres/Neo4j.
// Suggestions are real now (lib/suggestions.ts); teammates and trending are
// still mocked. Shapes mirror the Neo4j query and trending_problem_areas so
// swapping in real queries changes the getters only.

export interface Teammate {
  id: string;
  name: string;
  complementarySkills: string[];
  sharedInterests: string[];
  /** Collaboration path that surfaced this match, e.g. "Worked with Sofia". */
  reason: string;
}

export interface TrendingTopic {
  category: string;
  signalCount: number;
}

const teammates: Teammate[] = [
  {
    id: "t1",
    name: "Hana Sato",
    complementarySkills: ["Machine learning", "Figma"],
    sharedInterests: ["healthtech", "climate"],
    reason: "Worked with Sofia Rossi, who you built a project with",
  },
  {
    id: "t2",
    name: "Marcus Webb",
    complementarySkills: ["Geospatial", "Go"],
    sharedInterests: ["civic tech"],
    reason: "Worked with you at the Spring Climate Hack",
  },
  {
    id: "t3",
    name: "Priya Nair",
    complementarySkills: ["Machine learning", "DevOps"],
    sharedInterests: ["developer tools", "education"],
    reason: "Worked with Leo Martins on two projects",
  },
  {
    id: "t4",
    name: "Tomás Ortega",
    complementarySkills: ["Swift", "UX research"],
    sharedInterests: ["healthtech"],
    reason: "Worked with Hana Sato, a strong match for you",
  },
];

const trending: TrendingTopic[] = [
  { category: "climate", signalCount: 48 },
  { category: "developer tools", signalCount: 41 },
  { category: "healthtech", signalCount: 33 },
  { category: "AI safety", signalCount: 27 },
  { category: "education", signalCount: 19 },
  { category: "civic tech", signalCount: 14 },
  { category: "fintech", signalCount: 11 },
  { category: "accessibility", signalCount: 8 },
];

// Async to match the shape of the future DB-backed getters.

export async function getTeammates(): Promise<Teammate[]> {
  return teammates;
}

export async function getTrendingTopics(): Promise<TrendingTopic[]> {
  return [...trending].sort((a, b) => b.signalCount - a.signalCount);
}
