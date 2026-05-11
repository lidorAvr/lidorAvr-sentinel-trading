"""
Tests for compute_data_quality_badge() in engine_core
and fmt_actionability() / fmt_data_quality_badge() in telegram_formatters.
All tests are deterministic and require no network calls.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import engine_core as ec
from telegram_formatters import fmt_actionability, fmt_data_quality_badge, ACTIONABILITY_LABELS


class TestComputeDataQualityBadge:
    def test_algo_returns_external(self):
        primary, risk_badge, label = ec.compute_data_quality_badge("ALGO", 100.0, 10, 0, 0, 500)
        assert primary == "🟠"
        assert label == "External"

    def test_algo_with_stop_still_external(self):
        primary, risk_badge, label = ec.compute_data_quality_badge("ALGO", 100.0, 10, 90.0, 95.0, 500)
        assert primary == "🟠"

    def test_verified_when_both_stops_present(self):
        primary, risk_badge, label = ec.compute_data_quality_badge("VCP", 100.0, 10, 92.0, 94.0, 500)
        assert primary == "✅"
        assert label == "Verified"

    def test_verified_includes_true_risk_badge(self):
        primary, risk_badge, label = ec.compute_data_quality_badge("VCP", 100.0, 10, 92.0, 94.0, 0)
        assert primary == "✅"
        assert risk_badge == "🧮"

    def test_partial_when_only_current_stop(self):
        primary, risk_badge, label = ec.compute_data_quality_badge("EP", 100.0, 10, 92.0, 0, 0)
        assert primary == "⚠️"
        assert label == "Partial"

    def test_partial_when_only_target_risk(self):
        primary, risk_badge, label = ec.compute_data_quality_badge("EP", 100.0, 10, 0, 0, 500)
        assert primary == "⚠️"
        assert risk_badge == "📊"

    def test_broken_when_no_price(self):
        primary, risk_badge, label = ec.compute_data_quality_badge("VCP", 0, 10, 0, 0, 0)
        assert primary == "🔴"
        assert label == "Broken"

    def test_broken_when_no_qty(self):
        primary, risk_badge, label = ec.compute_data_quality_badge("VCP", 100.0, 0, 0, 0, 0)
        assert primary == "🔴"

    def test_broken_when_no_stops_and_no_target(self):
        primary, risk_badge, label = ec.compute_data_quality_badge("VCP", 100.0, 10, 0, 0, 0)
        assert primary == "🔴"

    def test_stop_above_price_not_counted(self):
        # stop > entry_price should not qualify as valid stop
        primary, risk_badge, label = ec.compute_data_quality_badge("VCP", 100.0, 10, 110.0, 0, 0)
        assert primary == "🔴"

    def test_result_is_tuple_of_three(self):
        result = ec.compute_data_quality_badge("EP", 100.0, 10, 92.0, 94.0, 500)
        assert len(result) == 3

    def test_target_risk_badge_for_target_basis(self):
        # No stop, only target_risk_usd → Target basis → 📊 badge
        primary, risk_badge, label = ec.compute_data_quality_badge("EP", 100.0, 10, 0, 0, 500)
        assert risk_badge == "📊"

    def test_no_risk_badge_when_unknown_basis(self):
        primary, risk_badge, label = ec.compute_data_quality_badge("VCP", 100.0, 10, 0, 0, 0)
        assert risk_badge == ""


class TestFmtActionability:
    def test_action_required_label(self):
        result = fmt_actionability("action_required")
        assert "פעולה נדרשת" in result
        assert "🔴" in result

    def test_review_required_label(self):
        result = fmt_actionability("review_required")
        assert "לבדוק" in result
        assert "🟡" in result

    def test_observation_only_label(self):
        result = fmt_actionability("observation_only")
        assert "מידע בלבד" in result

    def test_system_health_label(self):
        result = fmt_actionability("system_health")
        assert "בריאות מערכת" in result

    def test_external_managed_label(self):
        result = fmt_actionability("external_managed")
        assert "מנוהל חיצונית" in result

    def test_unknown_level_falls_back_gracefully(self):
        result = fmt_actionability("totally_unknown_level")
        assert "totally_unknown_level" in result

    def test_all_known_levels_covered(self):
        for level in ACTIONABILITY_LABELS:
            result = fmt_actionability(level)
            assert len(result) > 5

    def test_result_is_string(self):
        assert isinstance(fmt_actionability("action_required"), str)


class TestFmtDataQualityBadge:
    def test_all_parts_present(self):
        result = fmt_data_quality_badge("✅", "🧮", "Verified")
        assert "✅" in result
        assert "🧮" in result
        assert "Verified" in result

    def test_empty_risk_badge_excluded(self):
        result = fmt_data_quality_badge("🔴", "", "Broken")
        assert "🔴" in result
        assert "Broken" in result
        # no extra space-separated empty token
        parts = result.split()
        assert all(p for p in parts)

    def test_label_in_backticks(self):
        result = fmt_data_quality_badge("⚠️", "📊", "Partial")
        assert "`Partial`" in result
