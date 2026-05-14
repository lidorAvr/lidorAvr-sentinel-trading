-- Sprint 5 — Add-On Phase 2a: addon tracking columns
-- Run in Supabase → SQL Editor. Safe: IF NOT EXISTS (no-op if already applied).

ALTER TABLE trades ADD COLUMN IF NOT EXISTS is_addon BOOLEAN DEFAULT false;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS base_campaign_lot_id UUID;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS addon_sequence INT DEFAULT 1;

-- Verify
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'trades'
  AND column_name IN ('is_addon', 'base_campaign_lot_id', 'addon_sequence');
