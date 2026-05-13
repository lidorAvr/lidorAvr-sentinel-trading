"""
Tests for bot_helpers.py — pure helper functions.

No bot/Telegram/Supabase dependencies needed.
"""
import sys, os, json, tempfile, types as py_types
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Stub heavy deps before import (only if not yet loaded) ────────────────────
for mod in ["telebot", "supabase", "dotenv", "engine_core"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import bot_helpers as bh

# ec_stub used only inside individual tests via patch.object
_ec_fresh = {
    "nav": 10000.0, "ok": True, "is_stale": False,
    "is_critical": False, "freshness_label": "fresh",
}


# ── _read_last_log_lines ───────────────────────────────────────────────────────

class TestReadLastLogLines:
    def test_missing_file_returns_message(self):
        result = bh._read_last_log_lines("/nonexistent/path/log.txt", 10)
        assert "לא קיים" in result or "nonexistent" in result

    def test_reads_last_n_lines(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text("\n".join(str(i) for i in range(100)))
        result = bh._read_last_log_lines(str(log), 10)
        lines = result.strip().split("\n")
        assert len(lines) == 10
        assert lines[-1] == "99"

    def test_empty_file(self, tmp_path):
        log = tmp_path / "empty.log"
        log.write_text("")
        result = bh._read_last_log_lines(str(log), 10)
        assert result == "(ריק)"

    def test_full_content_when_fewer_lines(self, tmp_path):
        log = tmp_path / "short.log"
        log.write_text("line1\nline2\nline3")
        result = bh._read_last_log_lines(str(log), 50)
        assert "line1" in result
        assert "line3" in result


# ── _write_runner_decision ─────────────────────────────────────────────────────

class TestWriteRunnerDecision:
    def _make_state_file(self, tmp_path, content=None):
        f = tmp_path / "risk_monitor_state.json"
        if content is not None:
            f.write_text(json.dumps(content))
        return str(f)

    def test_creates_file_if_missing(self, tmp_path):
        path = str(tmp_path / "rm_state.json")
        with patch.object(bh, "_RM_STATE_FILE", path):
            bh._write_runner_decision("CID1", "hold")
        data = json.loads(open(path).read())
        assert data["positions"]["CID1"]["runner_decision"] == "hold"

    def test_writes_ts(self, tmp_path):
        path = str(tmp_path / "rm_state.json")
        with patch.object(bh, "_RM_STATE_FILE", path):
            bh._write_runner_decision("CID2", "hold")
        data = json.loads(open(path).read())
        assert "runner_decision_ts" in data["positions"]["CID2"]

    def test_updates_existing_entry(self, tmp_path):
        state = {"positions": {"CID3": {"runner_decision": "old"}}, "cluster": {}}
        path = self._make_state_file(tmp_path, state)
        with patch.object(bh, "_RM_STATE_FILE", path):
            bh._write_runner_decision("CID3", "hold")
        data = json.loads(open(path).read())
        assert data["positions"]["CID3"]["runner_decision"] == "hold"

    def test_does_not_raise_on_bad_path(self):
        with patch.object(bh, "_RM_STATE_FILE", "/no/such/dir/file.json"):
            bh._write_runner_decision("X", "hold")  # should silently pass


# ── get_account_settings ───────────────────────────────────────────────────────

class TestGetAccountSettings:
    def test_returns_defaults_when_missing(self, tmp_path):
        with patch("os.getcwd", return_value=str(tmp_path)):
            cfg = bh.get_account_settings()
        assert "total_deposited" in cfg
        assert "risk_pct_input" in cfg

    def test_reads_config_file(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "sentinel_config.json"
        cfg_file.write_text(json.dumps({"total_deposited": 9999.0, "risk_pct_input": 1.5}))
        monkeypatch.chdir(tmp_path)
        cfg = bh.get_account_settings()
        assert cfg["total_deposited"] == 9999.0
        assert cfg["risk_pct_input"] == 1.5


# ── get_nav_and_risk ───────────────────────────────────────────────────────────

class TestGetNavAndRisk:
    def test_returns_tuple_of_three(self):
        ec_mock = MagicMock()
        ec_mock.get_nav_with_freshness.return_value = _ec_fresh
        with patch.object(bh, 'ec', ec_mock):
            result = bh.get_nav_and_risk()
        assert len(result) == 3

    def test_acc_size_from_nav(self):
        ec_mock = MagicMock()
        ec_mock.get_nav_with_freshness.return_value = {
            "nav": 12345.0, "ok": True, "is_stale": False,
            "is_critical": False, "freshness_label": "fresh",
        }
        with patch.object(bh, 'ec', ec_mock):
            acc, risk_usd, stale = bh.get_nav_and_risk({"total_deposited": 5000.0, "risk_pct_input": 1.0})
        assert acc == 12345.0
        assert abs(risk_usd - 123.45) < 0.01

    def test_falls_back_to_deposited_when_nav_not_ok(self):
        ec_mock = MagicMock()
        ec_mock.get_nav_with_freshness.return_value = {
            "nav": 0, "ok": False, "is_stale": False,
            "is_critical": False, "freshness_label": "",
        }
        with patch.object(bh, 'ec', ec_mock):
            acc, _, _ = bh.get_nav_and_risk({"total_deposited": 8000.0, "risk_pct_input": 0.5})
        assert acc == 8000.0

    def test_stale_label_returned_when_stale(self):
        ec_mock = MagicMock()
        ec_mock.get_nav_with_freshness.return_value = {
            "nav": 10000.0, "ok": True, "is_stale": True,
            "is_critical": False, "freshness_label": "⚠️ NAV ישן",
        }
        with patch.object(bh, 'ec', ec_mock):
            _, _, label = bh.get_nav_and_risk({"total_deposited": 5000.0, "risk_pct_input": 0.5})
        assert label == "⚠️ NAV ישן"

    def test_stale_label_none_when_fresh(self):
        ec_mock = MagicMock()
        ec_mock.get_nav_with_freshness.return_value = _ec_fresh
        with patch.object(bh, 'ec', ec_mock):
            _, _, label = bh.get_nav_and_risk({"total_deposited": 5000.0, "risk_pct_input": 0.5})
        assert label is None
