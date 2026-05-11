"""
Tests for classify_stat_bucket(), is_stat_countable(), is_discretionary_bucket(),
and compute_algo_risk_oversight_score().
All tests are deterministic and require no network calls.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import engine_core as ec


class TestClassifyStatBucket:
    def test_algo_returns_algo_observed(self):
        assert ec.classify_stat_bucket("ALGO", 500, 500) == "ALGO_OBSERVED"

    def test_algo_without_risk_still_algo(self):
        assert ec.classify_stat_bucket("ALGO", 0, 0) == "ALGO_OBSERVED"

    def test_vcp_with_risk_returns_vcp_manual(self):
        assert ec.classify_stat_bucket("VCP", 300, 500) == "VCP_MANUAL"

    def test_ep_with_risk_returns_ep_manual(self):
        assert ec.classify_stat_bucket("EP", 300, 500) == "EP_MANUAL"

    def test_breakout_with_risk_returns_breakout_manual(self):
        assert ec.classify_stat_bucket("BREAKOUT", 300, 500) == "BREAKOUT_MANUAL"

    def test_vcp_without_risk_returns_data_incomplete(self):
        assert ec.classify_stat_bucket("VCP", 0, 500) == "DATA_INCOMPLETE"

    def test_ep_without_risk_returns_data_incomplete(self):
        assert ec.classify_stat_bucket("EP", 0, 0) == "DATA_INCOMPLETE"

    def test_unknown_setup_no_risk_returns_data_incomplete(self):
        assert ec.classify_stat_bucket("UNKNOWN", 0, 0) == "DATA_INCOMPLETE"

    def test_empty_setup_no_risk_returns_data_incomplete(self):
        assert ec.classify_stat_bucket("", 0, 0) == "DATA_INCOMPLETE"

    def test_custom_setup_with_risk_returns_manual_suffix(self):
        bucket = ec.classify_stat_bucket("SWING", 200, 500)
        assert bucket.endswith("_MANUAL")

    def test_algo_case_insensitive(self):
        assert ec.classify_stat_bucket("algo", 0, 0) == "ALGO_OBSERVED"


class TestIsStatCountable:
    def test_vcp_manual_is_countable(self):
        assert ec.is_stat_countable("VCP_MANUAL") is True

    def test_ep_manual_is_countable(self):
        assert ec.is_stat_countable("EP_MANUAL") is True

    def test_algo_not_countable(self):
        assert ec.is_stat_countable("ALGO_OBSERVED") is False

    def test_data_incomplete_not_countable(self):
        assert ec.is_stat_countable("DATA_INCOMPLETE") is False


class TestIsDiscretionaryBucket:
    def test_vcp_manual_is_discretionary(self):
        assert ec.is_discretionary_bucket("VCP_MANUAL") is True

    def test_ep_manual_is_discretionary(self):
        assert ec.is_discretionary_bucket("EP_MANUAL") is True

    def test_algo_not_discretionary(self):
        assert ec.is_discretionary_bucket("ALGO_OBSERVED") is False

    def test_data_incomplete_not_discretionary(self):
        assert ec.is_discretionary_bucket("DATA_INCOMPLETE") is False


class TestComputeAlgoRiskOversightScore:
    def test_perfect_score_all_data_present(self):
        result = ec.compute_algo_risk_oversight_score("QQQ", 500, 300, 0, 1.5, 8)
        assert result["score"] == 100

    def test_zero_score_no_data(self):
        result = ec.compute_algo_risk_oversight_score("UNKNOWN_SYM", 0, 0, 0, 0, None)
        assert result["score"] == 0

    def test_known_symbol_adds_20(self):
        result_known = ec.compute_algo_risk_oversight_score("QQQ", 0, 0, 0, 0, None)
        result_unknown = ec.compute_algo_risk_oversight_score("XYZABC", 0, 0, 0, 0, None)
        assert result_known["score"] == result_unknown["score"] + 20

    def test_target_risk_known_adds_20(self):
        r1 = ec.compute_algo_risk_oversight_score("XYZABC", 0, 300, 0, 0, None)
        r2 = ec.compute_algo_risk_oversight_score("XYZABC", 0, 0, 0, 0, None)
        assert r1["score"] == r2["score"] + 20

    def test_pnl_present_adds_20(self):
        r1 = ec.compute_algo_risk_oversight_score("XYZABC", 500, 0, 0, 0, None)
        r2 = ec.compute_algo_risk_oversight_score("XYZABC", 0, 0, 0, 0, None)
        assert r1["score"] == r2["score"] + 20

    def test_quality_recorded_adds_20(self):
        r1 = ec.compute_algo_risk_oversight_score("XYZABC", 0, 0, 0, 0, 7)
        r2 = ec.compute_algo_risk_oversight_score("XYZABC", 0, 0, 0, 0, None)
        assert r1["score"] == r2["score"] + 20

    def test_score_range_0_to_100(self):
        for sym in ["QQQ", "TSLA", "UNKNOWN"]:
            for pnl in [0, 100, -200]:
                result = ec.compute_algo_risk_oversight_score(sym, pnl, 300, 0, 1.0, 8)
                assert 0 <= result["score"] <= 100

    def test_result_has_required_keys(self):
        result = ec.compute_algo_risk_oversight_score("QQQ", 100, 300, 0, 1.0, 8)
        assert "score" in result
        assert "label" in result
        assert "details" in result

    def test_label_is_hebrew(self):
        result = ec.compute_algo_risk_oversight_score("QQQ", 500, 300, 0, 1.5, 8)
        assert len(result["label"]) > 3
        # label should contain a Hebrew character
        assert any('֐' <= c <= '׿' for c in result["label"])

    def test_high_score_gets_green_label(self):
        result = ec.compute_algo_risk_oversight_score("QQQ", 500, 300, 0, 1.5, 8)
        assert "🟢" in result["label"]

    def test_zero_score_gets_red_label(self):
        result = ec.compute_algo_risk_oversight_score("XYZABC", 0, 0, 0, 0, None)
        assert "🔴" in result["label"]
