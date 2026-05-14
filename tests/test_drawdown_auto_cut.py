"""
Sprint 8 #9 — drawdown auto-cut (Jordan/Risk Mgmt from Meeting 8).

When 30-day realised PnL drops below -8% of NAV, the heat-based
recommendation is overridden to a forced cut. Mark's "stop the bleeding"
rule overrides any positive heat reading — the trader cannot recover
into worse risk.

Tests cover:
  1. filter_closed_within_days — date math correctness
  2. drawdown_auto_cut_recommendation — pure trigger logic
  3. compute_adaptive_risk integration — override applied end-to-end
"""
import pytest
from datetime import datetime, timedelta
import adaptive_risk_engine as are


def _camp(pnl, days_ago=1, win=None):
    """Build a closed-campaign dict with sensible defaults."""
    return {
        "campaign_id": f"CID-{pnl}",
        "symbol": "TEST",
        "setup_type": "VCP",
        "total_pnl_usd": float(pnl),
        "close_date": datetime.now() - timedelta(days=days_ago),
        "is_win": win if win is not None else (pnl > 0),
        "original_campaign_risk": 100.0,
        "stat_bucket": "discretionary",
    }


# ── filter_closed_within_days ────────────────────────────────────────────────

@pytest.mark.unit
class TestFilterClosedWithinDays:

    def test_includes_recent_campaigns(self):
        camps = [_camp(100, days_ago=5), _camp(-50, days_ago=15)]
        out = are.filter_closed_within_days(camps, window_days=30)
        assert len(out) == 2

    def test_excludes_old_campaigns(self):
        camps = [_camp(100, days_ago=5), _camp(-50, days_ago=45)]
        out = are.filter_closed_within_days(camps, window_days=30)
        assert len(out) == 1
        assert out[0]["total_pnl_usd"] == 100

    def test_boundary_30_days_included(self):
        # A campaign closed exactly 29 days ago is in the 30-day window
        camps = [_camp(100, days_ago=29)]
        out = are.filter_closed_within_days(camps, window_days=30)
        assert len(out) == 1

    def test_returns_empty_when_no_dates(self):
        camps = [{"total_pnl_usd": 100, "close_date": None}]
        out = are.filter_closed_within_days(camps)
        assert out == []

    def test_handles_unparseable_date_gracefully(self):
        camps = [{"total_pnl_usd": 100, "close_date": "not-a-date"}]
        # Must not raise — returns empty
        out = are.filter_closed_within_days(camps)
        assert out == []

    def test_custom_window(self):
        camps = [_camp(100, days_ago=5), _camp(-50, days_ago=14)]
        out = are.filter_closed_within_days(camps, window_days=10)
        assert len(out) == 1


# ── drawdown_auto_cut_recommendation ─────────────────────────────────────────

