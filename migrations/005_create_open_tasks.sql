-- Sprint 10 — open_tasks table for the Action-Items (Open Tasks) engine.
-- DRAFT — authored by the Architecture team. NOT executed against any database.
-- Run in Supabase → SQL Editor. Safe: IF NOT EXISTS (no-op if already applied).
--
-- Stores LIFECYCLE DELTAS ONLY (done / skipped / user notes). The set of *open*
-- tasks is always re-derived from engine_core.compute_position_state(), so the
-- engine stays the single source of truth and this table cannot drift.
--
-- Follows the migration 003 user_id pattern exactly: additive UUID column,
-- NOT NULL, DEFAULT sentinel '00000000-0000-0000-0000-000000000001', dedicated
-- index. Single-user (Phase A) behaviour is byte-identical: every row's
-- user_id is the sentinel.

-- 1. Forward DDL
CREATE TABLE IF NOT EXISTS open_tasks (
    id                BIGSERIAL PRIMARY KEY,
    user_id           UUID NOT NULL
                      DEFAULT '00000000-0000-0000-0000-000000000001',
    campaign_id       TEXT        NOT NULL,
    task_type         TEXT        NOT NULL,
    status            TEXT        NOT NULL,   -- 'done' | 'skipped'
    symbol            TEXT,
    urgency           TEXT,                   -- 'P0' | 'P1' | 'P2' | 'P3'
    trigger_state     TEXT,                   -- engine_core.POSITION_STATE_* snapshot
    trigger_open_r    DOUBLE PRECISION,       -- snapshot only — never authoritative
    trigger_age_days  DOUBLE PRECISION,       -- snapshot only — never authoritative
    notes             JSONB       NOT NULL DEFAULT '[]'::jsonb,
    created_ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_ts         TIMESTAMPTZ
);

-- 2. Dedup constraint — at most ONE lifecycle row per task.
--    Makes mark_done / skip upserts idempotent and race-safe (a double-tap
--    from a Telegram retry is a no-op upsert, not a duplicate row).
CREATE UNIQUE INDEX IF NOT EXISTS idx_open_tasks_user_campaign_type
    ON open_tasks (user_id, campaign_id, task_type);

-- 3. Lookup indexes (cheap on small tables; required once we filter by user).
CREATE INDEX IF NOT EXISTS idx_open_tasks_user_id   ON open_tasks (user_id);
CREATE INDEX IF NOT EXISTS idx_open_tasks_campaign  ON open_tasks (campaign_id);

-- 4. Verify (schema)
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'open_tasks'
ORDER BY ordinal_position;

-- 5. Verification (must return 0 — no row may exist without the sentinel/user)
SELECT COUNT(*) AS null_user_id_rows FROM open_tasks WHERE user_id IS NULL;
-- Expected output: 0

-- ── Reverse DDL (safe — additive table, no FK constraints in Phase A) ─────────
-- To roll back, run the statements in rollback_005.sql:
--   DROP INDEX IF EXISTS idx_open_tasks_user_campaign_type;
--   DROP INDEX IF EXISTS idx_open_tasks_user_id;
--   DROP INDEX IF EXISTS idx_open_tasks_campaign;
--   DROP TABLE IF EXISTS open_tasks;
</content>
