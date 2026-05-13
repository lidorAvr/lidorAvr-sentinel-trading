"""
Phase 4 — ALGO Oversight tests.

Tests compute_algo_oversight_summary() (engine_core.py) and the three
new ALGO alert text functions (risk_monitor.py).
All tests are pure — no Telegram, no DB, no yfinance.
"""

import sys
import types
import pytest

# ── Stub heavy dependencies before importing risk_monitor ────────────────────
for mod_name in ["telebot", "supabase", "dotenv"]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

sys.modules["supabase"].create_client = lambda *a, **k: None  # type: ignore
sys.modules["dotenv"].load_dotenv = lambda *a, **k: None  # type: ignore

class _FakeBot:
    def __init__(self, *a, **k): pass
sys.modules["telebot"].TeleBot = _FakeBot  # type: ignore

import engine_core as ec
import risk_monitor as rm


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pos(symbol="QQQ", pos_value=1000.0, oversight_score=60, open_r=-0.5,
         campaign_id="C1"):
    return {
        "symbol": symbol,
        "pos_value": pos_value,
        "oversight_score": oversight_score,
        "open_r": open_r,
        "campaign_id": campaign_id,
    }


# ── compute_algo_oversight_summary ────────────────────────────────────────────

class TestAlgoOversightSummaryEmpty:
    def test_empty_returns_zero_positions(self):
        r = ec.compute_algo_oversight_summary([], 10000.0)
        assert r["n_positions"] == 0

    def test_empty_visibility_not_below_threshold(self):
        r = ec.compute_algo_oversight_summary([], 10000.0)
        assert r["visibility_below_threshold"] is False

    def test_empty_no_cap_breaches(self):
        r = ec.compute_algo_oversight_summary([], 10000.0)
        assert r["symbol_cap_breaches"] == []

    def test_empty_no_deep_loss(self):
        r = ec.compute_algo_oversight_summary([], 10000.0)
        assert r["deep_loss_positions"] == []


class TestAlgoOversightSummarySingle:
    def setup_method(self):
        # QQQ cap = 10%, 1000/10000 = 10% — at cap, not breaching
        self.r = ec.compute_algo_oversight_summary([_pos("QQQ", 1000.0, 60, -0.5)], 10000.0)

    def test_n_positions(self):
        assert self.r["n_positions"] == 1

    def test_exposure_pct(self):
        assert abs(self.r["total_exposure_pct"] - 10.0) < 0.01

    def test_visibility_avg(self):
        assert self.r["visibility_avg"] == 60.0

    def test_visibility_not_below_threshold_at_60(self):
        assert self.r["visibility_below_threshold"] is False

    def test_no_cap_breach_at_exact_limit(self):
        assert self.r["symbol_cap_breaches"] == []

    def test_no_deep_loss_at_minus_0_5(self):
        assert self.r["deep_loss_positions"] == []


class TestAlgoOversightSummaryCapBreach:
    def test_qqq_breach_at_11_pct(self):
        # QQQ cap = 10%, 1100/10000 = 11% → breach
        r = ec.compute_algo_oversight_summary([_pos("QQQ", 1100.0)], 10000.0)
        assert len(r["symbol_cap_breaches"]) == 1
        assert r["symbol_cap_breaches"][0]["symbol"] == "QQQ"
        assert r["symbol_cap_breaches"][0]["cap_pct"] == 10.0
        assert r["symbol_cap_breaches"][0]["exposure_pct"] > 10.0

    def test_tsla_breach_at_8_pct(self):
        # TSLA cap = 7%, 800/10000 = 8% → breach
        r = ec.compute_algo_oversight_summary([_pos("TSLA", 800.0)], 10000.0)
        assert len(r["symbol_cap_breaches"]) == 1
        assert r["symbol_cap_breaches"][0]["symbol"] == "TSLA"

    def test_no_breach_for_unknown_symbol(self):
        # Unknown symbol cap = 100%, so no breach
        r = ec.compute_algo_oversight_summary([_pos("UNKNOWN", 9000.0)], 10000.0)
        assert r["symbol_cap_breaches"] == []

    def test_two_breaches_detected(self):
        positions = [_pos("QQQ", 1100.0), _pos("TSLA", 800.0)]
        r = ec.compute_algo_oversight_summary(positions, 10000.0)
        assert len(r["symbol_cap_breaches"]) == 2

    def test_same_symbol_aggregated(self):
        # Two QQQ positions: 600+600 = 1200/10000 = 12% → breach
        positions = [
            _pos("QQQ", 600.0, campaign_id="C1"),
            _pos("QQQ", 600.0, campaign_id="C2"),
        ]
        r = ec.compute_algo_oversight_summary(positions, 10000.0)
        assert len(r["symbol_cap_breaches"]) == 1
        assert r["symbol_cap_breaches"][0]["exposure_pct"] == 12.0


