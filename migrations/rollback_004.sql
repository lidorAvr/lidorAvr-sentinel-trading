-- Phase A rollback — remove user_id from audit_log.
-- Run in Supabase → SQL Editor. Safe: IF EXISTS (no-op if already rolled back).
-- Reverse of 004_add_user_id_to_audit_log.sql. Safe — column has DEFAULT, no FK
-- constraints in Phase A, so no app data is lost.

DROP INDEX IF EXISTS idx_audit_log_user_id;
ALTER TABLE audit_log DROP COLUMN IF EXISTS user_id;

-- Verify (must return 0 rows — column is gone)
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'audit_log'
  AND column_name = 'user_id';
