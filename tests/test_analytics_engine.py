"""Tests for analytics_engine.py"""
import os
import sys
from datetime import datetime

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import analytics_engine as m

_ACCOUNT = {"nav": 10000.0, "risk_pct_input": 1.0}   # target_risk = $100


def _make_df(rows):
    return pd.DataFrame(rows)


def _base_trade(campaign_id, side, date_str, price, qty, pnl=0,
                initial_stop=0, setup="Breakout", symbol="AAPL"):
    return {
        "campaign_id": campaign_id,
        "side":         side,
        "trade_date":   date_str,
        "price":        price,
        "quantity":     qty,
        "pnl_usd":      pnl,
        "initial_stop": initial_stop,
        "stop_loss":    initial_stop,
        "setup_type":   setup,
        "symbol":       symbol,
    }


START = datetime(2025, 1, 6)
END   = datetime(2025, 1, 13)


class TestComputePeriodAnalyticsEmpty:
    def test_none_df_returns_empty(self):
        result = m.compute_period_analytics(None, START, END, _ACCOUNT)
        assert result["campaigns_closed"] == 0
        assert result["ok"] is True

    def test_empty_df_returns_empty(self):
        result = m.compute_period_analytics(pd.DataFrame(), START, END, _ACCOUNT)
        assert result["campaigns_closed"] == 0

    def test_no_sells_in_period_returns_empty(self):
        df = _make_df([
            _base_trade("c1", "BUY",  "2025-01-07", 100, 10, 0, 95),
        ])
        result = m.compute_period_analytics(df, START, END, _ACCOUNT)
        assert result["campaigns_closed"] == 0


class TestComputePeriodAnalyticsOneTrade:
    def _win_df(self):
        return _make_df([
            _base_trade("c1", "BUY",  "2025-01-07", 100, 10, 0,  95),
            _base_trade("c1", "SELL", "2025-01-09", 110, 10, 100, 0),
        ])

    def test_one_winning_campaign(self):
        result = m.compute_period_analytics(self._win_df(), START, END, _ACCOUNT)
        assert result["campaigns_closed"] == 1
        assert result["win_rate"] == 1.0
        assert result["realized_pnl"] == pytest.approx(100.0)

    def test_total_r_positive(self):
        result = m.compute_period_analytics(self._win_df(), START, END, _ACCOUNT)
        assert result["total_r_net"] > 0

    def test_profit_factor_no_losses(self):
        import math
        result = m.compute_period_analytics(self._win_df(), START, END, _ACCOUNT)
        assert math.isinf(result["profit_factor"])  # no losses → infinity (mathematically correct)

    def test_missing_stop_rate_full(self):
        df = _make_df([
            _base_trade("c1", "BUY",  "2025-01-07", 100, 10, 0,  0),   # no initial_stop
            _base_trade("c1", "SELL", "2025-01-09", 110, 10, 100, 0),
        ])
        result = m.compute_period_analytics(df, START, END, _ACCOUNT)
        assert result["missing_stop_rate"] == 1.0

    def test_missing_stop_rate_zero_when_stop_set(self):
        result = m.compute_period_analytics(self._win_df(), START, END, _ACCOUNT)
        assert result["missing_stop_rate"] == 0.0


class TestComputePeriodAnalyticsWinLoss:
    def _mixed_df(self):
        return _make_df([
            _base_trade("c1", "BUY",  "2025-01-07", 100, 10, 0,   95),
            _base_trade("c1", "SELL", "2025-01-09", 110, 10, 100,  0),
            _base_trade("c2", "BUY",  "2025-01-07", 200, 5,  0,  190),
            _base_trade("c2", "SELL", "2025-01-10", 180, 5,  -100, 0),
        ])

    def test_two_campaigns(self):
        result = m.compute_period_analytics(self._mixed_df(), START, END, _ACCOUNT)
        assert result["campaigns_closed"] == 2

    def test_win_rate_fifty_percent(self):
        result = m.compute_period_analytics(self._mixed_df(), START, END, _ACCOUNT)
        assert result["win_rate"] == pytest.approx(0.5)

    def test_profit_factor_positive(self):
        result = m.compute_period_analytics(self._mixed_df(), START, END, _ACCOUNT)
        assert result["profit_factor"] == pytest.approx(1.0)

    def test_setup_breakdown_populated(self):
        result = m.compute_period_analytics(self._mixed_df(), START, END, _ACCOUNT)
        assert "Breakout" in result["setup_breakdown"]

    def test_best_worst_trade_present(self):
        result = m.compute_period_analytics(self._mixed_df(), START, END, _ACCOUNT)
        assert result["best_trade"] is not None
        assert result["worst_trade"] is not None
        assert result["best_trade"]["net_pnl"] > result["worst_trade"]["net_pnl"]

    def test_returns_ok_true(self):
        result = m.compute_period_analytics(self._mixed_df(), START, END, _ACCOUNT)
        assert result["ok"] is True