class TestAlgoOversightSummaryDeepLoss:
    def test_deep_loss_at_minus_2(self):
        r = ec.compute_algo_oversight_summary([_pos("QQQ", 1000.0, open_r=-2.0)], 10000.0)
        assert len(r["deep_loss_positions"]) == 1
        assert r["deep_loss_positions"][0]["symbol"] == "QQQ"

    def test_deep_loss_only_below_minus_2(self):
        r = ec.compute_algo_oversight_summary([_pos("QQQ", 1000.0, open_r=-1.9)], 10000.0)
        assert r["deep_loss_positions"] == []

    def test_multiple_deep_losses(self):
        positions = [
            _pos("QQQ", 1000.0, open_r=-2.5, campaign_id="C1"),
            _pos("TSLA", 700.0, open_r=-3.0, campaign_id="C2"),
            _pos("PLTR", 500.0, open_r=-0.5, campaign_id="C3"),
        ]
        r = ec.compute_algo_oversight_summary(positions, 10000.0)
        assert len(r["deep_loss_positions"]) == 2


class TestAlgoOversightSummaryVisibility:
    def test_visibility_below_30_flagged(self):
        # score=20 means no target_risk_usd — truly blind, should alert
        r = ec.compute_algo_oversight_summary([_pos(oversight_score=20)], 10000.0)
        assert r["visibility_below_threshold"] is True

    def test_visibility_avg_calculated(self):
        positions = [_pos(oversight_score=40), _pos(oversight_score=60)]
        r = ec.compute_algo_oversight_summary(positions, 10000.0)
        assert r["visibility_avg"] == 50.0

    def test_visibility_40_is_not_below_threshold(self):
        # 40 is the normal/healthy ALGO max (no real stop known) — must NOT alert
        r = ec.compute_algo_oversight_summary([_pos(oversight_score=40)], 10000.0)
        assert r["visibility_below_threshold"] is False

    def test_visibility_60_is_not_below_threshold(self):
        r = ec.compute_algo_oversight_summary([_pos(oversight_score=60)], 10000.0)
        assert r["visibility_below_threshold"] is False


class TestAlgoOversightSummaryExposure:
    def test_total_exposure_usd(self):
        positions = [_pos("QQQ", 500.0), _pos("TSLA", 300.0)]
        r = ec.compute_algo_oversight_summary(positions, 10000.0)
        assert r["total_exposure_usd"] == 800.0

    def test_total_exposure_pct(self):
        positions = [_pos("QQQ", 500.0), _pos("TSLA", 300.0)]
        r = ec.compute_algo_oversight_summary(positions, 10000.0)
        assert abs(r["total_exposure_pct"] - 8.0) < 0.01

    def test_zero_acc_size_no_crash(self):
        r = ec.compute_algo_oversight_summary([_pos()], 0.0)
        assert r["total_exposure_pct"] == 0.0


# ── _algo_deep_loss_alert ─────────────────────────────────────────────────────

