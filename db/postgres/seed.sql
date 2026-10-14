-- =========================================================
-- Brew — demo seed data (run after schema.sql)
-- =========================================================
-- 10 users with skills, interests, constraints, and 7 past collaborations;
-- 3 ingestion sources;
-- 31 synthetic problem signals with signal_skills rows. Signals have no
-- embeddings — run the embedding job to fill them in.
--
-- Signal titles/text are invented examples, not real issues or papers, so
-- url is left NULL. Three signals are dated > 30 days ago to demonstrate
-- staleness.
--
-- Seed users cannot log in: password_hash holds a locked placeholder that no
-- password hashes to. Register a real account to use the app.
--
-- The user/skill/interest/collaboration inserts fire the graph-sync triggers, so
-- graph_sync_queue will hold pending events afterwards.
-- db/neo4j/constraints_and_seed.cypher creates the same graph directly;
-- running the sync worker as well is harmless (it is idempotent).
--
-- Re-runnable: every insert skips rows that already exist.

BEGIN;

-- ---------------------------------------------------------
-- Users (fixed UUIDs so the Neo4j seed can reference them)
-- ---------------------------------------------------------
INSERT INTO users (id, email, name, password_hash, role) VALUES
    ('00000000-0000-4000-8000-000000000001', 'aisha.rahman@example.com',  'Aisha Rahman',  '!seed-account-no-login', 'curator'),
    ('00000000-0000-4000-8000-000000000002', 'mateo.alvarez@example.com', 'Mateo Alvarez', '!seed-account-no-login', 'user'),
    ('00000000-0000-4000-8000-000000000003', 'priya.nair@example.com',    'Priya Nair',    '!seed-account-no-login', 'user'),
    ('00000000-0000-4000-8000-000000000004', 'jonas.becker@example.com',  'Jonas Becker',  '!seed-account-no-login', 'user'),
    ('00000000-0000-4000-8000-000000000005', 'mei.lin@example.com',       'Mei Lin',       '!seed-account-no-login', 'user'),
    ('00000000-0000-4000-8000-000000000006', 'kwame.mensah@example.com',  'Kwame Mensah',  '!seed-account-no-login', 'user'),
    ('00000000-0000-4000-8000-000000000007', 'sofia.rossi@example.com',   'Sofia Rossi',   '!seed-account-no-login', 'user'),
    ('00000000-0000-4000-8000-000000000008', 'arjun.mehta@example.com',   'Arjun Mehta',   '!seed-account-no-login', 'user'),
    ('00000000-0000-4000-8000-000000000009', 'hana.sato@example.com',     'Hana Sato',     '!seed-account-no-login', 'user'),
    ('00000000-0000-4000-8000-000000000010', 'liam.oconnor@example.com',  'Liam O''Connor', '!seed-account-no-login', 'user')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------
