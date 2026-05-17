-- Sprint 10 rollback — remove the open_tasks table.
-- DRAFT — authored by the Architecture team. NOT executed against any database.
-- Run in Supabase → SQL Editor. Safe: IF EXISTS (no-op if already rolled back).
-- Reverse of 005_create_open_tasks.sql. Safe — additive table, no FK
-- constraints in Phase A, so no other app data is lost. The Open Tasks engine
-- re-derives all *open* tasks from engine_core; dropping this table only
-- discards stored done/skip/notes lifecycle deltas.

DROP INDEX IF EXISTS idx_open_tasks_user_campaign_type;
DROP INDEX IF EXISTS idx_open_tasks_user_id;
DROP INDEX IF EXISTS idx_open_tasks_campaign;
DROP TABLE IF EXISTS open_tasks;

-- Verify (must return 0 rows — table is gone)
SELECT table_name
FROM information_schema.tables
WHERE table_name = 'open_tasks';
</content>