class TestAlgoDeepLossAlert:
    def _call(self, open_r=-2.3):
        return rm._algo_deep_loss_alert("QQQ", open_r)

    def test_contains_symbol(self):
        assert "QQQ" in self._call()

    def test_contains_open_r(self):
        assert "2.3" in self._call() or "-2.3" in self._call()

    def test_no_sell_instruction(self):
        text = self._call()
        assert "למכור" not in text
        assert "לצאת" not in text

    def test_no_stop_change_instruction(self):
        text = self._call()
        assert "שנה סטופ" not in text
        assert "הקדם סטופ" not in text

    def test_oversight_language_present(self):
        text = self._call()
        assert "פיקוח" in text or "Sentinel" in text

    def test_returns_string(self):
        assert isinstance(self._call(), str)


# ── _algo_loss_streak_alert ───────────────────────────────────────────────────

class TestAlgoLossStreakAlert:
    def _call_yellow(self):
        return rm._algo_loss_streak_alert("TSLA", -0.8, 3, "yellow")

    def _call_orange(self):
        return rm._algo_loss_streak_alert("TSLA", -1.2, 5, "orange")

    def test_yellow_contains_symbol(self):
        assert "TSLA" in self._call_yellow()

    def test_orange_contains_symbol(self):
        assert "TSLA" in self._call_orange()

    def test_yellow_contains_streak_count(self):
        assert "3" in self._call_yellow()

    def test_orange_contains_streak_count(self):
        assert "5" in self._call_orange()

    def test_orange_has_stronger_heading(self):
        # Orange level should have red circle or stronger indicator
        assert "🔴" in self._call_orange()

    def test_yellow_no_sell_instruction(self):
        text = self._call_yellow()
        assert "למכור" not in text

    def test_orange_no_sell_instruction(self):
        text = self._call_orange()
        assert "למכור" not in text

    def test_oversight_language(self):
        text = self._call_yellow()
        assert "Sentinel" in text or "פיקוח" in text

    def test_returns_string(self):
        assert isinstance(self._call_yellow(), str)
        assert isinstance(self._call_orange(), str)


# ── _algo_visibility_alert ────────────────────────────────────────────────────

class TestAlgoVisibilityAlert:
    def _call(self, visibility_avg=45.0, n_positions=3):
        return rm._algo_visibility_alert(visibility_avg, n_positions)

    def test_contains_visibility_score(self):
        assert "45" in self._call()

    def test_contains_position_count(self):
        assert "3" in self._call()

    def test_no_sell_instruction(self):
        text = self._call()
        assert "למכור" not in text

    def test_oversight_language(self):
        text = self._call()
        assert "ALGO Oversight" in text or "פיקוח" in text or "Sentinel" in text

    def test_returns_string(self):
        assert isinstance(self._call(), str)


# ── Integration: consistency checks ──────────────────────────────────────────

class TestAlgoOversightIntegration:
    def test_qqq_at_exactly_cap_no_breach(self):
        # QQQ cap = 10.0%, 1000/10000 = 10.0% — NOT a breach (> required)
        r = ec.compute_algo_oversight_summary([_pos("QQQ", 1000.0)], 10000.0)
        assert r["symbol_cap_breaches"] == []

    def test_qqq_one_basis_point_above_cap_is_breach(self):
        # 1001/10000 = 10.01% > 10% → breach
        r = ec.compute_algo_oversight_summary([_pos("QQQ", 1001.0)], 10000.0)
        assert len(r["symbol_cap_breaches"]) == 1

    def test_pltr_cap_is_6_pct(self):
        # PLTR cap = 6%
        r = ec.compute_algo_oversight_summary([_pos("PLTR", 601.0)], 10000.0)
        assert len(r["symbol_cap_breaches"]) == 1
        assert r["symbol_cap_breaches"][0]["cap_pct"] == 6.0

    def test_no_algo_exit_instruction_in_any_alert(self):
        """All Phase 4 alerts must never issue exit commands."""
        deep = rm._algo_deep_loss_alert("QQQ", -3.0)
        streak = rm._algo_loss_streak_alert("QQQ", -1.5, 5, "orange")
        vis = rm._algo_visibility_alert(35.0, 2)
        for text in [deep, streak, vis]:
            assert "למכור" not in text
            assert "לצאת" not in text
            assert "הכנס" not in text
