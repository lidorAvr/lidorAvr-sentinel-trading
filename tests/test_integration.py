"""
Integration tests — cross-module flows.

These tests exercise interactions between modules rather than unit-testing
a single function. They use fixtures from conftest.py where appropriate.
"""
import json
import math
import os
import sys
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.mark.integration
class TestAnalyticsUsesGetCampaignRiskMetrics:
    """Verify analytics_engine no longer uses inline orig_risk formula."""

    def _make_df(self):
        return pd.DataFrame([
            {"campaign_id": "c1", "side": "BUY",  "trade_date": "2025-01-07",
             "price": 100, "quantity": 10, "pnl_usd": 0,   "initial_stop": 90,
             "stop_loss": 90, "setup_type": "Breakout", "symbol": "AAPL"},
            {"campaign_id": "c1", "side": "SELL", "trade_date": "2025-01-09",
             "price": 110, "quantity": 10, "pnl_usd": 100, "initial_stop": 0,
             "stop_loss": 0,  "setup_type": "Breakout", "symbol": "AAPL"},
        ])

    def test_get_campaign_risk_metrics_is_called(self):
        import analytics_engine as ae
        import engine_core as ec
        start = datetime(2025, 1, 6)
        end   = datetime(2025, 1, 13)
        account = {"nav": 10000.0, "risk_pct_input": 1.0}
        # ec.get_campaign_risk_metrics is called inside analytics_engine via the
        # module-level 'ec' reference. Patch it there.
        sentinel = MagicMock(return_value={"original_risk": 100.0, "valid": True, "reason": ""})
        with patch.object(ae.ec, "get_campaign_risk_metrics", sentinel):
            result = ae.compute_period_analytics(self._make_df(), start, end, account)
        assert result["campaigns_closed"] == 1
        sentinel.assert_called_once()

    def test_r_correct_via_get_campaign_risk_metrics(self):
        """End-to-end: entry=100, stop=90, qty=10 → orig_risk=$100; pnl=$200 → net_r=2.0"""
        import analytics_engine as ae
        start   = datetime(2025, 1, 6)
        end     = datetime(2025, 1, 13)
        account = {"nav": 10000.0, "risk_pct_input": 1.0}
        df = pd.DataFrame([
            {"campaign_id": "c1", "side": "BUY",  "trade_date": "2025-01-07",
             "price": 100, "quantity": 10, "pnl_usd": 0,   "initial_stop": 90,
             "stop_loss": 90, "setup_type": "Breakout", "symbol": "AAPL"},
            {"campaign_id": "c1", "side": "SELL", "trade_date": "2025-01-09",
             "price": 120, "quantity": 10, "pnl_usd": 200, "initial_stop": 0,
             "stop_loss": 0,  "setup_type": "Breakout", "symbol": "AAPL"},
        ])
        result = ae.compute_period_analytics(df, start, end, account)
        assert result["avg_win_r"] == pytest.approx(2.0)


@pytest.mark.integration
class TestFollowThroughWiredToPositionState:
    """Verify follow_through_score affects DEAD_MONEY classification."""

    def _dead_money_args(self):
        from engine_core import compute_position_state
        # Conditions that would trigger DEAD_MONEY if follow_through is weak:
        # age >= 8, open_r in [-0.5, 0.75], no new high
        return dict(
            side="BUY",
            management_mode="manual_managed",
            age_days=10.0,
            open_r=0.3,
            realized_pnl=0.0,
            original_campaign_risk=500.0,
            current_price=105.0,
            current_stop=98.0,
            days_to_earnings=None,
            has_new_high_since_entry=False,
        )

    def test_weak_follow_through_enables_dead_money(self):
        from engine_core import compute_position_state, POSITION_STATE_DEAD_MONEY
        result = compute_position_state(**self._dead_money_args(), follow_through_score=20.0)
        assert result["state"] == POSITION_STATE_DEAD_MONEY

    def test_strong_follow_through_prevents_dead_money(self):
        from engine_core import compute_position_state, POSITION_STATE_DEAD_MONEY
        result = compute_position_state(**self._dead_money_args(), follow_through_score=85.0)
        assert result["state"] != POSITION_STATE_DEAD_MONEY

    def test_none_follow_through_treated_as_neutral_not_dead_money(self):
        from engine_core import compute_position_state, POSITION_STATE_DEAD_MONEY
        result = compute_position_state(**self._dead_money_args(), follow_through_score=None)
        assert result["state"] != POSITION_STATE_DEAD_MONEY


@pytest.mark.integration
class TestSnapshotStoreInfSerialization:
    """Verify report_snapshot_store sanitizes math.inf before JSON serialization."""

    def test_inf_profit_factor_serialized_as_null(self):
        import report_snapshot_store as rss
        analytics = {
            "campaigns_closed": 5,
            "win_rate": 1.0,
            "expectancy_r": 2.0,
            "profit_factor": math.inf,
            "avg_win_r": 2.0,
            "avg_loss_r": 0.0,
            "total_r_net": 10.0,
            "realized_pnl": 500.0,
            "missing_stop_rate": 0.0,
            "oversized_rate": 0.0,
            "avg_r_per_day": 0.2,
        }
        account_state = {"nav": 10000.0, "nav_source": "broker",
                         "freshness": "fresh", "risk_pct_input": 1.0}
        with tempfile.TemporaryDirectory() as tmpdir:
            original_base = rss._BASE_DIR
            rss._BASE_DIR = os.path.join(tmpdir, "snapshots")
            try:
                rss.save("weekly", datetime(2026, 4, 28), datetime(2026, 5, 4),
                         analytics, account_state)
                saved = rss.load_recent("weekly", n=1)
            finally:
                rss._BASE_DIR = original_base

        assert len(saved) == 1
        assert saved[0]["profit_factor"] is None  # math.inf → None in JSON

    def test_finite_profit_factor_preserved(self):
        import report_snapshot_store as rss
        analytics = {
            "campaigns_closed": 5,
            "win_rate": 0.6,
            "expectancy_r": 0.5,
            "profit_factor": 2.5,
            "avg_win_r": 1.5,
            "avg_loss_r": -0.5,
            "total_r_net": 3.0,
            "realized_pnl": 200.0,
            "missing_stop_rate": 0.0,
            "oversized_rate": 0.0,
            "avg_r_per_day": 0.1,
        }
        account_state = {"nav": 10000.0, "nav_source": "broker",
                         "freshness": "fresh", "risk_pct_input": 1.0}
        with tempfile.TemporaryDirectory() as tmpdir:
            original_base = rss._BASE_DIR
            rss._BASE_DIR = os.path.join(tmpdir, "snapshots")
            try:
                rss.save("weekly", datetime(2026, 5, 5), datetime(2026, 5, 11),
                         analytics, account_state)
                saved = rss.load_recent("weekly", n=1)
            finally:
                rss._BASE_DIR = original_base

        assert len(saved) == 1
        assert saved[0]["profit_factor"] == pytest.approx(2.5)
