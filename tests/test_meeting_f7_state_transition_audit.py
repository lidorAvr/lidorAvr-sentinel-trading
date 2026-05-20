"""
F7 (Meeting 21/05/2026) — position state transitions are now audit-logged,
including ALGO positions whose Telegram alerts are intentionally
suppressed.

Why this exists:
  The founder asked "when did PLTR go to Broken?" and the system could
  not answer. The state machine in risk_monitor.py detects ALGO
  transitions correctly (state_label shown in /portfolio), but the
  Telegram-alert path is gated by `_mgt_mode != "algo_observed"` — by
  design (Sentinel doesn't manage ALGO exits). That gate also
  silently skipped writing ANY record of the transition, leaving the
  CEO without an audit trail.

F7 adds ONE audit row per state change, regardless of ALGO. The new
ACTION_POSITION_STATE_TRANSITION constant captures:
  - symbol / campaign_id / setup
  - prev_state / new_state
  - is_algo (bool)
  - telegram_suppressed (bool — True iff is_algo)
  - suppression_reason (None or "algo_observed")
  - open_r

Telegram alert behaviour is BYTE-IDENTICAL to before — ALGO is still
not alerted (the gate at line 1020 stays). Only the audit log gains a
new write.

Tests pinned in this file:
  A. The audit constant exists with the documented name.
  B. risk_monitor source carries the log_action call gated only on
     state change (not on _mgt_mode), so ALGO transitions audit.
  C. Surface-wiring: audit_logger is imported in risk_monitor.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(rel_path):
    with open(os.path.join(ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


# ════════════════════════════════════════════════════════════════════════════
# A. The audit constant exists with the documented name
# ════════════════════════════════════════════════════════════════════════════

class TestAuditConstant:
    def test_constant_name(self):
        import audit_logger
        assert hasattr(audit_logger, "ACTION_POSITION_STATE_TRANSITION")
        assert audit_logger.ACTION_POSITION_STATE_TRANSITION == \
            "position_state_transition"


# ════════════════════════════════════════════════════════════════════════════
# B. Source-scan — risk_monitor.py wires the audit before the ALGO gate
# ════════════════════════════════════════════════════════════════════════════

class TestRiskMonitorAuditsAllStateTransitions:
    def test_imports_audit_logger(self):
        src = _read("risk_monitor.py")
        assert "import audit_logger" in src, (
            "risk_monitor.py must import audit_logger to write the F7 "
            "state-transition rows."
        )

    def test_audit_action_referenced(self):
        src = _read("risk_monitor.py")
        assert "ACTION_POSITION_STATE_TRANSITION" in src, (
            "risk_monitor.py must reference the F7 audit constant — "
            "otherwise no state transitions are recorded."
        )

    def test_audit_block_runs_before_state_alert_algo_gate(self):
        # The state-transition audit MUST execute BEFORE the state-alert
        # ALGO-suppression gate (the "Phase 5" block at the bottom of the
        # per-position loop). If it runs INSIDE that gate, ALGO transitions
        # go un-audited — exactly the bug F7 fixes. Anchor on the
        # "Phase 5: state-change alerts" comment which uniquely identifies
        # the state-alert block (multiple `algo_observed` references exist
        # elsewhere in the file for unrelated gates).
        src = _read("risk_monitor.py")
        audit_pos = src.find("ACTION_POSITION_STATE_TRANSITION")
        # The Phase 5 block opens with this exact comment line; the algo
        # gate sits inside it on the SAME line as the if-statement that
        # gates the legacy state-alert behaviour.
        state_alert_block_pos = src.find("Phase 5: state-change alerts")
        assert audit_pos > 0, "audit call not found"
        assert state_alert_block_pos > 0, "Phase 5 block not found"
        assert audit_pos < state_alert_block_pos, (
            "F7 audit call must precede the Phase 5 state-alert block "
            "so ALGO transitions are recorded BEFORE the ALGO-suppression "
            "gate filters them out. If a future edit moves it inside the "
            "block, the CEO loses ALGO chronological visibility."
        )

    def test_audit_metadata_carries_required_fields(self):
        src = _read("risk_monitor.py")
        # The metadata dict written to the audit row must carry the keys
        # the CEO needs to answer "when did SYMBOL go to STATE?".
        for field in ("symbol", "prev_state", "new_state",
                      "is_algo", "telegram_suppressed"):
            assert f'"{field}"' in src, (
                f"audit metadata missing required field `{field}` — "
                f"the CEO query will not work without it."
            )


# ════════════════════════════════════════════════════════════════════════════
# C. The existing Telegram-alert path is unchanged for ALGO (suppression)
# ════════════════════════════════════════════════════════════════════════════

class TestTelegramAlertPathUnchanged:
    """F7 must NOT cause Telegram alerts for ALGO. Suppression for ALGO is
    intentional (Sentinel doesn't manage external exits). The audit is the
    only addition."""

    def test_algo_telegram_suppression_gate_still_present(self):
        src = _read("risk_monitor.py")
        # The original gate text must still be present — F7 added a
        # SIBLING audit block, not a replacement.
        assert '_mgt_mode != "algo_observed"' in src, (
            "the ALGO Telegram-suppression gate disappeared — F7 should "
            "only add the audit, never weaken existing protections."
        )

    def test_runner_broken_dead_money_alert_branches_unchanged(self):
        # The three first-time state alerts (RUNNER, BROKEN, DEAD_MONEY)
        # must remain in the source. They live INSIDE the algo-suppression
        # gate, so ALGO never gets these — intentional.
        src = _read("risk_monitor.py")
        assert "_runner_state_alert" in src
        assert "_broken_state_alert" in src
        assert "_dead_money_alert" in src
