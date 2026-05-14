-- 003_trade_entry_snapshots.sql
-- 2026-05-14 — Snapshot per-trade the risk_pct and NAV that were active at
-- insert time. Needed so the dashboard / portfolio room can compute the
-- ORIGINAL campaign target (the one in effect when the trade was opened),
-- not the moving CURRENT target that drifts every time the user changes
-- their adaptive risk setting.
--
-- See docs/IBKR_CONFIG_REFERENCE.md and the 2026-05-14 session feedback
-- ("בקרת קמפיין: סיכון נמוך ($23 מול יעד $48) — בעניין זה בזמן פתיחת הטרייד
-- הסיכון בפועל היה 0.35% שזה ... $30 אבל עכשיו ... זה מראה $48 זה מבלבל.").
--
-- Both columns are NULLABLE — pre-migration trades have NULL and the
-- display falls back to the current target with an "(approx)" tag.
-- Newly imported trades get populated at insert time by
-- ibkr_trade_importer.parse_trades_from_xml() reading
-- /app/sentinel_config.json.

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS risk_pct_at_entry numeric,
    ADD COLUMN IF NOT EXISTS nav_at_entry      numeric;

-- No index needed: these columns are only read on the SAME row queries
-- already exercise (trade_id / campaign_id), never as filter keys.

-- Idempotent (IF NOT EXISTS). Safe to re-run.
