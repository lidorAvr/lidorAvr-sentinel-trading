"""
Unit tests for new Minervini-aligned trade metric functions in engine_core.py.
All tests are deterministic and require no secrets or network access.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import engine_core as ec


# ──────────────────────────────────────────────────────────────
# compute_initial_risk_metrics
# ──────────────────────────────────────────────────────────────

class TestComputeInitialRiskMetrics:
    def test_normal_trade_within_range(self):
        # Entry $50, stop $47.50, 100 shares, NAV $10,000
        # Risk = 100 * $2.50 = $250 = 2.5% of $10,000 (boundary = ok)
        result = ec.compute_initial_risk_metrics(50, 47.5, 100, 10_000)
        assert result["initial_risk_usd"] == 250.0
        assert abs(result["initial_risk_pct"] - 2.5) < 0.01
        assert result["sizing_grade"] == "ok"

    def test_oversized_position(self):
        # Risk = 400 / 10,000 = 4% > 2.5% threshold
        result = ec.compute_initial_risk_metrics(50, 46, 100, 10_000)
        assert result["initial_risk_usd"] == 400.0
        assert result["sizing_grade"] == "oversized"

    def test_undersized_position(self):
        # Risk = 10 / 10,000 = 0.1% < 0.5% threshold
        result = ec.compute_initial_risk_metrics(50, 49.9, 10, 10_000)
        assert result["sizing_grade"] == "undersized"

    def test_missing_stop(self):
        result = ec.compute_initial_risk_metrics(50, 0, 100, 10_000)
        assert result["sizing_grade"] == "missing_data"
        assert result["initial_risk_usd"] == 0.0

    def test_stop_above_entry_invalid(self):
        result = ec.compute_initial_risk_metrics(50, 55, 100, 10_000)
        assert result["sizing_grade"] == "missing_data"

    def test_zero_nav(self):
        result = ec.compute_initial_risk_metrics(50, 47, 100, 0)
        assert result["sizing_grade"] == "missing_data"

    def test_minervini_sweet_spot(self):
        # 1.5% risk = ideal Minervini range
        # NAV $20,000, want $300 risk → entry $100, stop $95, qty=60
        result = ec.compute_initial_risk_metrics(100, 95, 60, 20_000)
        assert result["initial_risk_usd"] == 300.0
        assert abs(result["initial_risk_pct"] - 1.5) < 0.01
        assert result["sizing_grade"] == "ok"


# ──────────────────────────────────────────────────────────────
# compute_r_efficiency
# ──────────────────────────────────────────────────────────────

class TestComputeREfficiency:
    def test_very_efficient(self):
        # 3R in 20 days = 0.15R/day > 0.10 threshold
        result = ec.compute_r_efficiency(3.0, 20)
        assert result["r_per_day"] == pytest.approx(0.15, abs=0.001)
        assert result["efficiency_label"] == "יעיל מאוד"
        assert result["efficiency_color"] == "🔥"

    def test_efficient(self):
        # 2R in 50 days = 0.04R/day → 0.02 ≤ x < 0.05 → סביר
        result = ec.compute_r_efficiency(2.0, 50)
        assert result["r_per_day"] == pytest.approx(0.04, abs=0.001)
        assert result["efficiency_label"] == "סביר"

    def test_dead_money(self):
        # 0.3R in 20 days → r_per_day=0.015 < 0.02, days>=8, total_r<0.5 → הון מת
        result = ec.compute_r_efficiency(0.3, 20)
        assert result["r_per_day"] == pytest.approx(0.015, abs=0.001)
        assert result["efficiency_color"] == "🔴"

    def test_loss(self):
        result = ec.compute_r_efficiency(-1.5, 15)
        assert result["efficiency_label"] == "הפסד פעיל"
        assert result["efficiency_color"] == "🔴"

    def test_zero_days_guard(self):
        result = ec.compute_r_efficiency(1.0, 0)
        assert result["r_per_day"] == 0.0
        assert result["efficiency_label"] == "אין נתון"


# ──────────────────────────────────────────────────────────────
# analyze_addon_quality
# ──────────────────────────────────────────────────────────────

class TestAnalyzeAddonQuality:
    def _make_buys(self, entries):
        """entries = list of (date_str, price, qty)"""
        return [{"trade_date": d, "price": p, "quantity": q} for d, p, q in entries]

    def test_no_addon(self):
        buys = self._make_buys([("2025-01-10", 50.0, 100)])
        result = ec.analyze_addon_quality(buys)
        assert result["has_addons"] is False
        assert result["all_addons_higher"] is True
        assert result["addon_count"] == 0

    def test_valid_pyramid_up(self):
        # Minervini-correct: add-on at higher price
        buys = self._make_buys([
            ("2025-01-10", 50.0, 100),
            ("2025-01-20", 55.0, 50),   # +10% above base — correct
        ])
        result = ec.analyze_addon_quality(buys)
        assert result["has_addons"] is True
        assert result["all_addons_higher"] is True
        assert result["worst_addon_vs_base"] == pytest.approx(10.0, abs=0.1)

    def test_average_down_violation(self):
        # Minervini violation: add-on below entry price
        buys = self._make_buys([
            ("2025-01-10", 50.0, 100),
            ("2025-01-20", 46.0, 50),   # -8% below base — WRONG
        ])
        result = ec.analyze_addon_quality(buys)
        assert result["has_addons"] is True
        assert result["all_addons_higher"] is False
        assert result["worst_addon_vs_base"] < 0

    def test_mixed_addons(self):
        # One good, one bad add-on — worst_addon_vs_base should be negative
        buys = self._make_buys([
            ("2025-01-10", 50.0, 100),
            ("2025-01-15", 55.0, 30),
            ("2025-01-25", 47.0, 20),   # average down — violation
        ])
        result = ec.analyze_addon_quality(buys)
        assert result["all_addons_higher"] is False
        assert result["addon_count"] == 2

    def test_empty_list(self):
        result = ec.analyze_addon_quality([])
        assert result["has_addons"] is False

    def test_single_entry(self):
        buys = self._make_buys([("2025-01-10", 50.0, 100)])
        result = ec.analyze_addon_quality(buys)
        assert result["has_addons"] is False


# ──────────────────────────────────────────────────────────────
# compute_r_efficiency — edge cases
# ──────────────────────────────────────────────────────────────

class TestREfficiencyEdgeCases:
    def test_exactly_at_efficient_boundary(self):
        # 0.05R/day exactly → "יעיל"
        result = ec.compute_r_efficiency(1.0, 20)
        assert result["r_per_day"] == pytest.approx(0.05, abs=0.001)
        assert result["efficiency_label"] == "יעיל"

    def test_r_per_day_precision(self):
        result = ec.compute_r_efficiency(2.5, 30)
        assert result["r_per_day"] == pytest.approx(2.5 / 30, abs=0.0001)


# ──────────────────────────────────────────────────────────────
# compute_initial_risk_metrics — precision
# ──────────────────────────────────────────────────────────────

class TestInitialRiskPrecision:
    def test_rounding(self):
        result = ec.compute_initial_risk_metrics(123.45, 120.00, 37, 8500)
        expected_usd = (123.45 - 120.00) * 37
        assert result["initial_risk_usd"] == round(expected_usd, 2)
        expected_pct = (expected_usd / 8500) * 100
        assert abs(result["initial_risk_pct"] - round(expected_pct, 3)) < 0.001