class TestOversizedRate:
    def test_oversized_flagged_when_above_125pct(self):
        # target_risk=$100; actual_risk = (100-94)*10 = $60 < $125 → not oversized
        # actual_risk = (100-80)*10 = $200 > $125 → oversized
        df = _make_df([
            _base_trade("c1", "BUY",  "2025-01-07", 100, 10, 0, 80),   # oversized
            _base_trade("c1", "SELL", "2025-01-09", 110, 10, 100, 0),
            _base_trade("c2", "BUY",  "2025-01-07", 100, 10, 0, 94),   # normal
            _base_trade("c2", "SELL", "2025-01-09", 110, 10, 100, 0),
        ])
        result = m.compute_period_analytics(df, START, END, _ACCOUNT)
        assert result["oversized_rate"] == pytest.approx(0.5)


class TestComputeVerdict:
    def _ana(self, tr, wr, miss=0.0, over=0.0):
        return {"ok": True, "campaigns_closed": 5, "total_r_net": tr,
                "win_rate": wr, "missing_stop_rate": miss, "oversized_rate": over}

    def test_strong(self):
        _, cls = m.compute_verdict(self._ana(2.0, 0.6))
        assert cls == "strong"

    def test_defensive_low_r(self):
        _, cls = m.compute_verdict(self._ana(-1.0, 0.4))
        assert cls == "defensive"

    def test_defensive_low_win_rate(self):
        _, cls = m.compute_verdict(self._ana(0.5, 0.3))
        assert cls == "defensive"

    def test_mixed(self):
        _, cls = m.compute_verdict(self._ana(0.5, 0.5))
        assert cls == "mixed"

    def test_neutral_no_trades(self):
        _, cls = m.compute_verdict({"ok": True, "campaigns_closed": 0,
                                    "total_r_net": 0, "win_rate": 0,
                                    "missing_stop_rate": 0, "oversized_rate": 0})
        assert cls == "neutral"


class TestComputeTraderDevScore:
    def _good_analytics(self):
        return {
            "ok": True, "campaigns_closed": 10,
            "missing_stop_rate": 0.0, "oversized_rate": 0.0,
            "expectancy_r": 0.5, "profit_factor": 2.0,
            "avg_win_r": 1.0, "avg_loss_r": -0.5,
            "avg_r_per_day": 0.15,
            "risk_adherence_rate": 0.9,
        }

    def test_high_score_for_good_trader(self):
        result = m.compute_trader_development_score(self._good_analytics())
        assert result["score"] is not None
        assert result["score"] >= 70

    def test_returns_none_score_with_no_trades(self):
        result = m.compute_trader_development_score(
            {"ok": True, "campaigns_closed": 0, **{k: 0 for k in
             ["missing_stop_rate","oversized_rate","expectancy_r",
              "profit_factor","avg_win_r","avg_loss_r","avg_r_per_day"]}}
        )
        assert result["score"] is None

    def test_breakdown_keys_present(self):
        result = m.compute_trader_development_score(self._good_analytics())
        for key in ("process", "edge", "risk", "execution"):
            assert key in result["breakdown"]

    def test_score_in_range(self):
        result = m.compute_trader_development_score(self._good_analytics())
        assert 0 <= result["score"] <= 100


