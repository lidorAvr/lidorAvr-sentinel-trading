-- Phase A rollback — remove user_id from trades.
-- Run in Supabase → SQL Editor. Safe: IF EXISTS (no-op if already rolled back).
-- Reverse of 003_add_user_id_to_trades.sql. Safe — column has DEFAULT, no FK
-- constraints in Phase A, so no app data is lost.

DROP INDEX IF EXISTS idx_trades_user_id;
ALTER TABLE trades DROP COLUMN IF EXISTS user_id;

-- Verify (must return 0 rows — column is gone)
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'trades'
  AND column_name = 'user_id';