-- User skills (proficiency 1-5)
-- ---------------------------------------------------------
INSERT INTO user_skills (user_id, skill_id, proficiency)
SELECT v.user_id, s.id, v.proficiency
FROM (VALUES
    ('00000000-0000-4000-8000-000000000001'::uuid, 'python', 5),
    ('00000000-0000-4000-8000-000000000001'::uuid, 'machine-learning', 4),
    ('00000000-0000-4000-8000-000000000001'::uuid, 'nlp', 4),
    ('00000000-0000-4000-8000-000000000001'::uuid, 'postgresql', 3),

    ('00000000-0000-4000-8000-000000000002'::uuid, 'typescript', 5),
    ('00000000-0000-4000-8000-000000000002'::uuid, 'react', 5),
    ('00000000-0000-4000-8000-000000000002'::uuid, 'nextjs', 4),
    ('00000000-0000-4000-8000-000000000002'::uuid, 'ui-design', 3),

    ('00000000-0000-4000-8000-000000000003'::uuid, 'python', 4),
    ('00000000-0000-4000-8000-000000000003'::uuid, 'computer-vision', 5),
    ('00000000-0000-4000-8000-000000000003'::uuid, 'machine-learning', 4),
    ('00000000-0000-4000-8000-000000000003'::uuid, 'iot', 3),

    ('00000000-0000-4000-8000-000000000004'::uuid, 'go', 5),
    ('00000000-0000-4000-8000-000000000004'::uuid, 'devops', 5),
    ('00000000-0000-4000-8000-000000000004'::uuid, 'postgresql', 4),
    ('00000000-0000-4000-8000-000000000004'::uuid, 'rust', 3),

    ('00000000-0000-4000-8000-000000000005'::uuid, 'ui-design', 5),
    ('00000000-0000-4000-8000-000000000005'::uuid, 'react', 4),
    ('00000000-0000-4000-8000-000000000005'::uuid, 'mobile', 4),
    ('00000000-0000-4000-8000-000000000005'::uuid, 'javascript', 4),

    ('00000000-0000-4000-8000-000000000006'::uuid, 'data-engineering', 5),
    ('00000000-0000-4000-8000-000000000006'::uuid, 'python', 4),
    ('00000000-0000-4000-8000-000000000006'::uuid, 'postgresql', 4),
    ('00000000-0000-4000-8000-000000000006'::uuid, 'geospatial', 4),

    ('00000000-0000-4000-8000-000000000007'::uuid, 'llm', 5),
    ('00000000-0000-4000-8000-000000000007'::uuid, 'nlp', 5),
    ('00000000-0000-4000-8000-000000000007'::uuid, 'vector-search', 4),
    ('00000000-0000-4000-8000-000000000007'::uuid, 'python', 4),

    ('00000000-0000-4000-8000-000000000008'::uuid, 'mobile', 5),
    ('00000000-0000-4000-8000-000000000008'::uuid, 'typescript', 4),
    ('00000000-0000-4000-8000-000000000008'::uuid, 'react', 4),
    ('00000000-0000-4000-8000-000000000008'::uuid, 'devops', 2),

    ('00000000-0000-4000-8000-000000000009'::uuid, 'neo4j', 4),
    ('00000000-0000-4000-8000-000000000009'::uuid, 'data-engineering', 3),
    ('00000000-0000-4000-8000-000000000009'::uuid, 'python', 3),
    ('00000000-0000-4000-8000-000000000009'::uuid, 'vector-search', 3),

    ('00000000-0000-4000-8000-000000000010'::uuid, 'rust', 5),
    ('00000000-0000-4000-8000-000000000010'::uuid, 'iot', 4),
    ('00000000-0000-4000-8000-000000000010'::uuid, 'go', 3),
    ('00000000-0000-4000-8000-000000000010'::uuid, 'devops', 3)
) AS v(user_id, skill, proficiency)
JOIN skills s ON s.name = v.skill
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------
-- User interests
-- ---------------------------------------------------------
INSERT INTO user_interests (user_id, interest_id)
SELECT v.user_id, i.id
FROM (VALUES
    ('00000000-0000-4000-8000-000000000001'::uuid, 'healthtech'),
    ('00000000-0000-4000-8000-000000000001'::uuid, 'education'),
    ('00000000-0000-4000-8000-000000000002'::uuid, 'climate'),
    ('00000000-0000-4000-8000-000000000002'::uuid, 'civic-tech'),
    ('00000000-0000-4000-8000-000000000003'::uuid, 'conservation'),
    ('00000000-0000-4000-8000-000000000003'::uuid, 'climate'),
    ('00000000-0000-4000-8000-000000000004'::uuid, 'security'),
    ('00000000-0000-4000-8000-000000000004'::uuid, 'developer-tools'),
    ('00000000-0000-4000-8000-000000000005'::uuid, 'accessibility'),
    ('00000000-0000-4000-8000-000000000005'::uuid, 'education'),
    ('00000000-0000-4000-8000-000000000006'::uuid, 'climate'),
    ('00000000-0000-4000-8000-000000000006'::uuid, 'civic-tech'),
    ('00000000-0000-4000-8000-000000000007'::uuid, 'research-tools'),
    ('00000000-0000-4000-8000-000000000007'::uuid, 'education'),
    ('00000000-0000-4000-8000-000000000008'::uuid, 'fintech-alt'),
    ('00000000-0000-4000-8000-000000000008'::uuid, 'accessibility'),
    ('00000000-0000-4000-8000-000000000009'::uuid, 'research-tools'),
    ('00000000-0000-4000-8000-000000000009'::uuid, 'developer-tools'),
    ('00000000-0000-4000-8000-000000000010'::uuid, 'conservation'),
    ('00000000-0000-4000-8000-000000000010'::uuid, 'security')
) AS v(user_id, interest)
JOIN interests i ON i.name = v.interest
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------
-- Past collaborations (same pairs as the Neo4j seed). LEAST/GREATEST put
-- each pair in canonical order (user_a < user_b).
-- ---------------------------------------------------------
INSERT INTO collaborations (user_a, user_b, project_name)
SELECT LEAST(v.a, v.b), GREATEST(v.a, v.b), v.project_name
FROM (VALUES
    ('00000000-0000-4000-8000-000000000001'::uuid, '00000000-0000-4000-8000-000000000007'::uuid, 'clinic-faq-bot'),
    ('00000000-0000-4000-8000-000000000007'::uuid, '00000000-0000-4000-8000-000000000009'::uuid, 'paper-graph-explorer'),
    ('00000000-0000-4000-8000-000000000002'::uuid, '00000000-0000-4000-8000-000000000006'::uuid, 'bike-lane-tracker'),
    ('00000000-0000-4000-8000-000000000006'::uuid, '00000000-0000-4000-8000-000000000003'::uuid, 'canopy-cover-map'),
    ('00000000-0000-4000-8000-000000000003'::uuid, '00000000-0000-4000-8000-000000000010'::uuid, 'river-sensor-net'),
    ('00000000-0000-4000-8000-000000000004'::uuid, '00000000-0000-4000-8000-000000000010'::uuid, 'edge-log-agent'),
    ('00000000-0000-4000-8000-000000000005'::uuid, '00000000-0000-4000-8000-000000000008'::uuid, 'accessible-budget-app')
) AS v(a, b, project_name)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------
-- Constraints (one row per user). Sofia (18h) and Arjun (12h) show the
-- short-timeframe penalty; Jonas and Arjun are solo builders.
-- ---------------------------------------------------------
INSERT INTO constraints (user_id, team_size, timeframe_hours, preferred_stack) VALUES
    ('00000000-0000-4000-8000-000000000001', 3, 48, ARRAY['python', 'postgresql']),
    ('00000000-0000-4000-8000-000000000002', 2, 36, ARRAY['nextjs', 'typescript']),
    ('00000000-0000-4000-8000-000000000003', 4, 48, ARRAY['python']),
    ('00000000-0000-4000-8000-000000000004', 1, 24, ARRAY['go']),
    ('00000000-0000-4000-8000-000000000005', 3, 48, ARRAY['react']),
    ('00000000-0000-4000-8000-000000000006', 2, 72, ARRAY['python', 'postgresql']),
    ('00000000-0000-4000-8000-000000000007', 2, 18, ARRAY['python']),
    ('00000000-0000-4000-8000-000000000008', 1, 12, ARRAY['react-native']),
    ('00000000-0000-4000-8000-000000000009', 3, 48, ARRAY['python', 'neo4j']),
    ('00000000-0000-4000-8000-000000000010', 2, 48, ARRAY['rust'])
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------
-- Ingestion sources
-- ---------------------------------------------------------
-- ingestion_sources has no natural unique key, so guard with NOT EXISTS.
INSERT INTO ingestion_sources (source_type, config, created_by)
SELECT v.source_type, v.config::jsonb, '00000000-0000-4000-8000-000000000001'::uuid
FROM (VALUES
    ('github', '{"labels": ["help wanted", "good first issue"], "min_reactions": 5}'),
    ('arxiv',  '{"categories": ["cs.CV", "cs.CL", "cs.LG", "cs.HC"], "max_results": 200}'),
    ('hn',     '{"story_types": ["ask_hn", "show_hn"], "min_points": 20}')
) AS v(source_type, config)
WHERE NOT EXISTS (SELECT 1 FROM ingestion_sources s WHERE s.source_type = v.source_type);

