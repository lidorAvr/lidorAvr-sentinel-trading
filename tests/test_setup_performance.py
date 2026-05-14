"""test_setup_performance.py — Per-setup breakdown for /setup_stats."""
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

for _mod in ("telebot", "telebot.types", "supabase", "dotenv"):
    sys.modules.setdefault(_mod, MagicMock())
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import setup_performance as sp
import engine_core as ec


def _camp(setup="VCP", pnl=100.0, risk=50.0, win=True):
    return {
        "campaign_id": f"C_{setup}_{pnl}",
        "symbol":      "TEST",
        "setup_type":  setup,
        "total_pnl_usd": pnl,
        "close_date":  datetime.now(),
        "is_win":      win,
        "original_campaign_risk": risk,
        "stat_bucket": ec.classify_stat_bucket(setup, risk),
    }


class TestNormalize:
    def test_vcp_manual_collapses_to_vcp(self):
        assert sp._normalize("VCP_MANUAL") == "VCP"

    def test_lowercase_normalized(self):
        assert sp._normalize("ep") == "EP"

    def test_whitespace_stripped(self):
        assert sp._normalize("  VCP  ") == "VCP"

    def test_empty_stays_empty(self):
        assert sp._normalize("") == ""

    def test_none_safe(self):
        assert sp._normalize(None) == ""


class TestComputeBreakdown:
    def test_empty_input(self):
        assert sp.compute_setup_breakdown([]) == {}

    def test_single_setup_single_winner(self):
        out = sp.compute_setup_breakdown([_camp(setup="VCP", pnl=100, risk=50, win=True)])
        assert "VCP" in out
        v = out["VCP"]
        assert v["n"] == 1
        assert v["wins"] == 1
        assert v["losses"] == 0
        assert v["win_rate"] == 1.0
        assert v["total_pnl_usd"] == 100.0
        assert v["avg_r"] == 2.0  # 100 / 50 = 2R

    def test_mixed_setups_grouped(self):
        camps = [
            _camp(setup="VCP", pnl=200, risk=50, win=True),
            _camp(setup="EP",  pnl=150, risk=50, win=True),
            _camp(setup="VCP", pnl=-50, risk=50, win=False),
        ]
        out = sp.compute_setup_breakdown(camps)
        assert out["VCP"]["n"] == 2
        assert out["EP"]["n"]  == 1
        assert out["VCP"]["win_rate"] == 0.5

    def test_vcp_manual_merges_with_vcp(self):
        out = sp.compute_setup_breakdown([
            _camp(setup="VCP",         pnl=100, risk=50, win=True),
            _camp(setup="VCP_MANUAL",  pnl=200, risk=50, win=True),
        ])
        # Both collapse to "VCP" bucket
        assert "VCP" in out
        assert "VCP_MANUAL" not in out
        assert out["VCP"]["n"] == 2

    def test_zero_risk_excluded_from_r_aggregate(self):
        camps = [
            _camp(setup="VCP", pnl=100, risk=0, win=True),     # no R
            _camp(setup="VCP", pnl=200, risk=50, win=True),    # R=4
        ]
        out = sp.compute_setup_breakdown(camps)
        # avg_r is over the 1 campaign with valid risk
        assert out["VCP"]["avg_r"] == 4.0
        # But n includes both
        assert out["VCP"]["n"] == 2

    def test_algo_marked_not_stat_countable(self):
        out = sp.compute_setup_breakdown([_camp(setup="ALGO", pnl=100, risk=50, win=True)])
        assert out["ALGO"]["stat_countable"] is False

    def test_vcp_is_stat_countable(self):
        out = sp.compute_setup_breakdown([_camp(setup="VCP", pnl=100, risk=50, win=True)])
        assert out["VCP"]["stat_countable"] is True

    def test_payoff_computed_correctly(self):
        camps = [
            _camp(setup="VCP", pnl=300, risk=50, win=True),    # avg_win=300
            _camp(setup="VCP", pnl=-50, risk=50, win=False),   # avg_loss=50
        ]
        out = sp.compute_setup_breakdown(camps)
        assert out["VCP"]["payoff"] == 6.0  # 300/50

    def test_payoff_zero_when_no_losses(self):
        out = sp.compute_setup_breakdown([
            _camp(setup="VCP", pnl=100, risk=50, win=True),
            _camp(setup="VCP", pnl=200, risk=50, win=True),
        ])
        assert out["VCP"]["payoff"] == 0.0  # no losses → undefined

    def test_total_r_sums_across_campaigns(self):
        out = sp.compute_setup_breakdown([
            _camp(setup="VCP", pnl=100, risk=50, win=True),   # +2R
            _camp(setup="VCP", pnl=-50, risk=50, win=False),  # -1R
        ])
        assert out["VCP"]["total_r"] == 1.0  # 2 + -1