class TestComputePeriodComparison:
    def test_delta_computed(self):
        curr = {"win_rate": 0.6, "expectancy_r": 0.5}
        prev = {"win_rate": 0.4, "expectancy_r": 0.3}
        result = m.compute_period_comparison(curr, prev)
        assert result["win_rate"]["delta"] == pytest.approx(0.2)
        assert result["win_rate"]["improving"] is True

    def test_empty_when_no_previous(self):
        result = m.compute_period_comparison({"win_rate": 0.5}, {})
        assert result == {}

    def test_lower_better_metrics_flip_improving(self):
        curr = {"missing_stop_rate": 0.1}
        prev = {"missing_stop_rate": 0.2}
        result = m.compute_period_comparison(curr, prev)
        assert result["missing_stop_rate"]["improving"] is True   # lower is better

    def test_missing_metric_skipped(self):
        result = m.compute_period_comparison({"win_rate": 0.5}, {"expectancy_r": 0.3})
        assert "win_rate" not in result
        assert "expectancy_r" not in result


class TestAggregateGetCampaignRiskMetrics:
    """Verify _aggregate_campaigns uses get_campaign_risk_metrics, not the inline formula."""

    def test_r_calculation_matches_get_campaign_risk_metrics(self):
        # entry=100, stop=90, qty=10 → orig_risk = 100 USD; pnl=200 → net_r=2.0
        df = _make_df([
            _base_trade("c1", "BUY",  "2025-01-07", 100, 10, 0,   90),
            _base_trade("c1", "SELL", "2025-01-09", 120, 10, 200,  0),
        ])
        result = m.compute_period_analytics(df, START, END, _ACCOUNT)
        assert result["campaigns_closed"] == 1
        # net_r should be 200 / 100 = 2.0
        assert result["avg_win_r"] == pytest.approx(2.0)

    def test_missing_stop_campaign_is_data_incomplete_and_excluded(self):
        # initial_stop=0 → get_campaign_risk_metrics valid=False → true_orig_risk=0
        # → classify_stat_bucket → DATA_INCOMPLETE → excluded from stats per
        # AGENTS.md invariant #8. (This previously asserted the bug: the
        # campaign was counted via the target_risk fallback.)
        df = _make_df([
            _base_trade("c1", "BUY",  "2025-01-07", 100, 10, 0,  0),   # no stop
            _base_trade("c1", "SELL", "2025-01-09", 105, 10, 50, 0),
        ])
        result = m.compute_period_analytics(df, START, END, _ACCOUNT)
        assert result["campaigns_closed"] == 0
        assert result["excluded_count"] == 1
        assert result["excluded_pnl"] == pytest.approx(50.0)
        assert result["ok"] is True


