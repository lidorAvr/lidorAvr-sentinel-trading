"""test_setup_profile.py — Per-setup methodology parameters.

Closes Sprint 11 BLOCKERs #2 and #3 from the research audit:
  - BLOCKER #2: initial-stop 5–8% rule enforcement
  - BLOCKER #3: setup-aware dead-money thresholds (EP shorter than VCP)
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import setup_profile as sp


# ════════════════════════════════════════════════════════════════════════════════
# Profile resolution
# ════════════════════════════════════════════════════════════════════════════════

class TestProfileResolution:
    def test_vcp_returns_vcp(self):
        assert sp.get_profile("VCP").name == "VCP"

    def test_vcp_manual_collapses_to_vcp(self):
        """Both VCP and VCP_MANUAL share the methodology family."""
        assert sp.get_profile("VCP_MANUAL") is sp.VCP

    def test_ep_returns_ep(self):
        assert sp.get_profile("EP").name == "EP"

    def test_ep_manual_collapses_to_ep(self):
        assert sp.get_profile("EP_MANUAL") is sp.EP

    def test_swing_returns_swing(self):
        assert sp.get_profile("SWING").name == "SWING"

    def test_algo_returns_algo(self):
        assert sp.get_profile("ALGO").name == "ALGO"

    def test_unknown_falls_back_to_vcp(self):
        """Defensive: weird strings shouldn't crash; fall back to VCP."""
        assert sp.get_profile("WEIRD_SETUP") is sp.VCP
        assert sp.get_profile("") is sp.VCP
        assert sp.get_profile(None) is sp.VCP

    def test_case_insensitive(self):
        assert sp.get_profile("vcp") is sp.VCP
        assert sp.get_profile("ep") is sp.EP

    def test_whitespace_stripped(self):
        assert sp.get_profile("  VCP  ") is sp.VCP


# ════════════════════════════════════════════════════════════════════════════════
# Profile contracts — the values matter; pinning them
# ════════════════════════════════════════════════════════════════════════════════

class TestProfileValues:
    """Pinning specific numeric values so a silent change is caught.
    If you change a profile value, also update WAKE_UP_BRIEF / docs."""

    def test_ep_dead_money_shorter_than_vcp(self):
        """Mark's BLOCKER #3: EP must trigger dead-money BEFORE the
        21-day VCP threshold."""
        assert sp.EP.dead_money_days < sp.VCP.dead_money_days

    def test_ep_dead_money_higher_floor(self):
        """EP's R floor is higher — by day 10, EP should be working."""
        assert sp.EP.dead_money_r > sp.VCP.dead_money_r

    def test_ep_profit_protect_lower(self):
        """EP locks BE earlier than VCP — 1.5R vs 2.0R."""
        assert sp.EP.profit_protect_r < sp.VCP.profit_protect_r

    def test_ep_runner_threshold_lower(self):
        """EP rarely sees 5R — runner threshold lower."""
        assert sp.EP.runner_r < sp.VCP.runner_r

    def test_vcp_max_stop_pct_is_8(self):
        """Minervini canon: 8% max."""
        assert sp.VCP.max_initial_stop_pct == 8.0

    def test_swing_wider_stop_than_vcp(self):
        """Swing trades use wider stops by design."""
        assert sp.SWING.max_initial_stop_pct > sp.VCP.max_initial_stop_pct

    def test_algo_thresholds_neutralized(self):
        """ALGO is externally managed — thresholds should never trigger
        Sentinel management tasks. Verified by very large dead_money_days
        and very negative dead_money_r."""
        assert sp.ALGO.dead_money_days > 100
        assert sp.ALGO.dead_money_r < 0

    def test_profiles_are_frozen(self):
        """Frozen dataclasses can't be mutated at runtime."""
        with pytest.raises(Exception):
            sp.VCP.dead_money_days = 999


# ════════════════════════════════════════════════════════════════════════════════
# validate_initial_stop
# ════════════════════════════════════════════════════════════════════════════════

class TestValidateInitialStop:
    def test_5pct_stop_vcp_in_spec(self):
        """Entry 100, stop 95 = 5% stop, well within VCP's 8% limit."""
        info = sp.validate_initial_stop(100.0, 95.0, "VCP")
        assert info["in_spec"] is True
        assert info["grade"] == sp.STOP_GRADE_IN_SPEC
        assert info["stop_pct"] == 5.0

    def test_8pct_stop_vcp_at_boundary_in_spec(self):
        """Boundary case: exactly 8% should still be in_spec."""
        info = sp.validate_initial_stop(100.0, 92.0, "VCP")
        assert info["in_spec"] is True

    def test_9pct_stop_vcp_marginal(self):
        """8.5% is between max (8) and marginal_ceil (10)."""
        info = sp.validate_initial_stop(100.0, 91.5, "VCP")
        assert info["grade"] == sp.STOP_GRADE_MARGINAL
        assert info["in_spec"] is False

    def test_15pct_stop_vcp_out_of_spec(self):
        """15% stop is way past Minervini methodology."""
        info = sp.validate_initial_stop(100.0, 85.0, "VCP")
        assert info["grade"] == sp.STOP_GRADE_OUT_OF_SPEC

    def test_30pct_stop_vcp_out_of_spec(self):
        """The "deceptive 1R" scenario from the audit."""
        info = sp.validate_initial_stop(100.0, 70.0, "VCP")
        assert info["grade"] == sp.STOP_GRADE_OUT_OF_SPEC
        assert info["stop_pct"] == 30.0

    def test_ep_uses_8pct_max_like_vcp(self):
        """EP uses same tightness as VCP (both 8%)."""
        info_ep  = sp.validate_initial_stop(100.0, 92.0, "EP")
        info_vcp = sp.validate_initial_stop(100.0, 92.0, "VCP")
        assert info_ep["in_spec"] == info_vcp["in_spec"]

    def test_swing_wider_max(self):
        """SWING tolerates wider stops (10%)."""
        info = sp.validate_initial_stop(100.0, 91.0, "SWING")
        # 9% stop, SWING max is 10% → in_spec
        assert info["in_spec"] is True

    def test_missing_entry(self):
        info = sp.validate_initial_stop(0, 90.0, "VCP")
        assert info["grade"] == sp.STOP_GRADE_MISSING

    def test_missing_stop(self):
        info = sp.validate_initial_stop(100.0, 0, "VCP")
        assert info["grade"] == sp.STOP_GRADE_MISSING

    def test_stop_above_entry_treated_as_missing(self):
        """Doesn't make sense for a long — treat as missing data."""
        info = sp.validate_initial_stop(100.0, 105.0, "VCP")
        assert info["grade"] == sp.STOP_GRADE_MISSING

    def test_none_inputs_safe(self):
        info = sp.validate_initial_stop(None, None, "VCP")
        assert info["grade"] == sp.STOP_GRADE_MISSING

    def test_unknown_setup_uses_vcp_threshold(self):
        info = sp.validate_initial_stop(100.0, 92.0, "MYSTERY")
        # MYSTERY falls back to VCP (8%); 8% stop is in_spec
        assert info["in_spec"] is True

    def test_label_is_hebrew(self):
        info = sp.validate_initial_stop(100.0, 70.0, "VCP")
        assert "מתודולוגיה" in info["label_he"]

    def test_label_for_in_spec(self):
        info = sp.validate_initial_stop(100.0, 95.0, "VCP")
        assert "✅" in info["label_he"]

    def test_label_for_out_of_spec(self):
        info = sp.validate_initial_stop(100.0, 70.0, "VCP")
        assert "🔴" in info["label_he"]
