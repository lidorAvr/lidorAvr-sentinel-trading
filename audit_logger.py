"""
audit_logger.py — write-only compliance trail.

Records state-changing actions to Supabase `audit_log` (migration 002). Reads
are intentionally not exposed here — the table is queried directly via
Supabase for forensic investigation; the application layer never needs to
read its own audit trail.

Design rules:
  - Fail-open. Never raise from log_action(); never block business logic.
    A missing audit row is better than a refused user action.
  - Dependency-injected Supabase client (same pattern as supabase_repository).
  - No imports from bot_core / telegram_* — keeps audit usable from any layer
    (CLI, scheduler, tests) without bot startup.
  - Constants enumerate every recorded action so call sites cannot drift.
"""
from __future__ import annotations
import sys
from typing import Optional, Any

# ── Action names (8 from Meeting 6) ──────────────────────────────────────────
# 4 wired in Sprint 6. The remaining 4 are reserved for Sprint 7 call sites.
ACTION_RISK_PCT_CHANGE   = "risk_pct_change"
ACTION_ADDON_CONFIRM     = "addon_confirm"
ACTION_DEV_PIN_ACTIVATE  = "dev_pin_activate"
ACTION_DEV_PIN_FAIL      = "dev_pin_fail"
# Reserved for Sprint 7:
ACTION_MANUAL_TRADE      = "manual_trade"
ACTION_DEPLOY_TRIGGER    = "deploy_trigger"
ACTION_SETTINGS_CHANGE   = "settings_change"
ACTION_TELEGRAM_ALERT    = "telegram_alert_send"

_AUDIT_TABLE = "audit_log"


def log_action(
    sb: Any,
    action: str,
    *,
    chat_id: Optional[int] = None,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> bool:
    """Insert one audit-log row. Returns True on success, False on any error.

    Never raises. The caller's logic must never block on audit failure —
    the alternative (audit-or-no-action) would refuse user actions when
    Supabase is briefly unreachable, which is the wrong trade-off.
    """
    if sb is None or not action:
        return False
    try:
        row = {"action": action}
        if chat_id is not None:
            row["chat_id"] = int(chat_id)
        if before is not None:
            row["before_state"] = before
        if after is not None:
            row["after_state"] = after
        if metadata is not None:
            row["metadata"] = metadata
        sb.table(_AUDIT_TABLE).insert(row).execute()
        return True
    except Exception as e:
        # Print to stderr so docker logs capture it; never raise.
        print(f"[audit_logger] failed action={action}: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)
        return False