class TestStatBucketExclusion:
    """
    Issue F (SYSTEM_AUDIT §5.6): analytics_engine must exclude ALGO_OBSERVED
    and DATA_INCOMPLETE campaigns from Win Rate / Expectancy / Profit Factor,
    matching AGENTS.md invariant #8 and the canonical filter in
    adaptive_risk_engine._is_disc / dashboard.py.
    """

    def _manual_win(self):
        # entry=100, stop=90, qty=10 → orig_risk $100; pnl=$200 → net_r +2.0
        return [
            _base_trade("m1", "BUY",  "2025-01-07", 100, 10, 0,   90, setup="EP"),
            _base_trade("m1", "SELL", "2025-01-09", 120, 10, 200,  0, setup="EP"),
        ]

    def _manual_loss(self):
        # entry=100, stop=90, qty=10 → orig_risk $100; pnl=-$50 → net_r -0.5
        return [
            _base_trade("m2", "BUY",  "2025-01-07", 100, 10, 0,   90, setup="VCP"),
            _base_trade("m2", "SELL", "2025-01-09",  95, 10, -50,  0, setup="VCP"),
        ]

    def _algo_win(self):
        # setup_type ALGO → is_algo_position → ALGO_OBSERVED bucket
        return [
            _base_trade("a1", "BUY",  "2025-01-07", 50, 20, 0,   45, setup="ALGO"),
            _base_trade("a1", "SELL", "2025-01-09", 80, 20, 600,  0, setup="ALGO"),
        ]

    def _data_incomplete(self):
        # manual setup but no initial stop → DATA_INCOMPLETE
        return [
            _base_trade("d1", "BUY",  "2025-01-07", 100, 10, 0,  0, setup="Breakout"),
            _base_trade("d1", "SELL", "2025-01-09", 130, 10, 300, 0, setup="Breakout"),
        ]

    def test_algo_excluded_from_win_rate(self):
        # 1 manual win + 1 ALGO win → countable = 1, win_rate = 1.0 (not 2/2)
        result = m.compute_period_analytics(
            _make_df(self._manual_win() + self._algo_win()), START, END, _ACCOUNT)
        assert result["campaigns_closed"] == 1
        assert result["win_rate"] == pytest.approx(1.0)
        assert result["excluded_count"] == 1

    def test_algo_excluded_from_expectancy(self):
        # manual loss (-0.5R) + ALGO huge win → expectancy reflects only the loss
        result = m.compute_period_analytics(
            _make_df(self._manual_loss() + self._algo_win()), START, END, _ACCOUNT)
        assert result["campaigns_closed"] == 1
        assert result["expectancy_r"] == pytest.approx(-0.5)
        assert result["excluded_count"] == 1

    def test_algo_excluded_from_profit_factor(self):
        # manual win + manual loss + ALGO win → PF = 200 / 50 = 4.0 (ALGO 600 not added)
        result = m.compute_period_analytics(
            _make_df(self._manual_win() + self._manual_loss() + self._algo_win()),
            START, END, _ACCOUNT)
        assert result["campaigns_closed"] == 2
        assert result["profit_factor"] == pytest.approx(4.0)

    def test_data_incomplete_excluded(self):
        # manual win + DATA_INCOMPLETE win → only the manual win counts
        result = m.compute_period_analytics(
            _make_df(self._manual_win() + self._data_incomplete()), START, END, _ACCOUNT)
        assert result["campaigns_closed"] == 1
        assert result["excluded_count"] == 1
        assert result["win_rate"] == pytest.approx(1.0)

    def test_excluded_pnl_reported(self):
        # ALGO win $600 + DATA_INCOMPLETE win $300 → excluded_pnl = $900
        result = m.compute_period_analytics(
            _make_df(self._manual_loss() + self._algo_win() + self._data_incomplete()),
            START, END, _ACCOUNT)
        assert result["excluded_count"] == 2
        assert result["excluded_pnl"] == pytest.approx(900.0)
        # Sprint-20 Step-2 — ADDITIVE manual/ALGO split of the SAME total.
        # Existing excluded_count/excluded_pnl semantics UNCHANGED above.
        assert result["excluded_count_manual"] == 1          # DATA_INCOMPLETE
        assert result["excluded_pnl_manual"] == pytest.approx(300.0)
        assert result["excluded_count_algo"] == 1            # ALGO
        assert result["excluded_pnl_algo"] == pytest.approx(600.0)
        # invariant: manual + algo == existing excluded total.
        assert (result["excluded_count_manual"]
                + result["excluded_count_algo"] == result["excluded_count"])
        assert (result["excluded_pnl_manual"] + result["excluded_pnl_algo"]
                == pytest.approx(result["excluded_pnl"]))

    def test_all_excluded_returns_empty_with_disclosure(self):
        # only ALGO + DATA_INCOMPLETE → no countable campaigns, ok stays True
        result = m.compute_period_analytics(
            _make_df(self._algo_win() + self._data_incomplete()), START, END, _ACCOUNT)
        assert result["campaigns_closed"] == 0
        assert result["ok"] is True
        assert result["excluded_count"] == 2
        assert result["excluded_pnl"] == pytest.approx(900.0)
        # Sprint-20 Step-2 — the countable.empty early-return path must ALSO
        # carry the additive split keys (founder scenario: 0 countable).
        assert result["excluded_count_manual"] == 1
        assert result["excluded_pnl_manual"] == pytest.approx(300.0)
        assert result["excluded_count_algo"] == 1
        assert result["excluded_pnl_algo"] == pytest.approx(600.0)

    def test_setup_breakdown_excludes_algo(self):
        result = m.compute_period_analytics(
            _make_df(self._manual_win() + self._algo_win()), START, END, _ACCOUNT)
        assert "ALGO" not in result["setup_breakdown"]
        assert "EP" in result["setup_breakdown"]

    def test_pure_manual_unaffected_regression(self):
        # No ALGO/incomplete → numbers identical to pre-fix behavior
        result = m.compute_period_analytics(
            _make_df(self._manual_win() + self._manual_loss()), START, END, _ACCOUNT)
        assert result["campaigns_closed"] == 2
        assert result["excluded_count"] == 0
        assert result["excluded_pnl"] == pytest.approx(0.0)
        assert result["win_rate"] == pytest.approx(0.5)
        assert result["profit_factor"] == pytest.approx(4.0)   # 200 / 50
