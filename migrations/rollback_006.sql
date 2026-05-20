-- RISK-1a rollback — remove the at-entry locked-immutable price columns.
-- Run in Supabase → SQL Editor. Safe: IF EXISTS (no-op if already rolled back).
-- Reverse of 006_add_locked_entry_to_trades.sql. Safe — additive columns, no FK
-- constraints, no other app data lost. Any locked-entry rows already populated
-- by RISK-1b/1c/1d are dropped with the columns; that's the intended rollback
-- semantics (forward-capture data is regenerable from the next-trade wizards;
-- backfill data is regenerable from broker reports + Reuters).
--
-- Drop order is the reverse of create order — companion columns last.

ALTER TABLE trades DROP COLUMN IF EXISTS lock_method;
ALTER TABLE trades DROP COLUMN IF EXISTS lock_source;
ALTER TABLE trades DROP COLUMN IF EXISTS locked_entry_at;
ALTER TABLE trades DROP COLUMN IF EXISTS locked_entry_price;

-- Verify (must return 0 rows — columns are gone)
SELECT column_name
FROM   information_schema.columns
WHERE  table_name = 'trades'
  AND  column_name IN ('locked_entry_price', 'locked_entry_at',
                       'lock_source', 'lock_method');
-- Expected output: 0 rows.
