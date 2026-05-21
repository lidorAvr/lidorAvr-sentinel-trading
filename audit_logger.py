"""
audit_logger.py — write-only compliance trail (+ one additive SELECT-only
retrospective read, DEC-20260515-008).

Records state-changing actions to Supabase `audit_log` (migration 002). The
module is write-only *in spirit*: ``log_action`` is the only mutating path.
DEC-20260515-008 adds ONE deliberate, additive, clearly-named READ path
(``read_recent_actions``) so the *user* can review their own recorded
decisions. It shares NONE of ``log_action``'s write path: it is SELECT-only,
hard-capped, fail-soft, and physically cannot insert/update/delete.

Design rules:
  - Fail-open. Never raise from log_action(); never block business logic.
    A missing audit row is better than a refused user action.
  - ``read_recent_actions`` is fail-soft: any error → ``[]`` (a read failure
    must never raise into a user flow), SELECT-only, never mutates.
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
# RISK-1b/1c/1d — at-entry locked-immutable price lifecycle (one row per lock
# attempt; richer than supabase_repository.set_locked_entry's value-only write):
ACTION_AT_ENTRY_LOCK         = "at_entry_lock"
ACTION_AT_ENTRY_SKIP         = "at_entry_skip"
# RISK-1c — admin-triggered batch backfill. ONE row per batch INVOCATION
# (in addition to the per-row ACTION_AT_ENTRY_LOCK / ACTION_AT_ENTRY_SKIP
# rows that lock_entry_from_trade_price writes inside the loop). Captures
# the operator chat_id + summary counts so the audit log answers "when did
# the founder run backfill, and what happened?" in one query.
ACTION_AT_ENTRY_BACKFILL_RUN = "at_entry_backfill_run"
# F7 (Meeting 21/05/2026) — every position state transition is recorded,
# including ALGO-managed positions whose Telegram alerts are intentionally
# suppressed (`_mgt_mode == "algo_observed"`). The CEO needed to answer
# "when did PLTR go to Broken?" — before F7 there was no record, only the
# state_label visible in /portfolio. metadata: symbol, prev_state, new_state,
# is_algo (bool), alert_sent (bool), suppression_reason (str or None).
ACTION_POSITION_STATE_TRANSITION = "position_state_transition"
# F8 (Meeting 21/05/2026 Wave 2) — deadletter for risk-monitor's Telegram
# sends. Before F8 a failed send (network blip / rate limit / bot down) was
# only logged to stderr. The CEO couldn't tell which alerts had silently
# dropped. F8 writes one row per send failure with: text_preview (first 80
# chars, no full message — defense in depth against accidental secret leak),
# error type, error message (truncated), source helper name (send_telegram
# vs send_telegram_with_keyboard). The audit log answers "did any
# state/digest alert silently fail in the last 24h?" in one query.
ACTION_TELEGRAM_SEND_FAILED = "telegram_send_failed"
# Engagement-meeting (21/05/2026 Wave-3A): rejection of an adaptive-risk
# recommendation. Distinct from ACTION_RISK_PCT_CHANGE so `/myactions` can
# render the dismissal with the operator's reason text rather than the
# misleading "0.60%→0.60%" line that ACTION_RISK_PCT_CHANGE produces on a
# rejection (where before == after). Pinned by Mark+Research rulings.
# Surfaces in telegram_audit_review with the reason verbatim (§X4).
ACTION_RISK_REJECT = "risk_reject"
# Engagement-meeting C1 "הספר מדבר חזרה": one row per Callback fire —
# Sentinel quoted the founder's own past journal line back to him at a
# near-identical setup. metadata: anchor_journal_id, surface_id, quoted_text
# (verbatim, §X4). Day-60+ first-fire; max 1 per fortnight per reason-bucket.
ACTION_CALLBACK_FIRED = "callback_fired"

_AUDIT_TABLE = "audit_log"

# DEC-20260515-008 / Mark §4 — bounded N for the read-only retrospective
# surface. A read can NEVER return more than this many rows regardless of the
# caller's requested limit (read-only guardrail; no unbounded scan).
_MAX_READ = 50


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


def read_recent_actions(
    sb: Any,
    *,
    chat_id: Optional[int] = None,
    limit: int = 20,
    actions: Optional[list] = None,
) -> list:
    """Read-only, bounded retrospective view of recorded actions
    (DEC-20260515-008 / Mark §4).

    SELECT-only. NEVER inserts/updates/deletes — it shares none of
    ``log_action``'s write path. Returns at most ``limit`` rows (hard-capped
    at ``_MAX_READ`` = 50), most-recent-first (``ORDER BY created_at DESC`` —
    relies on audit_log's own stored timestamp; no fabricated ordering).
    ``actions`` optionally filters to a whitelist of action constants. On any
    error returns ``[]`` and logs to stderr (same fail-soft posture as
    ``log_action`` — a read failure must never raise into a user flow).
    Honest: returns rows exactly as stored; callers must label the data
    source and must NOT derive performance numbers from these rows
    (Mark §4 D3/D4; AGENTS.md #1).
    """
    if sb is None:
        return []
    try:
        n = max(1, min(int(limit), _MAX_READ))
    except (TypeError, ValueError):
        n = _MAX_READ
    try:
        q = (
            sb.table(_AUDIT_TABLE)
            .select(
                "action,chat_id,before_state,after_state,metadata,created_at"
            )
            .order("created_at", desc=True)
            .limit(n)
        )
        if chat_id is not None:
            try:
                q = q.eq("chat_id", int(chat_id))
            except (TypeError, ValueError):
                pass
        if actions:
            q = q.in_("action", list(actions))
        res = q.execute()
        rows = (res.data if res and getattr(res, "data", None) else []) or []
        return list(rows)
    except Exception as e:
        # Fail-soft: a read failure must never raise into a user flow.
        print(
            f"[audit_logger] read_recent_actions failed: "
            f"{type(e).__name__}: {e}",
            file=sys.stderr,
            flush=True,
        )
        return []