-- ---------------------------------------------------------
-- Problem signals
-- ---------------------------------------------------------
INSERT INTO problem_signals (source, external_id, title, raw_text, category_tags, published_at) VALUES
    -- GitHub issues
    ('github', 'seed-gh-001',
     'Screen reader announces chart data points in the wrong order',
     'VoiceOver and NVDA read line-chart points right-to-left after the latest release. Users who rely on screen readers cannot follow trends in the dashboard.',
     ARRAY['accessibility'], now() - INTERVAL '3 days'),
    ('github', 'seed-gh-002',
     'Add offline mode for field data collection app',
     'Rangers lose survey entries when they walk out of coverage. Need local-first storage with background sync and conflict handling when the device reconnects.',
     ARRAY['conservation'], now() - INTERVAL '5 days'),
    ('github', 'seed-gh-003',
     'Air-quality sensor readings drift after firmware update',
     'PM2.5 values from low-cost sensors read 20-30% high after v2.4. We need a calibration pipeline against reference stations before data is published.',
     ARRAY['climate'], now() - INTERVAL '2 days'),
    ('github', 'seed-gh-004',
     'Similarity search slows down once the embeddings table passes 1M rows',
     'Nearest-neighbour queries go from 20 ms to 4 s. Looking for guidance on index choice, filtering, and how to benchmark recall vs. latency.',
     ARRAY['developer-tools'], now() - INTERVAL '1 day'),
    ('github', 'seed-gh-005',
     'Camera-trap images need automatic species pre-labeling',
     'Volunteers hand-label ~40k images per season. A model that pre-labels common species and flags empty frames would cut review time dramatically.',
     ARRAY['conservation'], now() - INTERVAL '8 days'),
    ('github', 'seed-gh-006',
     'Clinic appointment reminders fail for patients without smartphones',
     'Reminder service only supports push notifications. Many patients only have feature phones; we need an SMS fallback with opt-out handling.',
     ARRAY['healthtech'], now() - INTERVAL '6 days'),
    ('github', 'seed-gh-007',
     'Dependency audit CLI flags false positives on vendored packages',
     'The scanner treats vendored copies as separate dependencies and reports CVEs that were already patched upstream. Need smarter provenance detection.',
     ARRAY['security', 'developer-tools'], now() - INTERVAL '4 days'),
    ('github', 'seed-gh-008',
     'Transit open-data parser crashes on GTFS-realtime extensions',
     'City feeds include vendor-specific extensions that crash the parser. Riders see no live arrivals when this happens.',
     ARRAY['civic-tech'], now() - INTERVAL '10 days'),
    ('github', 'seed-gh-009',
     'Keyboard navigation trap in date picker component',
     'Tabbing into the date picker never lets focus leave. Fails WCAG 2.1.2 and blocks keyboard-only users from completing the form.',
     ARRAY['accessibility'], now() - INTERVAL '50 days'),
    ('github', 'seed-gh-010',
     'Categorize bank transactions from CSV exports',
     'Budgeting app users import CSVs from dozens of banks with inconsistent descriptions. Rule-based categorization misses most merchants.',
     ARRAY['fintech-alt'], now() - INTERVAL '7 days'),
    ('github', 'seed-gh-011',
     'Auto-generate captions for recorded lectures',
     'Course platform hosts 3,000+ lecture videos without captions. Need an automated pipeline with a quick human review step.',
     ARRAY['education', 'accessibility'], now() - INTERVAL '9 days'),
    ('github', 'seed-gh-012',
     'Rewrite hot path of log shipper to cut memory use',
     'The shipper uses 1.2 GB RSS on busy hosts. Profiling points at the parsing loop; a Rust rewrite of that module is proposed.',
     ARRAY['developer-tools'], now() - INTERVAL '12 days'),
    ('github', 'seed-gh-013',
     'Flood-risk map tiles render too slowly on mobile browsers',
     'Residents check flood maps on phones during storms, but vector tiles take 15+ s to render on mid-range devices.',
     ARRAY['climate', 'civic-tech'], now() - INTERVAL '3 days'),

    -- arXiv abstracts
    ('arxiv', 'seed-ax-001',
     'Few-shot detection of illegal logging from Sentinel-2 imagery',
     'We study detecting small-scale clearings with few labelled examples. Existing models need thousands of labels per region, which conservation groups rarely have.',
     ARRAY['conservation', 'climate'], now() - INTERVAL '4 days'),
    ('arxiv', 'seed-ax-002',
     'Retrieval-augmented generation for clinical guideline question answering',
     'Clinicians need answers grounded in current guidelines. We evaluate retrieval strategies and find citation accuracy remains the main failure mode.',
     ARRAY['healthtech'], now() - INTERVAL '2 days'),
    ('arxiv', 'seed-ax-003',
     'Evaluating LLM tutors on misconception diagnosis in algebra',
     'LLM tutors often give correct answers but miss the student''s underlying misconception. We release a benchmark of annotated student errors.',
     ARRAY['education'], now() - INTERVAL '6 days'),
    ('arxiv', 'seed-ax-004',
     'Graph neural networks for detecting money-mule accounts',
     'Mule accounts are hard to spot individually but form distinctive transaction subgraphs. We compare GNN architectures on a synthetic banking graph.',
     ARRAY['fintech-alt', 'security'], now() - INTERVAL '11 days'),
    ('arxiv', 'seed-ax-005',
     'Energy-efficient on-device keyword spotting for low-cost hearing aids',
     'We target microcontrollers with under 256 KB RAM. Current models drain batteries in hours, which makes them impractical for daily hearing-aid use.',
     ARRAY['healthtech', 'accessibility'], now() - INTERVAL '9 days'),
    ('arxiv', 'seed-ax-006',
     'Citation-intent classification for literature-review tooling',
     'Knowing whether a paper is cited as background, method, or contrast would speed up reviews. Existing classifiers transfer poorly across fields.',
     ARRAY['research-tools'], now() - INTERVAL '13 days'),
    ('arxiv', 'seed-ax-007',
     'Benchmarking approximate nearest-neighbour indexes under filtered queries',
     'Most ANN benchmarks ignore metadata filters. With selective filters, recall of graph-based indexes drops sharply unless search is made filter-aware.',
     ARRAY['research-tools', 'developer-tools'], now() - INTERVAL '5 days'),
    ('arxiv', 'seed-ax-008',
     'Estimating rooftop solar potential from aerial imagery and LiDAR',
     'We combine roof segmentation with elevation data to estimate per-building solar yield. Municipal planners lack tools to do this at city scale.',
     ARRAY['climate'], now() - INTERVAL '75 days'),
    ('arxiv', 'seed-ax-009',
     'Sign-language recognition from monocular video with pose estimation',
     'Pose-based models run on phones but struggle with fingerspelling. We show where current pipelines fail and release a fingerspelling test set.',
     ARRAY['accessibility'], now() - INTERVAL '8 days'),

    -- Hacker News posts
    ('hn', 'seed-hn-001',
     'Ask HN: How do you keep track of which grants your lab applied to?',
     'Our lab tracks grant applications, deadlines, and reviewer feedback across spreadsheets and email. Is there anything better than a shared sheet?',
     ARRAY['research-tools'], now() - INTERVAL '1 day'),
    ('hn', 'seed-hn-002',
     'Show HN: I mapped every public water fountain in my city — now what?',
     'Built the dataset over a summer. People ask for a mobile map with "working / broken" reports, but I have no idea how to keep it up to date.',
     ARRAY['civic-tech'], now() - INTERVAL '4 days'),
    ('hn', 'seed-hn-003',
     'Ask HN: Tools for small nonprofits to manage volunteer schedules?',
     'We coordinate 80 volunteers with a group chat and a calendar. Commercial tools are priced for companies. What do other small orgs use?',
     ARRAY['civic-tech'], now() - INTERVAL '7 days'),
    ('hn', 'seed-hn-004',
     'Our hospital still faxes discharge summaries — is there a better way?',
     'Discharge summaries go to GPs by fax and get re-typed. Interop standards exist, but nobody has built something small clinics can actually deploy.',
     ARRAY['healthtech'], now() - INTERVAL '10 days'),
    ('hn', 'seed-hn-005',
     'Ask HN: Self-hosted password manager for a non-technical family?',
     'I want my parents off sticky notes, but every self-hosted option assumes you are comfortable with Docker and reverse proxies.',
     ARRAY['security'], now() - INTERVAL '3 days'),
    ('hn', 'seed-hn-006',
     'Show HN: Tracking microplastics in local rivers with $30 sensors',
     'Prototype works on the bench. Struggling with power, waterproofing, and getting readings back from remote sites reliably.',
     ARRAY['conservation', 'climate'], now() - INTERVAL '6 days'),
    ('hn', 'seed-hn-007',
     'Ask HN: Why is there no good open-source app for splitting rent fairly?',
     'Room sizes, shared spaces, and income differences make even splits feel unfair. Existing apps only handle equal or fixed splits.',
     ARRAY['fintech-alt'], now() - INTERVAL '2 days'),
    ('hn', 'seed-hn-008',
     'Teachers are drowning in grading — anyone automating essay feedback?',
     'I teach 150 students. Rubric-aligned first-pass feedback would give me time for the comments that actually need a human.',
     ARRAY['education'], now() - INTERVAL '5 days'),
    ('hn', 'seed-hn-009',
     'Ask HN: Best way to visualize a codebase''s dependency graph?',
     'Onboarding engineers get lost in our monorepo. Static diagrams go stale immediately; we want something queryable and interactive.',
     ARRAY['developer-tools'], now() - INTERVAL '40 days')
