"""
Tests for compute_risk_deviation() and compute_giveback_from_peak().
All tests are deterministic and require no network calls.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import engine_core as ec


class TestComputeRiskDeviation:
    def test_no_loss_returns_normal(self):
        result = ec.compute_risk_deviation(0, 100)
        assert result["classification"] == "normal"
        assert result["deviation_r"] == 0.0

    def test_profit_treated_as_no_deviation(self):
        result = ec.compute_risk_deviation(50, 100)
        # open_pnl is positive — abs() makes deviation = 0.5R = normal
        assert result["classification"] == "normal"

    def test_exactly_1r_is_normal(self):
        result = ec.compute_risk_deviation(-100, 100)
        assert result["classification"] == "normal"
        assert result["deviation_r"] == 1.0

    def test_1_25r_is_minor(self):
        result = ec.compute_risk_deviation(-125, 100)
        assert result["classification"] == "minor"
        assert result["alert_level"] == "watch"

    def test_1_5r_is_minor_boundary(self):
        result = ec.compute_risk_deviation(-150, 100)
        assert result["classification"] == "minor"

    def test_1_75r_is_moderate(self):
        result = ec.compute_risk_deviation(-175, 100)
        assert result["classification"] == "moderate"
        assert result["alert_level"] == "alert"

    def test_2r_is_moderate_boundary(self):
        result = ec.compute_risk_deviation(-200, 100)
        assert result["classification"] == "moderate"

    def test_2_5r_is_severe(self):
        result = ec.compute_risk_deviation(-250, 100)
        assert result["classification"] == "severe"
        assert result["alert_level"] == "severe"

    def test_3r_is_severe_boundary(self):
        result = ec.compute_risk_deviation(-300, 100)
        assert result["classification"] == "severe"

    def test_3_1r_is_system_event(self):
        result = ec.compute_risk_deviation(-310, 100)
        assert result["classification"] == "system_event"
        assert result["alert_level"] == "system"

    def test_zero_target_risk_returns_unknown(self):
        result = ec.compute_risk_deviation(-100, 0)
        assert result["classification"] == "unknown"
        assert result["alert_level"] == "none"

    def test_negative_target_risk_returns_unknown(self):
        result = ec.compute_risk_deviation(-100, -50)
        assert result["classification"] == "unknown"

    def test_result_has_required_keys(self):
        result = ec.compute_risk_deviation(-150, 100)
        assert "deviation_r" in result
        assert "classification" in result
        assert "label" in result
        assert "alert_level" in result

    def test_deviation_r_is_rounded(self):
        result = ec.compute_risk_deviation(-133, 100)
        assert result["deviation_r"] == 1.33

    def test_label_is_hebrew_string(self):
        result = ec.compute_risk_deviation(-250, 100)
        assert len(result["label"]) > 3


class TestComputeGivebackFromPeak:
    def test_no_peak_returns_na(self):
        result = ec.compute_giveback_from_peak(0, 0)
        assert result["classification"] == "na"
        assert result["giveback_r"] == 0.0

    def test_negative_peak_returns_na(self):
        result = ec.compute_giveback_from_peak(-1, 0)
        assert result["classification"] == "na"

    def test_no_giveback_is_natural(self):
        result = ec.compute_giveback_from_peak(5.0, 5.0)
        assert result["classification"] == "natural"
        assert result["giveback_r"] == 0.0
        assert result["giveback_pct_of_peak"] == 0.0

    def test_10_pct_giveback_is_natural(self):
        result = ec.compute_giveback_from_peak(10.0, 9.0)
        assert result["classification"] == "natural"
        assert result["giveback_pct_of_peak"] == 10.0

    def test_20_pct_giveback_is_natural_boundary(self):
        result = ec.compute_giveback_from_peak(10.0, 8.0)
        assert result["classification"] == "natural"
        assert result["giveback_pct_of_peak"] == 20.0

    def test_25_pct_giveback_is_watch(self):
        result = ec.compute_giveback_from_peak(10.0, 7.5)
        assert result["classification"] == "watch"

    def test_35_pct_giveback_is_watch_boundary(self):
        result = ec.compute_giveback_from_peak(10.0, 6.5)
        assert result["classification"] == "watch"

    def test_40_pct_giveback_is_tighten(self):
        result = ec.compute_giveback_from_peak(10.0, 6.0)
        assert result["classification"] == "tighten"

    def test_50_pct_giveback_is_tighten_boundary(self):
        result = ec.compute_giveback_from_peak(10.0, 5.0)
        assert result["classification"] == "tighten"

    def test_51_pct_giveback_is_protection_failure(self):
        result = ec.compute_giveback_from_peak(10.0, 4.9)
        assert result["classification"] == "protection_failure"

    def test_giveback_r_correct(self):
        result = ec.compute_giveback_from_peak(8.0, 5.0)
        assert result["giveback_r"] == 3.0

    def test_result_has_required_keys(self):
        result = ec.compute_giveback_from_peak(5.0, 3.0)
        assert "giveback_r" in result
        assert "giveback_pct_of_peak" in result
        assert "classification" in result
        assert "label" in result

    def test_gain_from_negative_peak_handled(self):
        # Edge: position went negative then recovered — peak was 0, now positive
        result = ec.compute_giveback_from_peak(0.0, 2.0)
        assert result["classification"] == "na"
