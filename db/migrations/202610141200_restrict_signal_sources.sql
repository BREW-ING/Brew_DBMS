-- =========================================================
-- Restrict signal sources to GitHub, arXiv, and Hacker News.
-- Renames 'news' -> 'hn' and removes 'reddit'.
-- =========================================================
BEGIN;

-- Drop the inline CHECK constraints from the initial schema
-- (Postgres default names: <table>_<column>_check).
ALTER TABLE ingestion_sources DROP CONSTRAINT IF EXISTS ingestion_sources_source_type_check;
ALTER TABLE problem_signals   DROP CONSTRAINT IF EXISTS problem_signals_source_check;

-- Migrate existing rows
UPDATE ingestion_sources SET source_type = 'hn' WHERE source_type = 'news';
UPDATE problem_signals   SET source      = 'hn' WHERE source      = 'news';

DELETE FROM ingestion_sources WHERE source_type = 'reddit';
DELETE FROM problem_signals   WHERE source      = 'reddit';   -- cascades to suggestions/feedback

-- Re-add constraints with the new source set
ALTER TABLE ingestion_sources
    ADD CONSTRAINT ingestion_sources_source_type_check
    CHECK (source_type IN ('github', 'arxiv', 'hn'));

ALTER TABLE problem_signals
    ADD CONSTRAINT problem_signals_source_check
    CHECK (source IN ('github', 'arxiv', 'hn'));

COMMENT ON COLUMN ingestion_sources.config IS 'Source-specific settings, e.g. repo filters or arXiv categories';

COMMIT;
