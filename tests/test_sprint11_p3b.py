"""test_sprint11_p3b.py — HIGH 8 + MEDIUM dead-money reconcile.

HIGH 8 — trail systems reconciliation:
  task_engine._task_trail_up_3r owns the 3R..runner_r territory
  (e.g., VCP: 3R..5R, EP: 2.5R..3R). Once open_r ≥ profile.runner_r,
  trail_up DEFERS to engine_core.compute_suggested_trail_stop (which
  owns MA21/MA50 trailing in RUNNER zone).

MEDIUM 10 — dead-money reconciliation:
  engine_core.map_time_efficiency now optionally accepts setup_type
  and delegates to setup_profile for the dead_money threshold —
  the same source task_engine uses. No more 8d/0.5R hardcode when
  setup is known.
"""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import engine_core as ec
import task_engine as te


def _pos(**overrides):
    base = {
        "campaign_id": "X_T1", "symbol": "X", "setup_type": "VCP",
        "current_price": 1000.0, "entry_price":   870.0,
        "stop_loss":     900.0, "initial_stop":  840.0,
        "open_r":        4.0,   "days_held":     10, "ma21": None,
    }
    base.update(overrides)
    return base


# ════════════════════════════════════════════════════════════════════════════════
# HIGH 8 — trail_up defers when open_r ≥ runner_r
# ════════════════════════════════════════════════════════════════════════════════

class TestTrailUpDefersInRunnerZone:
    def test_vcp_trail_up_fires_at_4r(self):
        """VCP runner_r=5, so trail_up STILL OWNS 4R."""
        t = te._task_trail_up_3r(_pos(open_r=4.0, setup_type="VCP",
                                        stop_loss=875.0))
        assert t is not None  # task fires

    def test_vcp_trail_up_defers_at_5r(self):
        """VCP runner_r=5, so trail_up DEFERS at 5R (engine_core takes over)."""
        t = te._task_trail_up_3r(_pos(open_r=5.0, setup_type="VCP",
                                        stop_loss=875.0))
        assert t is None

    def test_vcp_trail_up_defers_at_8r(self):
        """8R is deep in runner zone — trail_up must stay silent."""
        t = te._task_trail_up_3r(_pos(open_r=8.0, setup_type="VCP",
                                        stop_loss=875.0))
        assert t is None

    def test_ep_trail_up_defers_at_3r(self):
        """EP runner_r=3, so trail_up DEFERS at 3R."""
        t = te._task_trail_up_3r(_pos(open_r=3.0, setup_type="EP",
                                        stop_loss=875.0))
        assert t is None

    def test_ep_trail_up_fires_at_2_5r(self):
        """EP profit_protect=1.5, trail trigger=2.5, runner_r=3 →
        2.5R fires."""
        # Note: at 2.5R, stop > entry; check both conditions met
        t = te._task_trail_up_3r(_pos(open_r=2.5, setup_type="EP",
                                        stop_loss=875.0, entry_price=870.0,
                                        initial_stop=840.0))
        # 2.5 ≥ trail_trigger (1.5+1=2.5), 2.5 < runner_r (3.0) → fires
        assert t is not None


# ════════════════════════════════════════════════════════════════════════════════
# MEDIUM 10 — map_time_efficiency setup-aware
# ════════════════════════════════════════════════════════════════════════════════

class TestMapTimeEfficiencySetupAware:
    def test_ep_dead_money_at_d11(self):
        """EP threshold (10d/1.5R): 11d with open_r 0 → dead_money."""
        result = ec.map_time_efficiency(11, 0.0, setup_type="EP")
        assert result == "dead_money"

    def test_ep_alive_at_d11_with_r_above_1_5(self):
        """EP profile: 11d but 2R → alive."""
        result = ec.map_time_efficiency(11, 2.0, setup_type="EP")
        assert result == "ok"  # well above the floor; not slow because 11<15

    def test_vcp_alive_at_d11_below_old_threshold(self):
        """VCP 11d with 0.4R → NOT dead_money (VCP threshold is 21d > 0.3R)."""
        result = ec.map_time_efficiency(11, 0.4, setup_type="VCP")
        # The legacy 8d/0.5R rule would have called this 'dead_money'.
        # The new setup-aware version says: VCP threshold is 21d.
        assert result != "dead_money"

    def test_vcp_dead_money_at_d22(self):
        """VCP at 22d/0.2R → dead_money."""
        result = ec.map_time_efficiency(22, 0.2, setup_type="VCP")
        assert result == "dead_money"

    def test_no_setup_falls_back_to_legacy(self):
        """When setup_type is None, the legacy 8d/0.5R fires."""
        result = ec.map_time_efficiency(9, 0.4)
        assert result == "dead_money"

    def test_unknown_setup_falls_back_to_vcp(self):
        """Unknown setup → setup_profile.get_profile falls to VCP."""
        # 11d at 0.4R: VCP profile says no dead-money (under 21d)
        result = ec.map_time_efficiency(11, 0.4, setup_type="MYSTERY")
        assert result != "dead_money"

    def test_slow_classification_unchanged(self):
        """The slow classification (15d/<1R) is unchanged."""
        assert ec.map_time_efficiency(16, 0.8, setup_type="VCP") == "slow"

    def test_ok_classification(self):
        """Working position: 5d at 1.2R → ok."""
        assert ec.map_time_efficiency(5, 1.2, setup_type="VCP") == "ok"