ON CONFLICT (source, external_id) DO NOTHING;

-- ---------------------------------------------------------
-- Signal skills (confidence 0..1 that the signal needs the skill)
-- ---------------------------------------------------------
INSERT INTO signal_skills (signal_id, skill_id, confidence)
SELECT ps.id, s.id, v.confidence
FROM (VALUES
    ('github', 'seed-gh-001', 'react', 0.9),
    ('github', 'seed-gh-001', 'javascript', 0.8),
    ('github', 'seed-gh-001', 'ui-design', 0.6),
    ('github', 'seed-gh-002', 'mobile', 0.9),
    ('github', 'seed-gh-002', 'typescript', 0.7),
    ('github', 'seed-gh-002', 'postgresql', 0.5),
    ('github', 'seed-gh-003', 'iot', 0.9),
    ('github', 'seed-gh-003', 'python', 0.7),
    ('github', 'seed-gh-003', 'data-engineering', 0.6),
    ('github', 'seed-gh-004', 'postgresql', 0.9),
    ('github', 'seed-gh-004', 'vector-search', 0.9),
    ('github', 'seed-gh-005', 'computer-vision', 0.95),
    ('github', 'seed-gh-005', 'python', 0.8),
    ('github', 'seed-gh-005', 'machine-learning', 0.7),
    ('github', 'seed-gh-006', 'python', 0.7),
    ('github', 'seed-gh-006', 'devops', 0.5),
    ('github', 'seed-gh-007', 'go', 0.9),
    ('github', 'seed-gh-007', 'devops', 0.6),
    ('github', 'seed-gh-008', 'python', 0.8),
    ('github', 'seed-gh-008', 'data-engineering', 0.8),
    ('github', 'seed-gh-008', 'geospatial', 0.6),
    ('github', 'seed-gh-009', 'react', 0.9),
    ('github', 'seed-gh-009', 'typescript', 0.7),
    ('github', 'seed-gh-010', 'python', 0.7),
    ('github', 'seed-gh-010', 'machine-learning', 0.6),
    ('github', 'seed-gh-010', 'nextjs', 0.5),
    ('github', 'seed-gh-011', 'nlp', 0.7),
    ('github', 'seed-gh-011', 'python', 0.7),
    ('github', 'seed-gh-011', 'machine-learning', 0.6),
    ('github', 'seed-gh-012', 'rust', 0.95),
    ('github', 'seed-gh-012', 'devops', 0.5),
    ('github', 'seed-gh-013', 'geospatial', 0.9),
    ('github', 'seed-gh-013', 'javascript', 0.7),
    ('github', 'seed-gh-013', 'mobile', 0.5),

    ('arxiv', 'seed-ax-001', 'computer-vision', 0.9),
    ('arxiv', 'seed-ax-001', 'machine-learning', 0.9),
    ('arxiv', 'seed-ax-001', 'geospatial', 0.7),
    ('arxiv', 'seed-ax-002', 'llm', 0.9),
    ('arxiv', 'seed-ax-002', 'nlp', 0.8),
    ('arxiv', 'seed-ax-002', 'vector-search', 0.8),
    ('arxiv', 'seed-ax-003', 'llm', 0.9),
    ('arxiv', 'seed-ax-003', 'nlp', 0.7),
    ('arxiv', 'seed-ax-004', 'machine-learning', 0.9),
    ('arxiv', 'seed-ax-004', 'python', 0.7),
    ('arxiv', 'seed-ax-004', 'neo4j', 0.6),
    ('arxiv', 'seed-ax-005', 'machine-learning', 0.8),
    ('arxiv', 'seed-ax-005', 'iot', 0.8),
    ('arxiv', 'seed-ax-005', 'rust', 0.4),
    ('arxiv', 'seed-ax-006', 'nlp', 0.9),
    ('arxiv', 'seed-ax-006', 'python', 0.7),
    ('arxiv', 'seed-ax-007', 'vector-search', 0.95),
    ('arxiv', 'seed-ax-007', 'postgresql', 0.6),
    ('arxiv', 'seed-ax-008', 'computer-vision', 0.8),
    ('arxiv', 'seed-ax-008', 'geospatial', 0.9),
    ('arxiv', 'seed-ax-008', 'python', 0.6),
    ('arxiv', 'seed-ax-009', 'computer-vision', 0.9),
    ('arxiv', 'seed-ax-009', 'machine-learning', 0.8),
    ('arxiv', 'seed-ax-009', 'mobile', 0.4),

    ('hn', 'seed-hn-001', 'nextjs', 0.6),
    ('hn', 'seed-hn-001', 'postgresql', 0.6),
    ('hn', 'seed-hn-001', 'ui-design', 0.5),
    ('hn', 'seed-hn-002', 'geospatial', 0.8),
    ('hn', 'seed-hn-002', 'mobile', 0.6),
    ('hn', 'seed-hn-002', 'react', 0.5),
    ('hn', 'seed-hn-003', 'nextjs', 0.7),
    ('hn', 'seed-hn-003', 'typescript', 0.7),
    ('hn', 'seed-hn-003', 'postgresql', 0.6),
    ('hn', 'seed-hn-004', 'data-engineering', 0.6),
    ('hn', 'seed-hn-004', 'python', 0.6),
    ('hn', 'seed-hn-004', 'devops', 0.5),
    ('hn', 'seed-hn-005', 'go', 0.6),
    ('hn', 'seed-hn-005', 'devops', 0.6),
    ('hn', 'seed-hn-005', 'ui-design', 0.6),
    ('hn', 'seed-hn-006', 'iot', 0.9),
    ('hn', 'seed-hn-006', 'data-engineering', 0.5),
    ('hn', 'seed-hn-007', 'mobile', 0.7),
    ('hn', 'seed-hn-007', 'react', 0.6),
    ('hn', 'seed-hn-007', 'typescript', 0.6),
    ('hn', 'seed-hn-008', 'llm', 0.8),
    ('hn', 'seed-hn-008', 'nlp', 0.8),
    ('hn', 'seed-hn-008', 'nextjs', 0.4),
    ('hn', 'seed-hn-009', 'neo4j', 0.8),
    ('hn', 'seed-hn-009', 'typescript', 0.6),
    ('hn', 'seed-hn-009', 'ui-design', 0.5)
) AS v(source, external_id, skill, confidence)
JOIN problem_signals ps ON ps.source = v.source AND ps.external_id = v.external_id
JOIN skills s ON s.name = v.skill
ON CONFLICT DO NOTHING;

COMMIT;

-- Populate the trending view with the seeded signals.
REFRESH MATERIALIZED VIEW trending_problem_areas;
