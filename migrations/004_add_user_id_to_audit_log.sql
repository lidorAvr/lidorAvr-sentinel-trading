-- Phase A — add user_id to audit_log.
-- Run in Supabase → SQL Editor. Safe: IF NOT EXISTS (no-op if already applied).
-- audit_log today has chat_id BIGINT but no user_id (see migrations/002_audit_log.sql:7).
-- chat_id is the only proxy for "who did this" — fine for single-user, ambiguous later.

-- 1. Forward DDL
ALTER TABLE audit_log
    ADD COLUMN IF NOT EXISTS user_id UUID
    NOT NULL
    DEFAULT '00000000-0000-0000-0000-000000000001';

-- 2. Backfill
UPDATE audit_log
SET    user_id = '00000000-0000-0000-0000-000000000001'
WHERE  user_id IS NULL;

-- 3. Index
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log (user_id);

-- 4. Verify
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'audit_log'
  AND column_name = 'user_id';

-- 5. Verification (must return 0)
SELECT COUNT(*) AS null_user_id_rows FROM audit_log WHERE user_id IS NULL;
-- Expected output: 0

-- ── Reverse DDL (safe — column has DEFAULT, no FK constraints in Phase A) ──────
-- To roll back, run the two statements below (also in rollback_004.sql):
--   DROP INDEX IF EXISTS idx_audit_log_user_id;
--   ALTER TABLE audit_log DROP COLUMN IF EXISTS user_id;
