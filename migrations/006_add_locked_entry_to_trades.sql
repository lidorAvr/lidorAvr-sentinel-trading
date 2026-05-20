-- RISK-1a — at-entry locked-immutable price columns on trades.
-- Run in Supabase → SQL Editor. Safe to re-run: IF NOT EXISTS (no-op if already applied).
--
-- Adds the locked-at-entry price that becomes the canonical anchor for planned-risk
-- math going forward. The legacy `price` column stays untouched (still the broker
-- fill record); `locked_entry_price` is the immutable at-entry reference that the
-- new RISK-1d formatter reads for live displays. Empty (NULL) until populated by:
--   - RISK-1b wizard (forward capture, at trade-entry time, lock_method='wizard')
--   - RISK-1c legacy backfill (admin operator, lock_method='backfill')
--   - RISK-1d admin correction (/at_entry_correct, lock_method='admin_correction')
--
-- LOCKED-April safety: this migration touches schema only. The April fixture's
-- analytics_engine path reads `price`/`pnl_usd` — not these new columns — so byte-
-- identical April reconciliation (DEC-019/-020; PF 2.6262 / WR .375 / 8 / +$180.49)
-- is preserved by construction. The new columns are NULL on every existing row;
-- any caller that reads them must handle NULL explicitly (the RISK-1d formatter's
-- mode='live' path; mode='historical' default ignores them).
--
-- Follows the migration 003 template exactly: additive, IF NOT EXISTS, no FK
-- constraints, fully reversible via rollback_006.sql.

-- 1. Forward DDL — 4 NULL-additive columns.
ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS locked_entry_price NUMERIC(12, 4);
-- ^ NUMERIC(12,4) matches the precision of broker average-fill reports (4 decimals;
--   e.g. 87.4321). Wider than `price` would need to be — chosen deliberately so a
--   broker-side avg-fill with 4-decimal precision does NOT round-trip through cent
--   rounding when locked. The R-denominator round(..., 2) in
--   engine_core.compute_original_campaign_risk (DATA_CONTRACTS.md F7) is a SEPARATE
--   downstream rounding that stays untouched.

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS locked_entry_at TIMESTAMPTZ;
-- ^ NULL until lock occurs. The wizard / backfill / admin-correction helpers set
--   this to `now()`-equivalent ISO timestamp at write time (NOT a column DEFAULT —
--   we need lock-time, not row-insert-time).

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS lock_source TEXT;
-- ^ WHERE the locked value came from. Application-layer values:
--     'broker_avg_fill'  — from broker average-fill report (wizard happy path)
--     'reuters_open'     — fallback when broker fill missing (backfill flow)
--     'declared_by_user' — admin correction with founder-supplied price
--     'unknown'          — backfill with no derivable source (banner-flagged)
--   No CHECK constraint — application layer validates. Free TEXT keeps Phase A
--   flexible (CLAUDE.md preferred-refactor: extract gradually, no premature DDL
--   lock-in).

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS lock_method TEXT;
-- ^ HOW the lock was set. Application-layer values:
--     'wizard'            — RISK-1b forward capture at trade-entry
--     'backfill'          — RISK-1c admin backfill of legacy positions
--     'admin_correction'  — RISK-1d /at_entry_correct admin command
--   Companion to lock_source; together they form the audit trail visible in the
--   dashboard banner and audit_log rows.

-- 2. No backfill — every existing row stays NULL until the explicit backfill
--    phase (RISK-1c) runs against it. NULL is the legitimate "not-yet-locked"
--    sentinel; the RISK-1d formatter mode='live' reads it as "fall back to
--    legacy display + show 'not yet locked' banner".

-- 3. No index in RISK-1a — no query pattern (yet) filters by lock_source /
--    lock_method or sorts by locked_entry_price. The
--    `get_trades_missing_lock` helper does an in-Python NULL filter on a full
--    BUY-row fetch (prod scale <500 trades, admin-only path). RISK-1c may add
--    a partial index `WHERE locked_entry_price IS NULL` if the backfill batch
--    grows large.

-- 4. Verify (schema)
SELECT column_name, data_type, is_nullable, column_default
FROM   information_schema.columns
WHERE  table_name = 'trades'
  AND  column_name IN ('locked_entry_price', 'locked_entry_at',
                       'lock_source', 'lock_method')
ORDER  BY column_name;
-- Expected: 4 rows, all is_nullable = 'YES', all column_default = NULL.

-- 5. Verification (must return total trades row count — every row is NULL pre-backfill)
SELECT COUNT(*) AS unlocked_rows
FROM   trades
WHERE  locked_entry_price IS NULL;
-- Expected output: equal to total row count of trades pre-migration.

-- ── Reverse DDL (safe — additive columns, no FK constraints) ──────────────────
-- To roll back, run the statements in rollback_006.sql:
--   ALTER TABLE trades DROP COLUMN IF EXISTS lock_method;
--   ALTER TABLE trades DROP COLUMN IF EXISTS lock_source;
--   ALTER TABLE trades DROP COLUMN IF EXISTS locked_entry_at;
--   ALTER TABLE trades DROP COLUMN IF EXISTS locked_entry_price;
