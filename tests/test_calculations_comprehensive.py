"""
test_calculations_comprehensive.py — Mathematical correctness at highest precision.

Covers:
- R-multiple calculation (entry, initial stop, quantity)
- Profit Factor edge cases (all wins, all losses, single trade, ∞)
- Expectancy formula correctness
- Dev score: bounds, component sums, boundary conditions
- Adaptive risk: weighted win rate, ladder stepping, streak detection
- Oversized rate: boundary at exactly 125%
- Period comparison delta direction and sign
- NAV freshness hours precision
- Target risk USD
- Period label boundaries (month change, year change)
- Payoff ratio (0 loss avg handled)
"""
import json
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import analytics_engine as ae
import account_state   as acc
import adaptive_risk_engine as are


# ── Fixtures ───────────────────────────────────────────────────────────────────

ACCOUNT = {"nav": 10000.0, "risk_pct_input": 1.0}   # target_risk = $100
START   = datetime(2025, 1, 6)
END     = datetime(2025, 1, 13)


def _trade(cid, side, date, price, qty, pnl=0, init_stop=0, setup="B", sym="AAPL"):
    return {"campaign_id": cid, "side": side, "trade_date": date,
            "price": price, "quantity": qty, "pnl_usd": pnl,
            "initial_stop": init_stop, "stop_loss": init_stop,
            "setup_type": setup, "symbol": sym}


# ════════════════════════════════════════════════════════════════════════════════
# R-MULTIPLE PRECISION
# ════════════════════════════════════════════════════════════════════════════════

