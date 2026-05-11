"""Tests for account_state.py"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import account_state as m


def _write_config(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


class TestLoad:
    def test_returns_fallback_when_no_file(self, tmp_path):
        with patch.object(m, "_CONFIG_PATHS", [str(tmp_path / "nonexistent.json")]):
            result = m.load()
        assert result["ok"] is False
        assert result["nav"] == 7500.0
        assert result["nav_source"] == "fallback"

    def test_reads_nav_from_config(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        _write_config(cfg, {"nav": 12000.0, "total_deposited": 8000.0, "risk_pct_input": 1.0,
                             "nav_updated_at": datetime.now().isoformat()})
        with patch.object(m, "_CONFIG_PATHS", [str(cfg)]):
            result = m.load()
        assert result["ok"] is True
        assert result["nav"] == 12000.0
        assert result["nav_source"] == "broker"

    def test_falls_back_to_total_deposited_when_no_nav_key(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        _write_config(cfg, {"total_deposited": 9000.0, "risk_pct_input": 0.5})
        with patch.object(m, "_CONFIG_PATHS", [str(cfg)]):
            result = m.load()
        assert result["nav"] == 9000.0
        assert result["nav_source"] == "deposited"

    def test_freshness_fresh(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        ts = (datetime.now() - timedelta(hours=2)).isoformat()
        _write_config(cfg, {"nav": 10000.0, "total_deposited": 10000.0,
                             "risk_pct_input": 0.5, "nav_updated_at": ts})
        with patch.object(m, "_CONFIG_PATHS", [str(cfg)]):
            result = m.load()
        assert result["freshness"] == "fresh"
        assert result["is_stale"] is False

    def test_freshness_stale(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        ts = (datetime.now() - timedelta(hours=30)).isoformat()
        _write_config(cfg, {"nav": 10000.0, "total_deposited": 10000.0,
                             "risk_pct_input": 0.5, "nav_updated_at": ts})
        with patch.object(m, "_CONFIG_PATHS", [str(cfg)]):
            result = m.load()
        assert result["freshness"] == "stale"
        assert result["is_stale"] is True
        assert result["is_critical"] is False

    def test_freshness_critical(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        ts = (datetime.now() - timedelta(hours=60)).isoformat()
        _write_config(cfg, {"nav": 10000.0, "total_deposited": 10000.0,
                             "risk_pct_input": 0.5, "nav_updated_at": ts})
        with patch.object(m, "_CONFIG_PATHS", [str(cfg)]):
            result = m.load()
        assert result["freshness"] == "critical"
        assert result["is_stale"] is True
        assert result["is_critical"] is True

    def test_freshness_unknown_when_no_timestamp(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        _write_config(cfg, {"nav": 10000.0, "total_deposited": 10000.0, "risk_pct_input": 0.5})
        with patch.object(m, "_CONFIG_PATHS", [str(cfg)]):
            result = m.load()
        assert result["freshness"] == "unknown"

    def test_returns_fallback_on_corrupt_json(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text("this is not json")
        with patch.object(m, "_CONFIG_PATHS", [str(cfg)]):
            result = m.load()
        assert result["ok"] is False

    def test_default_risk_pct(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        _write_config(cfg, {"nav": 10000.0, "total_deposited": 10000.0})
        with patch.object(m, "_CONFIG_PATHS", [str(cfg)]):
            result = m.load()
        assert result["risk_pct_input"] == 0.5


class TestTargetRiskUsd:
    def test_calculation(self):
        account = {"nav": 10000.0, "risk_pct_input": 1.0}
        assert m.target_risk_usd(account) == 100.0

    def test_default_values(self):
        account = {"nav": 7500.0, "risk_pct_input": 0.5}
        assert m.target_risk_usd(account) == 37.5
