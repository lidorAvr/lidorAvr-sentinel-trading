"""
Tests for ALGO Observer Mode: management_mode, risk_basis, risk_visibility_score.
These functions enforce the rule that Sentinel must not issue discretionary
management instructions to externally-managed ALGO positions.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import engine_core as ec


class TestIsAlgoPosition:
    def test_algo_setup_type_uppercase(self):
        assert ec.is_algo_position("ALGO") is True

    def test_algo_setup_type_lowercase(self):
        assert ec.is_algo_position("algo") is True

    def test_ep_is_not_algo(self):
        assert ec.is_algo_position("EP") is False

    def test_vcp_is_not_algo(self):
        assert ec.is_algo_position("VCP") is False

    def test_unknown_setup_is_not_algo(self):
        assert ec.is_algo_position("Unknown") is False

    def test_algo_symbol_with_non_algo_setup_type(self):
        # setup_type takes priority: PLTR with EP setup is manual, not ALGO
        assert ec.is_algo_position("EP", "PLTR") is False

    def test_algo_setup_type_with_known_symbol(self):
        assert ec.is_algo_position("ALGO", "PLTR") is True

    def test_algo_symbols_set_contains_known_symbols(self):
        for sym in ["QQQ", "TSLA", "JPM", "PLTR", "HOOD"]:
            assert sym in ec.ALGO_SYMBOLS

    def test_algo_symbols_excludes_discretionary_symbols(self):
        for sym in ["MRVL", "MTZ", "AEHR", "RVMD"]:
            assert sym not in ec.ALGO_SYMBOLS


class TestClassifyManagementMode:
    def test_algo_returns_algo_observed(self):
        assert ec.classify_management_mode("ALGO") == "algo_observed"

    def test_ep_returns_manual_managed(self):
        assert ec.classify_management_mode("EP") == "manual_managed"

    def test_vcp_returns_manual_managed(self):
        assert ec.classify_management_mode("VCP") == "manual_managed"

    def test_unknown_setup_returns_manual_managed(self):
        # Unknown setups default to manual so they get full analysis, not hidden
        assert ec.classify_management_mode("Unknown") == "manual_managed"


class TestClassifyRiskBasis:
    def test_algo_with_target_risk_returns_target(self):
        assert ec.classify_risk_basis(0, 100.0, "ALGO", target_risk_usd=50.0) == "Target"

    def test_algo_without_target_risk_returns_unknown(self):
        assert ec.classify_risk_basis(0, 100.0, "ALGO", target_risk_usd=0) == "Unknown"

    def test_ep_with_valid_stop_returns_true(self):
        assert ec.classify_risk_basis(90.0, 100.0, "EP") == "True"

    def test_ep_stop_above_price_not_true(self):
        # Stop above entry price is invalid — cannot be True basis
        assert ec.classify_risk_basis(110.0, 100.0, "EP") != "True"

    def test_ep_no_stop_with_target_returns_target(self):
        assert ec.classify_risk_basis(0, 100.0, "EP", target_risk_usd=50.0) == "Target"

    def test_ep_no_stop_no_target_returns_unknown(self):
        assert ec.classify_risk_basis(0, 100.0, "EP") == "Unknown"

    def test_stop_equal_to_price_not_true(self):
        # Stop at entry price has zero risk — invalid for True basis
        assert ec.classify_risk_basis(100.0, 100.0, "EP") != "True"


class TestComputeRiskVisibilityScore:
    def test_algo_with_target_risk_scores_40(self):
        assert ec.compute_risk_visibility_score("ALGO", 0, 100.0, 50.0) == 40

    def test_algo_without_target_risk_scores_20(self):
        assert ec.compute_risk_visibility_score("ALGO", 0, 100.0, 0) == 20

    def test_manual_with_known_stop_scores_100(self):
        assert ec.compute_risk_visibility_score("EP", 90.0, 100.0) == 100

    def test_manual_target_only_scores_60(self):
        assert ec.compute_risk_visibility_score("EP", 0, 100.0, 50.0) == 60

    def test_manual_no_stop_no_target_scores_20(self):
        assert ec.compute_risk_visibility_score("EP", 0, 100.0, 0) == 20

    def test_score_in_valid_range(self):
        for setup, stop, price, target in [
            ("ALGO", 0, 100, 50), ("EP", 90, 100, 0), ("VCP", 0, 100, 0)
        ]:
            score = ec.compute_risk_visibility_score(setup, stop, price, target)
            assert 0 <= score <= 100, f"Score {score} out of range for {setup}"