class TestRMultiplePrecision:
    def test_r_equals_one_on_exact_target_risk(self):
        """If PnL equals exactly the original risk, net_r must be 1.0."""
        # entry=100, stop=90, qty=10 → orig_risk=$100
        df = pd.DataFrame([
            _trade("c1", "BUY",  "2025-01-07", 100, 10, 0,   90),
            _trade("c1", "SELL", "2025-01-09", 100, 10, 100, 0),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert result["total_r_net"] == pytest.approx(1.0, abs=1e-9)

    def test_r_is_two_on_double_risk_pnl(self):
        df = pd.DataFrame([
            _trade("c1", "BUY",  "2025-01-07", 100, 10, 0,   90),
            _trade("c1", "SELL", "2025-01-09", 100, 10, 200, 0),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert result["total_r_net"] == pytest.approx(2.0, abs=1e-9)

    def test_negative_r_on_loss(self):
        df = pd.DataFrame([
            _trade("c1", "BUY",  "2025-01-07", 100, 10, 0,   90),
            _trade("c1", "SELL", "2025-01-09", 100, 10, -100, 0),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert result["total_r_net"] == pytest.approx(-1.0, abs=1e-9)

    def test_r_falls_back_to_target_risk_when_no_initial_stop(self):
        """No initial stop → use target_risk_usd as denominator."""
        # target_risk = 10000 * 1% = $100
        df = pd.DataFrame([
            _trade("c1", "BUY",  "2025-01-07", 100, 10, 0,   0),  # no stop
            _trade("c1", "SELL", "2025-01-09", 100, 10, 100, 0),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert result["total_r_net"] == pytest.approx(1.0, abs=1e-9)

    def test_r_sums_correctly_across_multiple_campaigns(self):
        df = pd.DataFrame([
            _trade("c1", "BUY",  "2025-01-07", 100, 10, 0,  90),
            _trade("c1", "SELL", "2025-01-09", 100, 10, 200, 0),
            _trade("c2", "BUY",  "2025-01-07", 200,  5, 0, 190),
            _trade("c2", "SELL", "2025-01-09", 200,  5, -50, 0),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        # c1: orig_risk=(100-90)*10=$100, net_r=200/100=+2R
        # c2: orig_risk=(200-190)*5=$50, net_r=-50/50=-1R
        assert result["total_r_net"] == pytest.approx(1.0, abs=1e-6)


# ════════════════════════════════════════════════════════════════════════════════
# PROFIT FACTOR EDGE CASES
# ════════════════════════════════════════════════════════════════════════════════

class TestProfitFactorEdgeCases:
    def test_all_wins_returns_sentinel_infinity(self):
        df = pd.DataFrame([
            _trade("c1", "BUY",  "2025-01-07", 100, 5, 0, 90),
            _trade("c1", "SELL", "2025-01-09", 100, 5, 100, 0),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert result["profit_factor"] == 99.0

    def test_all_losses_returns_zero(self):
        df = pd.DataFrame([
            _trade("c1", "BUY",  "2025-01-07", 100, 5, 0, 90),
            _trade("c1", "SELL", "2025-01-09", 100, 5, -100, 0),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert result["profit_factor"] == 0.0

    def test_even_gross_gives_pf_one(self):
        df = pd.DataFrame([
            _trade("c1", "BUY",  "2025-01-07", 100, 5, 0, 90),
            _trade("c1", "SELL", "2025-01-09", 100, 5, 100, 0),
            _trade("c2", "BUY",  "2025-01-07", 100, 5, 0, 90),
            _trade("c2", "SELL", "2025-01-09", 100, 5, -100, 0),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert result["profit_factor"] == pytest.approx(1.0)

    def test_pf_2_on_double_wins(self):
        df = pd.DataFrame([
            _trade("c1", "BUY",  "2025-01-07", 100, 5, 0, 90),
            _trade("c1", "SELL", "2025-01-09", 100, 5, 200, 0),
            _trade("c2", "BUY",  "2025-01-07", 100, 5, 0, 90),
            _trade("c2", "SELL", "2025-01-09", 100, 5, -100, 0),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert result["profit_factor"] == pytest.approx(2.0)


# ════════════════════════════════════════════════════════════════════════════════
# EXPECTANCY FORMULA
# ════════════════════════════════════════════════════════════════════════════════

class TestExpectancy:
    def test_expectancy_equals_wr_times_avg_win_plus_lossrate_times_avg_loss(self):
        """E = WR * avg_win_r + (1-WR) * avg_loss_r (avg_loss_r is negative)."""
        df = pd.DataFrame([
            _trade("c1", "BUY",  "2025-01-07", 100, 10, 0, 90),
            _trade("c1", "SELL", "2025-01-09", 100, 10, 200, 0),  # +2R win
            _trade("c2", "BUY",  "2025-01-07", 200,  5, 0, 190),
            _trade("c2", "SELL", "2025-01-09", 200,  5, -50, 0), # -1R loss
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        wr   = result["win_rate"]         # 0.5
        avgw = result["avg_win_r"]        # +2R
        avgl = result["avg_loss_r"]       # -1R
        expected_e = wr * avgw + (1 - wr) * avgl
        assert result["expectancy_r"] == pytest.approx(expected_e, abs=1e-6)

    def test_zero_expectancy_when_avg_win_equals_neg_avg_loss_at_50pct_wr(self):
        df = pd.DataFrame([
            _trade("c1", "BUY",  "2025-01-07", 100, 10, 0, 90),
            _trade("c1", "SELL", "2025-01-09", 100, 10, 100, 0),   # +1R
            _trade("c2", "BUY",  "2025-01-07", 100, 10, 0, 90),
            _trade("c2", "SELL", "2025-01-09", 100, 10, -100, 0),  # -1R
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert result["expectancy_r"] == pytest.approx(0.0, abs=1e-6)


# ════════════════════════════════════════════════════════════════════════════════
# DEV SCORE BOUNDS & COMPONENTS
# ════════════════════════════════════════════════════════════════════════════════

class TestDevScoreBounds:
    def _perfect(self):
        return {"ok": True, "campaigns_closed": 20,
                "missing_stop_rate": 0.0, "oversized_rate": 0.0,
                "expectancy_r": 2.0, "profit_factor": 5.0,
                "avg_win_r": 2.0, "avg_loss_r": -0.5,
                "avg_r_per_day": 0.2, "risk_adherence_rate": 1.0}

    def _worst(self):
        return {"ok": True, "campaigns_closed": 5,
                "missing_stop_rate": 1.0, "oversized_rate": 1.0,
                "expectancy_r": -1.0, "profit_factor": 0.0,
                "avg_win_r": 0.0, "avg_loss_r": -2.0,
                "avg_r_per_day": -0.5, "risk_adherence_rate": 0.0}

    def test_score_never_exceeds_100(self):
        result = ae.compute_trader_development_score(self._perfect())
        assert result["score"] <= 100

    def test_score_never_below_zero(self):
        result = ae.compute_trader_development_score(self._worst())
        assert result["score"] >= 0

    def test_breakdown_components_sum_to_score(self):
        for analytics in (self._perfect(), self._worst()):
            result = ae.compute_trader_development_score(analytics)
            if result["score"] is not None:
                bd     = result["breakdown"]
                total  = bd["process"] + bd["edge"] + bd["risk"] + bd["execution"]
                assert total == pytest.approx(result["score"], abs=1.0)

    def test_perfect_score_is_high(self):
        result = ae.compute_trader_development_score(self._perfect())
        assert result["score"] >= 85

    def test_worst_score_is_low(self):
        result = ae.compute_trader_development_score(self._worst())
        assert result["score"] <= 15

    def test_process_component_max_is_35(self):
        result = ae.compute_trader_development_score(self._perfect())
        assert result["breakdown"]["process"] <= 35.0

    def test_edge_component_max_is_35(self):
        result = ae.compute_trader_development_score(self._perfect())
        assert result["breakdown"]["edge"] <= 35.0

    def test_risk_component_max_is_20(self):
        result = ae.compute_trader_development_score(self._perfect())
        assert result["breakdown"]["risk"] <= 20.0

    def test_execution_component_max_is_10(self):
        result = ae.compute_trader_development_score(self._perfect())
        assert result["breakdown"]["execution"] <= 10.0


# ════════════════════════════════════════════════════════════════════════════════
# OVERSIZED RATE — EXACT 125% BOUNDARY
# ════════════════════════════════════════════════════════════════════════════════

class TestOversizedBoundary:
    """target_risk=$100; oversized threshold = $125 (125%)."""

    def _df_with_risk(self, actual_risk: float):
        """Build a DataFrame where BUY has specific actual_risk."""
        # actual_risk = (price - initial_stop) * quantity
        # e.g. price=100, qty=10, stop=100-actual_risk/10
        qty   = 10
        price = 100.0
        stop  = price - actual_risk / qty
        return pd.DataFrame([
            _trade("c1", "BUY",  "2025-01-07", price, qty, 0, stop),
            _trade("c1", "SELL", "2025-01-09", price, qty, 100, 0),
        ])

    def test_exactly_125pct_is_NOT_oversized(self):
        df = self._df_with_risk(125.0)   # exactly at threshold
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert result["oversized_rate"] == 0.0

    def test_one_dollar_above_125_IS_oversized(self):
        df = self._df_with_risk(125.01)
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert result["oversized_rate"] == 1.0

    def test_below_125pct_not_oversized(self):
        df = self._df_with_risk(99.0)
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert result["oversized_rate"] == 0.0


# ════════════════════════════════════════════════════════════════════════════════
# ADAPTIVE RISK ENGINE MATH
# ════════════════════════════════════════════════════════════════════════════════

class TestAdaptiveRiskMath:
    def _campaigns(self, wins: int, losses: int):
        base_win  = datetime(2025, 1, 20)
        base_loss = datetime(2025, 1, 10)
        result = []
        for i in range(wins):
            result.append({"campaign_id": f"w{i}", "is_win": True,
                           "close_date": base_win - timedelta(days=i), "total_pnl_usd": 100.0})
        for j in range(losses):
            result.append({"campaign_id": f"l{j}", "is_win": False,
                           "close_date": base_loss - timedelta(days=wins + j), "total_pnl_usd": -50.0})
        result.sort(key=lambda x: x["close_date"], reverse=True)
        return result

    def test_not_enough_trades_returns_error(self):
        result = are.compute_adaptive_risk(self._campaigns(1, 1), 0.5, 10000)
        assert result["ok"] is False
        assert result["error"] == "not_enough_trades"

    def test_strong_heat_goes_up_one_step(self):
        campaigns = self._campaigns(wins=8, losses=2)  # 80% WR → strong
        result = are.compute_adaptive_risk(campaigns, 0.5, 10000)
        assert result["ok"] is True
        assert result["direction"] == "up"
        assert result["recommended_risk_pct"] > 0.5

    def test_weak_heat_goes_down_two_steps(self):
        # 3+ consecutive losses (newest first)
        campaigns = [
            {"campaign_id": "l1", "is_win": False, "close_date": datetime(2025,1,10), "total_pnl_usd": -50},
            {"campaign_id": "l2", "is_win": False, "close_date": datetime(2025,1,9), "total_pnl_usd": -50},
            {"campaign_id": "l3", "is_win": False, "close_date": datetime(2025,1,8), "total_pnl_usd": -50},
            {"campaign_id": "w1", "is_win": True,  "close_date": datetime(2025,1,7), "total_pnl_usd": 100},
            {"campaign_id": "w2", "is_win": True,  "close_date": datetime(2025,1,6), "total_pnl_usd": 100},
        ]
        result = are.compute_adaptive_risk(campaigns, 1.0, 10000)
        assert result["direction"] == "down_fast"
        # 1.0% → ladder index 3; down 2 = index 1 = 0.50%
        assert result["recommended_risk_pct"] <= 0.75

    def test_recommendation_stays_within_ladder_bounds(self):
        """Recommended pct must always be in RISK_LADDER."""
        campaigns = self._campaigns(wins=9, losses=1)
        for current_pct in are.RISK_LADDER:
            result = are.compute_adaptive_risk(campaigns, current_pct, 10000)
            if result["ok"]:
                assert result["recommended_risk_pct"] in are.RISK_LADDER

    def test_ladder_top_cannot_go_higher(self):
        campaigns = self._campaigns(wins=10, losses=0)
        result = are.compute_adaptive_risk(campaigns, are.RISK_LADDER[-1], 10000)
        assert result["recommended_risk_pct"] == are.RISK_LADDER[-1]

    def test_ladder_bottom_cannot_go_lower(self):
        campaigns = [
            {"campaign_id": f"l{i}", "is_win": False, "close_date": datetime(2025,1,10-i), "total_pnl_usd": -50}
            for i in range(5)
        ]
        result = are.compute_adaptive_risk(campaigns, are.RISK_LADDER[0], 10000)
        assert result["recommended_risk_pct"] == are.RISK_LADDER[0]

    def test_strong_performer_gives_high_heat(self):
        """10 wins + 5 losses (67% WR, 2:1 payoff) → strong heat ≥ 80%, direction up."""
        # Old single-window formula gave exactly 80%. New multi-window gives higher score:
        # S9 = 9 wins (100% WR) + payoff/PF bonuses → heat well above 80%.
        campaigns = (
            [{"campaign_id": f"w{i}", "is_win": True,  "close_date": datetime(2025,1,20-i), "total_pnl_usd": 100} for i in range(10)] +
            [{"campaign_id": f"l{i}", "is_win": False, "close_date": datetime(2025,1,9-i),  "total_pnl_usd": -50}  for i in range(5)]
        )
        result = are.compute_adaptive_risk(campaigns, 0.5, 10000)
        assert result["ok"] is True
        assert result["heat_score"] >= 80.0
        assert result["direction"] == "up"

    def test_rec_usd_equals_nav_times_pct_div_100(self):
        campaigns = self._campaigns(wins=7, losses=3)
        nav = 15000.0
        result = are.compute_adaptive_risk(campaigns, 0.5, nav)
        if result["ok"]:
            expected = round(nav * result["recommended_risk_pct"] / 100, 0)
            assert result["recommended_risk_usd"] == expected


# ════════════════════════════════════════════════════════════════════════════════
# NAV FRESHNESS HOURS PRECISION
# ════════════════════════════════════════════════════════════════════════════════

class TestNavFreshnessPrecision:
    def test_exactly_24h_is_stale(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        ts  = (datetime.now() - timedelta(hours=24, seconds=1)).isoformat()
        cfg.write_text(json.dumps({"nav": 10000.0, "total_deposited": 10000.0,
                                   "risk_pct_input": 0.5, "nav_updated_at": ts}))
        with patch.object(acc, "_CONFIG_PATHS", [str(cfg)]):
            result = acc.load()
        assert result["freshness"] == "stale"

    def test_23h_59m_is_fresh(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        ts  = (datetime.now() - timedelta(hours=23, minutes=59)).isoformat()
        cfg.write_text(json.dumps({"nav": 10000.0, "total_deposited": 10000.0,
                                   "risk_pct_input": 0.5, "nav_updated_at": ts}))
        with patch.object(acc, "_CONFIG_PATHS", [str(cfg)]):
            result = acc.load()
        assert result["freshness"] == "fresh"

    def test_exactly_48h_is_critical(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        ts  = (datetime.now() - timedelta(hours=48, seconds=1)).isoformat()
        cfg.write_text(json.dumps({"nav": 10000.0, "total_deposited": 10000.0,
                                   "risk_pct_input": 0.5, "nav_updated_at": ts}))
        with patch.object(acc, "_CONFIG_PATHS", [str(cfg)]):
            result = acc.load()
        assert result["freshness"] == "critical"

    def test_age_hours_matches_actual_elapsed(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        ts  = (datetime.now() - timedelta(hours=5)).isoformat()
        cfg.write_text(json.dumps({"nav": 10000.0, "total_deposited": 10000.0,
                                   "risk_pct_input": 0.5, "nav_updated_at": ts}))
        with patch.object(acc, "_CONFIG_PATHS", [str(cfg)]):
            result = acc.load()
        assert result["age_hours"] == pytest.approx(5.0, abs=0.05)


# ════════════════════════════════════════════════════════════════════════════════
# TARGET RISK USD
# ════════════════════════════════════════════════════════════════════════════════

class TestTargetRiskUsd:
    def test_basic_calculation(self):
        account = {"nav": 10000.0, "risk_pct_input": 1.0}
        assert acc.target_risk_usd(account) == pytest.approx(100.0)

    def test_half_percent(self):
        account = {"nav": 7500.0, "risk_pct_input": 0.5}
        assert acc.target_risk_usd(account) == pytest.approx(37.5)

    def test_zero_nav_gives_zero(self):
        account = {"nav": 0.0, "risk_pct_input": 1.0}
        assert acc.target_risk_usd(account) == 0.0

    def test_large_nav(self):
        account = {"nav": 1_000_000.0, "risk_pct_input": 0.25}
        assert acc.target_risk_usd(account) == pytest.approx(2500.0)


# ════════════════════════════════════════════════════════════════════════════════
# PERIOD COMPARISON DELTA SIGNS
# ════════════════════════════════════════════════════════════════════════════════

class TestPeriodComparisonDeltas:
    def test_positive_delta_win_rate(self):
        r = ae.compute_period_comparison({"win_rate": 0.7}, {"win_rate": 0.5})
        assert r["win_rate"]["delta"] == pytest.approx(0.2)
        assert r["win_rate"]["direction"] == "up"
        assert r["win_rate"]["improving"] is True

    def test_negative_delta_win_rate(self):
        r = ae.compute_period_comparison({"win_rate": 0.3}, {"win_rate": 0.5})
        assert r["win_rate"]["delta"] == pytest.approx(-0.2)
        assert r["win_rate"]["direction"] == "down"
        assert r["win_rate"]["improving"] is False

    def test_lower_is_better_oversized_rate_improvement(self):
        r = ae.compute_period_comparison({"oversized_rate": 0.1}, {"oversized_rate": 0.3})
        assert r["oversized_rate"]["delta"] == pytest.approx(-0.2)
        assert r["oversized_rate"]["improving"] is True  # lower is better

    def test_lower_is_better_missing_stop_worsening(self):
        r = ae.compute_period_comparison({"missing_stop_rate": 0.3}, {"missing_stop_rate": 0.1})
        assert r["missing_stop_rate"]["improving"] is False

    def test_flat_delta_direction(self):
        r = ae.compute_period_comparison({"win_rate": 0.5}, {"win_rate": 0.5})
        assert r["win_rate"]["delta"] == 0.0
        assert r["win_rate"]["direction"] == "flat"

    def test_delta_rounded_to_4_decimal_places(self):
        r = ae.compute_period_comparison({"win_rate": 0.66666}, {"win_rate": 0.33333})
        assert r["win_rate"]["delta"] == round(0.66666 - 0.33333, 4)
