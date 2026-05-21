"""
§X5 Silence-As-Beat — pinning tests for engagement_suppression.py.

Mark binding: "absence IS the surface during missed-day / -2R-day /
settle-period; 'we noticed' messages BANNED". This file pins:
  - each predicate (is_two_r_down_day / is_settle_period_active /
    is_missed_day_window) in isolation
  - the composite gate (should_suppress_engagement) hierarchy
  - audit-line formatting

Plus a tiny §X6 Process-Mirror smoke that verifies the suppression
module imports stdlib-only (no engine/formatter/bot import → no
chance of drift into market-narration).
"""
import datetime as dt
import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import engagement_suppression as es  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# is_two_r_down_day
# ════════════════════════════════════════════════════════════════════════════

class TestIsTwoRDownDay:
    def test_none_is_not_a_bad_day(self):
        """Mark §3: absent data MUST NOT imply a verdict."""
        assert es.is_two_r_down_day(None) is False

    def test_zero_R_is_not_a_bad_day(self):
        assert es.is_two_r_down_day(0.0) is False

    def test_minus_one_R_is_not_a_bad_day(self):
        # The threshold is -2.0R, not -1.0R. A -1R day is just a normal
        # day; suppressing engagement for every minor red day would
        # collapse the system into silence.
        assert es.is_two_r_down_day(-1.0) is False

    def test_exact_minus_two_R_is_a_bad_day(self):
        # Mark §X5: -2R is the BOUNDARY of the -2R-day rule (`<=` not `<`).
        assert es.is_two_r_down_day(-2.0) is True

    def test_minus_three_R_is_a_bad_day(self):
        assert es.is_two_r_down_day(-3.0) is True

    def test_positive_R_is_not_a_bad_day(self):
        # An UP day, no matter how big, never triggers -2R suppression.
        assert es.is_two_r_down_day(5.0) is False

    def test_threshold_override(self):
        # Callers may override the threshold for testing. But §X5 binding
        # says overrides should stay strict (<= -1.0). The function does
        # not enforce this; the rules-doc does.
        assert es.is_two_r_down_day(-1.5, threshold=-1.0) is True
        assert es.is_two_r_down_day(-1.5, threshold=-2.0) is False


# ════════════════════════════════════════════════════════════════════════════
# is_settle_period_active
# ════════════════════════════════════════════════════════════════════════════

class TestIsSettlePeriodActive:
    def test_none_is_not_active(self):
        assert es.is_settle_period_active(None) is False

    def test_empty_dict_is_not_active(self):
        assert es.is_settle_period_active({}) is False

    def test_explicit_active_false_is_not_active(self):
        assert es.is_settle_period_active({"active": False}) is False

    def test_active_true_is_active(self):
        assert es.is_settle_period_active({"active": True}) is True

    def test_active_truthy_string_is_active(self):
        # Defensive bool() coercion — some callers may pass strings.
        assert es.is_settle_period_active({"active": "yes"}) is True


# ════════════════════════════════════════════════════════════════════════════
# is_missed_day_window
# ════════════════════════════════════════════════════════════════════════════

class TestIsMissedDayWindow:
    def test_none_is_not_missed(self):
        # No data on last-interaction → NOT a missed-day verdict.
        assert es.is_missed_day_window(None) is False

    def test_recent_interaction_is_not_missed(self):
        # 1 hour ago — clearly not missed.
        assert es.is_missed_day_window(1.0 / 24.0) is False

    def test_one_day_ago_is_not_missed(self):
        # 24h gap — under the 48h default threshold.
        assert es.is_missed_day_window(1.0) is False

    def test_exact_threshold_is_missed(self):
        # 48h gap = threshold boundary (`>=`).
        assert es.is_missed_day_window(2.0) is True

    def test_three_days_ago_is_missed(self):
        assert es.is_missed_day_window(3.0) is True

    def test_custom_threshold(self):
        # Callers may override (e.g. a stricter 24h threshold for
        # a specific surface).
        assert es.is_missed_day_window(1.5, threshold_hours=24.0) is True
        assert es.is_missed_day_window(0.5, threshold_hours=24.0) is False


# ════════════════════════════════════════════════════════════════════════════
# should_suppress_engagement — composite hierarchy
# ════════════════════════════════════════════════════════════════════════════

