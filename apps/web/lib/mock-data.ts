// Mock data for the UI until the API routes are wired to Postgres/Neo4j.
// Shapes mirror db/postgres/schema.sql (problem_signals, suggestions,
// trending_problem_areas) so swapping in real queries changes the getters only.

export type SignalSource = "github" | "arxiv" | "hn";

export interface UserSkill {
  name: string;
  /** 1-5, matches user_skills.proficiency */
  proficiency: number;
}

export interface UserProfile {
  name: string;
  skills: UserSkill[];
  interests: string[];
  teamSize: number;
  hoursAvailable: number;
}

export interface Suggestion {
  id: string;
  source: SignalSource;
  /** Link to the original issue/paper/post. */
  url: string;
  publishedAt: string;
  /** Broad topic area (problem_signals.category_tags[0]). */
  topic: string;
  /** Problem title (problem_signals.title). */
  title: string;
  /** Full problem text (problem_signals.raw_text). */
  rawText: string;
  /** One-line project idea. */
  idea: string;
  /** suggestions.similarity_score, 0-1 */
  relevance: number;
  /** suggestions.feasibility_score, 0-1 */
  feasibility: number;
  /** Skills the signal requires (signal_skills). */
  requiredSkills: string[];
}

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

function daysAgo(days: number): string {
  return new Date(Date.now() - days * 86_400_000).toISOString();
}

const profile: UserProfile = {
  name: "Aisha Khan",
  skills: [
    { name: "TypeScript", proficiency: 4 },
    { name: "React", proficiency: 4 },
    { name: "Python", proficiency: 3 },
    { name: "PostgreSQL", proficiency: 3 },
    { name: "Data visualization", proficiency: 2 },
  ],
  interests: ["climate", "healthtech", "developer tools"],
  teamSize: 3,
  hoursAvailable: 36,
};

const suggestions: Suggestion[] = [
  {
    id: "s1",
    source: "github",
    url: "https://github.com/example/open-energy/issues/412",
    publishedAt: daysAgo(2),
    topic: "climate",
    title: "No easy way to compare household energy usage against regional grid carbon intensity",
    rawText:
      "Users of the dashboard can see their smart-meter readings, but there is no way to overlay them with the carbon intensity of the regional grid at the same time. Several people have asked for a view that shows when their consumption was 'dirtiest' and suggests shifting flexible loads (dishwasher, EV charging) to cleaner hours. The data is available from public grid APIs, but nobody has stitched it together.",
    idea: "A web app that overlays smart-meter data with live grid carbon intensity and suggests cleaner hours to run appliances.",
    relevance: 0.91,
    feasibility: 0.82,
    requiredSkills: ["TypeScript", "React", "Data visualization", "Python"],
  },
  {
    id: "s2",
    source: "arxiv",
    url: "https://arxiv.org/abs/2601.01234",
    publishedAt: daysAgo(5),
    topic: "healthtech",
    title: "Lightweight triage of patient-reported symptoms with small language models",
    rawText:
      "We show that a 300M-parameter model fine-tuned on de-identified triage notes matches larger models at routing patient-reported symptoms to the right care pathway. However, clinics lack a simple interface for staff to review, correct and audit the model's suggestions, which limits adoption in low-resource settings.",
    idea: "A clinician-facing review queue that lets staff accept or correct model triage suggestions and logs every decision.",
    relevance: 0.84,
    feasibility: 0.64,
    requiredSkills: ["Python", "React", "PostgreSQL", "Machine learning"],
  },
  {
    id: "s3",
    source: "hn",
    url: "https://news.ycombinator.com/item?id=40000001",
    publishedAt: daysAgo(1),
    topic: "developer tools",
    title: "Ask HN: How do you keep track of flaky tests across CI runs?",
    rawText:
      "Our CI has hundreds of tests and a handful flake every week. We re-run and move on, but there's no history of which tests flake, how often, or since when. Existing tools are either expensive SaaS or tied to one CI provider. Is anyone using something simple that just ingests JUnit XML and shows trends?",
    idea: "Ingest JUnit XML from any CI and chart per-test flake rates over time in a self-hostable dashboard.",
    relevance: 0.79,
    feasibility: 0.88,
    requiredSkills: ["TypeScript", "PostgreSQL", "Data visualization"],
  },
  {
    id: "s4",
    source: "github",
    url: "https://github.com/example/transit-tools/issues/88",
    publishedAt: daysAgo(9),
    topic: "civic tech",
    title: "Accessible route planning ignores elevator outages",
    rawText:
      "The route planner treats every station as step-free if it has an elevator, even when the transit agency's feed reports the elevator as out of service. Wheelchair users end up stranded. The outage feed exists (GTFS-realtime alerts) but is not consumed by the planner.",
    idea: "A step-free journey planner that reroutes around live elevator outages from GTFS-realtime alerts.",
    relevance: 0.68,
    feasibility: 0.57,
    requiredSkills: ["TypeScript", "React", "Geospatial", "Python"],
  },
  {
    id: "s5",
    source: "arxiv",
    url: "https://arxiv.org/abs/2601.04567",
    publishedAt: daysAgo(16),
    topic: "education",
    title: "Measuring misconception persistence in introductory programming courses",
    rawText:
      "Students' misconceptions about variables and references persist well beyond the week they are taught. We release a labelled dataset of 12k student submissions annotated with misconception types, but instructors currently have no tooling to spot these patterns in their own classes.",
    idea: "A dashboard that flags recurring misconceptions in student code submissions using the released dataset as a baseline.",
    relevance: 0.61,
    feasibility: 0.71,
    requiredSkills: ["Python", "Machine learning", "React"],
  },
];

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

export async function getProfile(): Promise<UserProfile> {
  return profile;
}

export async function getSuggestions(): Promise<Suggestion[]> {
  return [...suggestions].sort((a, b) => b.relevance - a.relevance);
}

export async function getSuggestion(id: string): Promise<Suggestion | undefined> {
  return suggestions.find((s) => s.id === id);
}

export async function getTeammates(): Promise<Teammate[]> {
  return teammates;
}

export async function getTrendingTopics(): Promise<TrendingTopic[]> {
  return [...trending].sort((a, b) => b.signalCount - a.signalCount);
}

/** Split a signal's required skills into ones the user has and ones they lack. */
export function matchSkills(
  required: string[],
  userSkills: UserSkill[],
): { have: string[]; missing: string[] } {
  const owned = new Set(userSkills.map((s) => s.name.toLowerCase()));
  return {
    have: required.filter((s) => owned.has(s.toLowerCase())),
    missing: required.filter((s) => !owned.has(s.toLowerCase())),
  };
}
