-- =========================================================
-- Staleness window: 30 days -> 180 days
-- =========================================================
-- Sources are backfilled well past 30 days (HN goes back 365), so a 30-day
-- window left only a small fraction of embedded signals eligible for
-- suggestions. A signal is now stale once COALESCE(published_at, fetched_at)
-- is more than 180 days old.
--
-- Function signatures are unchanged, so trg_set_signal_staleness and
-- trg_sweep_stale_signals keep pointing at them. The partial index
-- idx_problem_signals_stale_candidates is keyed on the date expression, not
-- the cutoff, so it needs no change.

BEGIN;

CREATE OR REPLACE FUNCTION expire_stale_signals() RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INTEGER;
BEGIN
    UPDATE problem_signals
    SET is_stale = true
    WHERE is_stale = false
      AND COALESCE(published_at, fetched_at) < now() - INTERVAL '180 days';
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION set_signal_staleness() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF COALESCE(NEW.published_at, NEW.fetched_at) < now() - INTERVAL '180 days' THEN
        NEW.is_stale := true;
    END IF;
    RETURN NEW;
END;
$$;

-- One-off exception to "staleness is one-way": un-stale the rows the old
-- 30-day rule would have marked (aged 30-180 days). A stale row younger than
-- 30 days can only have been retired by hand, so those stay retired. Hand-
-- retired rows aged 30-180 days can't be told apart from auto-staled ones.
-- Updating is_stale doesn't fire trg_set_signal_staleness (it fires only on
-- writes to published_at / fetched_at).
UPDATE problem_signals
SET is_stale = false
WHERE is_stale
  AND COALESCE(published_at, fetched_at) >= now() - INTERVAL '180 days'
  AND COALESCE(published_at, fetched_at) <  now() - INTERVAL '30 days';

COMMIT;

-- The trending view filters on is_stale, so rebuild it with the un-staled rows.
REFRESH MATERIALIZED VIEW CONCURRENTLY trending_problem_areas;