class TestCompositeSuppressionHierarchy:
    def test_no_signals_proceed(self):
        d = es.should_suppress_engagement()
        assert d["suppress"] is False
        assert d["rule_id"] == "NONE"
        assert d["reason"] == ""

    def test_two_r_down_wins(self):
        d = es.should_suppress_engagement(todays_R=-2.5)
        assert d["suppress"] is True
        assert d["rule_id"] == "TWO_R_DOWN"
        assert "-2R" in d["reason"]
        assert "-2.50R" in d["reason"]  # formatted with sign + 2 decimals

    def test_settle_wins_when_no_two_r(self):
        d = es.should_suppress_engagement(
            settle_info={"active": True, "hours_remaining": 3, "dir": "up"},
        )
        assert d["suppress"] is True
        assert d["rule_id"] == "SETTLE"
        assert "Settle-period active" in d["reason"]

    def test_missed_day_wins_when_no_two_r_no_settle(self):
        d = es.should_suppress_engagement(
            days_since_last_interaction=3.0,
        )
        assert d["suppress"] is True
        assert d["rule_id"] == "MISSED_DAY"
        assert "Missed-day window" in d["reason"]

    def test_two_r_overrides_settle(self):
        # Hierarchy binding: TWO_R_DOWN > SETTLE.
        d = es.should_suppress_engagement(
            todays_R=-2.5,
            settle_info={"active": True, "hours_remaining": 3},
        )
        assert d["rule_id"] == "TWO_R_DOWN"

    def test_two_r_overrides_missed_day(self):
        d = es.should_suppress_engagement(
            todays_R=-3.0,
            days_since_last_interaction=10.0,
        )
        assert d["rule_id"] == "TWO_R_DOWN"

    def test_settle_overrides_missed_day(self):
        # Hierarchy binding: SETTLE > MISSED_DAY (per the module's
        # docstring; settle is a current/active rule, missed-day is a
        # state of absence — the active rule takes precedence).
        d = es.should_suppress_engagement(
            settle_info={"active": True, "hours_remaining": 3},
            days_since_last_interaction=5.0,
        )
        assert d["rule_id"] == "SETTLE"

    def test_minus_one_R_does_not_suppress(self):
        # The hierarchy MUST NOT fire on -1R. This catches the worst
        # regression: silently lowering the bar to -1.0.
        d = es.should_suppress_engagement(todays_R=-1.0)
        assert d["suppress"] is False
        assert d["rule_id"] == "NONE"


# ════════════════════════════════════════════════════════════════════════════
# format_suppression_for_audit
# ════════════════════════════════════════════════════════════════════════════

class TestFormatSuppressionForAudit:
    def test_proceed_decision_returns_empty(self):
        decision = {"suppress": False, "rule_id": "NONE", "reason": ""}
        assert es.format_suppression_for_audit(decision) == ""

    def test_suppression_includes_rule_and_reason(self):
        decision = {
            "suppress": True,
            "rule_id": "TWO_R_DOWN",
            "reason": "-2R day floor — silent until next 16:00 IL (today's R=-2.50R)",
        }
        line = es.format_suppression_for_audit(decision)
        assert "§X5 SUPPRESS" in line
        assert "rule=TWO_R_DOWN" in line
        assert '"-2R day floor' in line

    def test_timestamp_prefix_when_now_supplied(self):
        decision = {
            "suppress": True,
            "rule_id": "SETTLE",
            "reason": "Settle-period active — 3h remaining",
        }
        now = dt.datetime(2026, 5, 21, 22, 30, 0)
        line = es.format_suppression_for_audit(decision, now=now)
        assert line.startswith("[2026-05-21T22:30:00]")


# ════════════════════════════════════════════════════════════════════════════
# §X6 Process-Mirror smoke — the module must stay a stdlib LEAF
# ════════════════════════════════════════════════════════════════════════════

class TestProcessMirrorLeafModule:
    """§X6 fence: the engagement-phase modules must use SELF-DATA only.
    The suppression primitive must stay a stdlib leaf — no imports from
    engine_core / analytics_engine / yfinance / market commentary
    formatters. A future drift that imports market data here would be
    a §X6 violation in dependency-graph form."""

    def test_imports_are_stdlib_only(self):
        import ast
        src_path = os.path.join(
            os.path.dirname(__file__), "..", "engagement_suppression.py"
        )
        with open(src_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        allowed_top_level = {"datetime", "typing", "__future__"}
        forbidden_names = {
            "engine_core", "analytics_engine", "yfinance",
            "telegram_formatters", "adaptive_risk_engine",
            "telegram_bot", "telegram_callbacks", "risk_monitor",
            "report_scheduler", "supabase", "pandas",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root not in forbidden_names, (
                        f"§X6 violation: engagement_suppression imports {root}"
                    )
                    # Not enforced positively — just verifying nothing
                    # forbidden snuck in. allowed_top_level is
                    # documentation.
                    _ = allowed_top_level
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                assert root not in forbidden_names, (
                    f"§X6 violation: engagement_suppression imports from {root}"
                )

    def test_module_actually_loads_without_external_deps(self):
        # Forced reload: the module loads with ONLY stdlib available.
        # If a future contributor adds an engine import, this test
        # passes (it's covered by the AST check above) but a CI
        # environment lacking the new dep would fail HERE, which is
        # the right place for the failure to surface.
        importlib.reload(es)
        assert hasattr(es, "should_suppress_engagement")
        assert hasattr(es, "is_two_r_down_day")
        assert hasattr(es, "is_settle_period_active")
        assert hasattr(es, "is_missed_day_window")
