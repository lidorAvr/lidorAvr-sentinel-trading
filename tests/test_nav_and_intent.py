"""
Tests for:
  - get_nav_with_freshness() — NAV Phase 2
  - classify_intent()
  - classify_mistake()
All deterministic, no network calls.
"""
import sys, os, json, time, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta
from unittest.mock import patch
import engine_core as ec


# ── NAV Freshness ──────────────────────────────────────────────────────────────

class TestGetNavWithFreshness:
    def _write_cfg(self, tmpdir, nav=10000.0, nav_updated_at=None):
        cfg = {"nav": nav, "total_deposited": 7500.0, "risk_pct_input": 0.5}
        if nav_updated_at is not None:
            cfg["nav_updated_at"] = nav_updated_at
        path = os.path.join(tmpdir, "sentinel_config.json")
        with open(path, "w") as f:
            json.dump(cfg, f)
        return path

    def test_fresh_nav_ok_and_green(self):
        with tempfile.TemporaryDirectory() as td:
            ts = datetime.now().isoformat()
            path = self._write_cfg(td, nav_updated_at=ts)
            with patch.object(ec, "_CONFIG_PATHS", [path]):
                result = ec.get_nav_with_freshness()
        assert result["ok"] is True
        assert result["is_stale"] is False
        assert result["is_critical"] is False
        assert "✅" in result["freshness_label"]

    def test_stale_nav_25h_yellow(self):
        with tempfile.TemporaryDirectory() as td:
            ts = (datetime.now() - timedelta(hours=25)).isoformat()
            path = self._write_cfg(td, nav_updated_at=ts)
            with patch.object(ec, "_CONFIG_PATHS", [path]):
                result = ec.get_nav_with_freshness()
        assert result["is_stale"] is True
        assert result["is_critical"] is False
        assert "🟡" in result["freshness_label"]

    def test_critical_nav_49h_red(self):
        with tempfile.TemporaryDirectory() as td:
            ts = (datetime.now() - timedelta(hours=49)).isoformat()
            path = self._write_cfg(td, nav_updated_at=ts)
            with patch.object(ec, "_CONFIG_PATHS", [path]):
                result = ec.get_nav_with_freshness()
        assert result["is_critical"] is True
        assert "🔴" in result["freshness_label"]

    def test_no_timestamp_is_stale(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._write_cfg(td)  # no nav_updated_at
            with patch.object(ec, "_CONFIG_PATHS", [path]):
                result = ec.get_nav_with_freshness()
        assert result["is_stale"] is True
        assert "🟠" in result["freshness_label"]

    def test_missing_file_returns_fallback(self):
        with patch.object(ec, "_CONFIG_PATHS", ["/nonexistent/path.json"]):
            result = ec.get_nav_with_freshness()
        assert result["ok"] is False
        assert result["nav"] == 7500.0

    def test_nav_value_correct(self):
        with tempfile.TemporaryDirectory() as td:
            ts = datetime.now().isoformat()
            path = self._write_cfg(td, nav=12345.0, nav_updated_at=ts)
            with patch.object(ec, "_CONFIG_PATHS", [path]):
                result = ec.get_nav_with_freshness()
        assert result["nav"] == 12345.0

    def test_result_has_required_keys(self):
        with patch.object(ec, "_CONFIG_PATHS", ["/nonexistent"]):
            result = ec.get_nav_with_freshness()
        for key in ("nav", "source", "updated_at", "age_hours", "is_stale", "is_critical", "freshness_label", "ok"):
            assert key in result

    def test_age_hours_computed(self):
        with tempfile.TemporaryDirectory() as td:
            ts = (datetime.now() - timedelta(hours=5)).isoformat()
            path = self._write_cfg(td, nav_updated_at=ts)
            with patch.object(ec, "_CONFIG_PATHS", [path]):
                result = ec.get_nav_with_freshness()
        assert result["age_hours"] is not None
        assert 4.5 < result["age_hours"] < 5.5


# ── Intent Classification ──────────────────────────────────────────────────────

class TestClassifyIntent:
    def test_algo_returns_algo_signal(self):
        assert ec.classify_intent("ALGO", "full_position", 1.0, 5) == "algo_signal"

    def test_probe_state_returns_probe(self):
        assert ec.classify_intent("VCP", "probe", 0.5, 2) == "probe"

    def test_runner_state_returns_runner(self):
        assert ec.classify_intent("EP", "runner", 2.5, 10) == "runner"

    def test_earnings_hold_state(self):
        assert ec.classify_intent("VCP", "earnings_hold", 1.0, 7) == "earnings_hold"

    def test_reentry_state(self):
        assert ec.classify_intent("EP", "reentry", 0.5, 3) == "reentry"

    def test_high_r_no_addon_returns_runner(self):
        assert ec.classify_intent("VCP", "full_position", 2.5, 15, 0) == "runner"

    def test_full_position_state(self):
        assert ec.classify_intent("VCP", "full_position", 1.0, 10, 1) == "full_position"

    def test_early_starter(self):
        assert ec.classify_intent("EP", "full", 0.3, 2, 0) == "starter"

    def test_returns_string(self):
        result = ec.classify_intent("VCP", "full_position", 1.0, 5)
        assert isinstance(result, str)

    def test_intent_labels_cover_all_intents(self):
        intents = ["starter", "probe", "full_position", "runner",
                   "earnings_hold", "algo_signal", "reentry", "unknown"]
        for intent in intents:
            assert intent in ec.INTENT_LABELS


# ── Mistake Classification ─────────────────────────────────────────────────────

class TestClassifyMistake:
    def test_winning_trade_returns_none(self):
        assert ec.classify_mistake("full_position", "EP_MANUAL", 500.0, "") is None

    def test_probe_loss(self):
        result = ec.classify_mistake("probe", "EP_MANUAL", -50.0, "")
        assert result == "probe_loss"

    def test_data_incomplete_returns_data_loss(self):
        result = ec.classify_mistake("full_position", "DATA_INCOMPLETE", -200.0, "")
        assert result == "data_loss"

    def test_gap_in_notes_returns_market_loss(self):
        result = ec.classify_mistake("full_position", "EP_MANUAL", -300.0, "gap down on earnings")
        assert result == "market_loss"

    def test_sync_error_returns_system_loss(self):
        result = ec.classify_mistake("full_position", "EP_MANUAL", -100.0, "execution error in system")
        assert result == "system_loss"

    def test_plan_honored_returns_good_loss(self):
        result = ec.classify_mistake("full_position", "VCP_MANUAL", -100.0, "stop honored per plan")
        assert result == "good_loss"

    def test_violated_stop_returns_bad_loss(self):
        result = ec.classify_mistake("full_position", "VCP_MANUAL", -400.0, "violated stop rule")
        assert result == "bad_loss"

    def test_unknown_fallback(self):
        result = ec.classify_mistake("full_position", "VCP_MANUAL", -100.0, "")
        assert result == "unknown"

    def test_mistake_labels_cover_all_types(self):
        types = ["good_loss", "bad_loss", "system_loss", "market_loss",
                 "data_loss", "probe_loss", "unknown"]
        for t in types:
            assert t in ec.MISTAKE_LABELS
