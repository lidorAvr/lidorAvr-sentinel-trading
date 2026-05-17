-- Phase A — add user_id to trades.
-- Run in Supabase → SQL Editor. Safe: IF NOT EXISTS (no-op if already applied).
-- Additive, default-backed, reversible. Backfills every existing row to the
-- DEFAULT_USER_ID sentinel so that Mark's data is owned by a real user UUID.

-- 1. Forward DDL
ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS user_id UUID
    NOT NULL
    DEFAULT '00000000-0000-0000-0000-000000000001';

-- 2. Backfill (no-op if column was just added with DEFAULT — every row already
--    has the default value; this is a belt-and-suspenders guard for the case
--    where the column existed before this migration applied).
UPDATE trades
SET    user_id = '00000000-0000-0000-0000-000000000001'
WHERE  user_id IS NULL;

-- 3. Index (cheap on small tables; required once we filter by user_id).
CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades (user_id);

-- 4. Verify
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'trades'
  AND column_name = 'user_id';

-- 5. Verification (must return 0)
SELECT COUNT(*) AS null_user_id_rows FROM trades WHERE user_id IS NULL;
-- Expected output: 0

-- 6. Verification (must return >= 1 with the sentinel UUID)
SELECT COUNT(*) AS sentinel_owned_rows
FROM   trades
WHERE  user_id = '00000000-0000-0000-0000-000000000001';
-- Expected output: equal to total row count of trades pre-migration.

-- ── Reverse DDL (safe — column has DEFAULT, no FK constraints in Phase A) ──────
-- To roll back, run the two statements below (also in rollback_003.sql):
--   DROP INDEX IF EXISTS idx_trades_user_id;
--   ALTER TABLE trades DROP COLUMN IF EXISTS user_id;
