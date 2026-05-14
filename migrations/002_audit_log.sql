-- Sprint 6 — audit_log table for compliance + security tracing.
-- Run in Supabase → SQL Editor. Safe: IF NOT EXISTS (no-op if already applied).

CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    action          TEXT        NOT NULL,
    chat_id         BIGINT,
    before_state    JSONB,
    after_state     JSONB,
    metadata        JSONB
);

CREATE INDEX IF NOT EXISTS idx_audit_log_ts     ON audit_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log (action);
CREATE INDEX IF NOT EXISTS idx_audit_log_chat   ON audit_log (chat_id);

-- Verify
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'audit_log'
ORDER BY ordinal_position;