class TestBestAndWorst:
    def test_returns_best_and_worst(self):
        bd = {
            "VCP": {"n": 5, "avg_r": 2.1, "stat_countable": True, "label": "VCP"},
            "EP":  {"n": 5, "avg_r": 1.3, "stat_countable": True, "label": "EP"},
        }
        best, worst = sp.best_and_worst(bd)
        assert best == "VCP" and worst == "EP"

    def test_returns_none_when_one_bucket(self):
        bd = {"VCP": {"n": 5, "avg_r": 2.0, "stat_countable": True, "label": "VCP"}}
        assert sp.best_and_worst(bd) == (None, None)

    def test_skips_non_countable(self):
        bd = {
            "VCP":  {"n": 5, "avg_r": 2.0, "stat_countable": True, "label": "VCP"},
            "ALGO": {"n": 5, "avg_r": 5.0, "stat_countable": False, "label": "ALGO"},
        }
        # Only VCP is eligible → can't pick best/worst from 1 entry
        assert sp.best_and_worst(bd) == (None, None)

    def test_skips_n_less_than_2(self):
        bd = {
            "VCP": {"n": 5, "avg_r": 2.0, "stat_countable": True, "label": "VCP"},
            "EP":  {"n": 1, "avg_r": 5.0, "stat_countable": True, "label": "EP"},
        }
        # EP has n=1, excluded → only VCP eligible → None,None
        assert sp.best_and_worst(bd) == (None, None)


class TestRender:
    def test_empty_breakdown(self):
        out = sp.render_breakdown({})
        assert "אין קמפיינים" in out

    def test_renders_setup_names(self):
        camps = [_camp(setup="VCP", pnl=100, risk=50, win=True)]
        bd = sp.compute_setup_breakdown(camps)
        out = sp.render_breakdown(bd)
        assert "VCP (Minervini)" in out
        assert "1" in out  # n

    def test_renders_insight_when_two_buckets(self):
        camps = [
            _camp(setup="VCP", pnl=200, risk=50, win=True),
            _camp(setup="VCP", pnl=150, risk=50, win=True),
            _camp(setup="EP",  pnl=50,  risk=50, win=True),
            _camp(setup="EP",  pnl=-40, risk=50, win=False),
        ]
        bd = sp.compute_setup_breakdown(camps)
        out = sp.render_breakdown(bd)
        # VCP wins → suggests larger allocation
        assert "תובנה" in out
        assert "VCP" in out

    def test_no_insight_when_one_eligible_bucket(self):
        camps = [_camp(setup="VCP", pnl=100, risk=50, win=True)]
        bd = sp.compute_setup_breakdown(camps)
        out = sp.render_breakdown(bd)
        # No insight line when there's no comparison
        assert "תובנה" not in out

    def test_non_countable_bucket_tagged(self):
        camps = [_camp(setup="ALGO", pnl=100, risk=50, win=True)]
        bd = sp.compute_setup_breakdown(camps)
        out = sp.render_breakdown(bd)
        assert "לא נכלל" in out  # non-stat-countable annotation