@pytest.mark.unit
class TestDrawdownTrigger:

    def test_triggers_at_minus_8pct_with_high_risk(self):
        nav = 10000.0
        # Need -800 over 30d to hit -8%; current_risk_pct=1.0 (above 0.40 floor)
        camps = [_camp(-400, days_ago=5), _camp(-450, days_ago=10)]
        rec = are.drawdown_auto_cut_recommendation(camps, current_risk_pct=1.0, nav=nav)
        assert rec is not None
        assert rec["force_cut_to_pct"] == 0.40
        assert rec["drawdown_pct"] < -8.0
        assert rec["pnl_30d_usd"] == -850.0

    def test_no_trigger_when_drawdown_too_small(self):
        nav = 10000.0
        # -700 = -7%, just under trigger
        camps = [_camp(-700, days_ago=5)]
        rec = are.drawdown_auto_cut_recommendation(camps, current_risk_pct=1.0, nav=nav)
        assert rec is None

    def test_no_trigger_when_already_at_floor(self):
        """If current_risk_pct ≤ 0.40, no further cut needed."""
        nav = 10000.0
        camps = [_camp(-1000, days_ago=5)]  # -10%
        rec = are.drawdown_auto_cut_recommendation(camps, current_risk_pct=0.40, nav=nav)
        assert rec is None

    def test_no_trigger_below_floor(self):
        nav = 10000.0
        camps = [_camp(-1000, days_ago=5)]
        rec = are.drawdown_auto_cut_recommendation(camps, current_risk_pct=0.25, nav=nav)
        assert rec is None

    def test_no_trigger_with_empty_campaigns(self):
        rec = are.drawdown_auto_cut_recommendation([], current_risk_pct=1.0, nav=10000.0)
        assert rec is None

    def test_no_trigger_with_zero_nav(self):
        camps = [_camp(-1000, days_ago=5)]
        rec = are.drawdown_auto_cut_recommendation(camps, current_risk_pct=1.0, nav=0)
        assert rec is None

    def test_excludes_old_losses_from_window(self):
        """A loss 60 days ago doesn't count toward the 30-day window."""
        nav = 10000.0
        camps = [
            _camp(-1500, days_ago=60),  # excluded
            _camp(-200,  days_ago=5),   # included
        ]
        rec = are.drawdown_auto_cut_recommendation(camps, current_risk_pct=1.0, nav=nav)
        # Only -200 inside window = -2%, below trigger
        assert rec is None

    def test_reason_string_contains_actionable_info(self):
        nav = 10000.0
        camps = [_camp(-1000, days_ago=5)]
        rec = are.drawdown_auto_cut_recommendation(camps, current_risk_pct=1.0, nav=nav)
        assert "30d" in rec["reason"] or "30" in rec["reason"]
        assert "0.40" in rec["reason"]

    def test_records_n_trades_in_window(self):
        nav = 10000.0
        camps = [_camp(-300, days_ago=5), _camp(-300, days_ago=10), _camp(-300, days_ago=15)]
        rec = are.drawdown_auto_cut_recommendation(camps, current_risk_pct=1.0, nav=nav)
        assert rec["n_trades"] == 3


# ── compute_adaptive_risk integration ────────────────────────────────────────

@pytest.mark.integration
class TestComputeAdaptiveRiskOverride:
    """When drawdown triggers, compute_adaptive_risk's recommendation is overridden."""

    def test_drawdown_overrides_positive_heat(self):
        """Even with a winning streak in S9, a 30d -10% DD forces the cut."""
        nav = 10000.0
        # 9 small wins recently (good heat) but 2 catastrophic losses 20-25d ago
        # totalling -1500 = -15% drawdown
        camps = (
            [_camp(50, days_ago=i, win=True) for i in range(1, 10)]
            + [_camp(-750, days_ago=20), _camp(-750, days_ago=25)]
        )
        rec = are.compute_adaptive_risk(camps, current_risk_pct=1.50, nav=nav)
        assert rec["ok"] is True
        assert rec.get("override") == "drawdown_auto_cut"
        assert rec["recommended_risk_pct"] == 0.40
        assert rec["direction"] == "down_fast"
        assert "drawdown" in rec["step_type"].lower() or "🚨" in rec["step_type"]

    def test_no_override_when_drawdown_normal(self):
        """Normal P&L → standard heat-based recommendation, no override key."""
        nav = 10000.0
        camps = [_camp(100, days_ago=i, win=True) for i in range(1, 10)]
        rec = are.compute_adaptive_risk(camps, current_risk_pct=0.85, nav=nav)
        assert rec["ok"] is True
        assert "override" not in rec

    def test_override_includes_diagnostic_fields(self):
        nav = 10000.0
        camps = (
            [_camp(0, days_ago=i, win=True) for i in range(1, 4)]
            + [_camp(-1000, days_ago=10)]
        )
        rec = are.compute_adaptive_risk(camps, current_risk_pct=1.50, nav=nav)
        if rec.get("override") == "drawdown_auto_cut":
            assert "drawdown_pct" in rec
            assert "drawdown_pnl_usd" in rec
            assert "drawdown_n_trades" in rec
            assert "drawdown_window_days" in rec
            # heat_factors gets the drawdown reason at the top
            assert any("Drawdown" in f or "DD" in f or "⛔" in f for f in rec["heat_factors"])
