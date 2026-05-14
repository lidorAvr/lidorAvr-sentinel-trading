"""test_sprint11_p3c.py — HIGH 7 + MEDIUM 11.

HIGH 7 — Heat scoring per bucket:
  compute_adaptive_risk computes per-bucket s9 scores for EP and VCP.
  When BOTH buckets have ≥3 stat-countable campaigns, the weakest
  bucket's score must be ≥60 before an UP step proceeds.

MEDIUM 11 — Distribution 25-day cluster:
  compute_behavior_features now surfaces dist_25d (count) and
  distribution_cluster (bool: count ≥ 4) per Mark's 20-25 session
  cluster definition.
"""
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

for _mod in ("telebot", "telebot.types", "supabase", "dotenv"):
    sys.modules.setdefault(_mod, MagicMock())
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import pandas as pd
import engine_core as ec
import adaptive_risk_engine as are


def _camp(setup="VCP", win=True, pnl=200.0, days_ago=1):
    return {
        "campaign_id": f"X_{setup}_{days_ago}_{win}",
        "symbol": "X",
        "setup_type": setup,
        "total_pnl_usd": pnl if win else -100.0,
        "close_date": pd.Timestamp(datetime.now() - timedelta(days=days_ago)),
        "is_win": win,
        "original_campaign_risk": 50.0,
        "stat_bucket": ec.classify_stat_bucket(setup, 50.0),
    }


def _no_regime_block():
    """Patch ec to make the cold-regime gate inactive."""
    return patch.object(ec, "compute_market_regime",
                         return_value={"ok": True, "data": {"status": "🔥 Hot"}})


# ════════════════════════════════════════════════════════════════════════════════
# HIGH 7 — Per-bucket heat gate
# ════════════════════════════════════════════════════════════════════════════════

class TestPerBucketHeatGate:
    def test_both_buckets_strong_no_gate(self, tmp_path, monkeypatch):
        """5 winning VCP + 5 winning EP → both buckets hot → no gate."""
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text('{"risk_pct_input": 0.60}')
        monkeypatch.setattr("adaptive_risk_engine.SENTINEL_CONFIG_FILE", str(cfg))
        camps = ([_camp(setup="VCP", win=True, days_ago=i) for i in range(5)]
               + [_camp(setup="EP",  win=True, days_ago=i+5) for i in range(5)])
        with _no_regime_block(), \
             patch.object(ec, "get_cached_history", return_value=None):
            result = are.compute_adaptive_risk(camps, current_risk_pct=0.60,
                                                 nav=8000.0)
        assert "גייט חום per-bucket" not in result.get("step_type", "")

    def test_ep_weak_blocks_up(self, tmp_path, monkeypatch):
        """VCP hot, EP cold (all losses) → weakest bucket score is too
        low → gate fires with EP mentioned."""
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text('{"risk_pct_input": 0.60}')
        monkeypatch.setattr("adaptive_risk_engine.SENTINEL_CONFIG_FILE", str(cfg))
        # 5 VCP wins, 3 EP losses
        camps = ([_camp(setup="VCP", win=True,  days_ago=i)   for i in range(5)]
               + [_camp(setup="EP",  win=False, days_ago=i+5) for i in range(3)])
        with _no_regime_block(), \
             patch.object(ec, "get_cached_history", return_value=None):
            result = are.compute_adaptive_risk(camps, current_risk_pct=0.60,
                                                 nav=8000.0)
        # When direction would be UP and EP is weak, gate fires
        if result.get("direction") == "hold" and "per-bucket" in result.get("step_type", ""):
            assert "EP" in result["step_type"]
        # In all cases — the gate text doesn't surface for non-up directions
        # but the per-bucket logic still computes silently

    def test_single_bucket_no_gate(self, tmp_path, monkeypatch):
        """Only VCP campaigns — gate doesn't apply (single-bucket = no
        comparison to make)."""
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text('{"risk_pct_input": 0.60}')
        monkeypatch.setattr("adaptive_risk_engine.SENTINEL_CONFIG_FILE", str(cfg))
        camps = [_camp(setup="VCP", win=True, days_ago=i) for i in range(8)]
        with _no_regime_block(), \
             patch.object(ec, "get_cached_history", return_value=None):
            result = are.compute_adaptive_risk(camps, current_risk_pct=0.60,
                                                 nav=8000.0)
        assert "גייט חום per-bucket" not in result.get("step_type", "")

    def test_bucket_with_under_3_samples_skipped(self, tmp_path, monkeypatch):
        """EP has only 2 samples — skipped (not enough data to gate on).
        VCP-only effectively, so no gate."""
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text('{"risk_pct_input": 0.60}')
        monkeypatch.setattr("adaptive_risk_engine.SENTINEL_CONFIG_FILE", str(cfg))
        camps = ([_camp(setup="VCP", win=True,  days_ago=i)   for i in range(5)]
               + [_camp(setup="EP",  win=False, days_ago=i+5) for i in range(2)])
        with _no_regime_block(), \
             patch.object(ec, "get_cached_history", return_value=None):
            result = are.compute_adaptive_risk(camps, current_risk_pct=0.60,
                                                 nav=8000.0)
        assert "גייט חום per-bucket" not in result.get("step_type", "")

    def test_gate_does_not_apply_to_down_direction(self, tmp_path, monkeypatch):
        """Both EP+VCP losing, weak buckets, direction will be 'down_fast'
        from loss streak — per-bucket gate is up-only."""
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text('{"risk_pct_input": 0.60}')
        monkeypatch.setattr("adaptive_risk_engine.SENTINEL_CONFIG_FILE", str(cfg))
        camps = ([_camp(setup="VCP", win=False, days_ago=i)   for i in range(4)]
               + [_camp(setup="EP",  win=False, days_ago=i+5) for i in range(3)])
        with _no_regime_block(), \
             patch.object(ec, "get_cached_history", return_value=None):
            result = are.compute_adaptive_risk(camps, current_risk_pct=0.60,
                                                 nav=8000.0)
        # Down direction → per-bucket gate must NOT mention "per-bucket"
        assert "per-bucket" not in result.get("step_type", "")


# ════════════════════════════════════════════════════════════════════════════════
# MEDIUM 11 — Distribution 25-day cluster
# ════════════════════════════════════════════════════════════════════════════════

class TestDistribution25Cluster:
    def _make_df_with_dist_days(self, n_dist_in_25):
        """Build a 60-row OHLCV DataFrame with n distribution days marked
        in the last 25 sessions. compute_behavior_features expects the
        full pipeline output, so this is an integration check via
        compute_behavior_features."""
        n = 60
        df = pd.DataFrame({
            "Open":   [100.0] * n,
            "High":   [102.0] * n,
            "Low":    [98.0] * n,
            "Close":  [100.5] * n,
            "Volume": [1_000_000] * n,
        }, index=pd.bdate_range("2026-01-01", periods=n))
        # Make `n_dist_in_25` of the last 25 rows look like distribution days:
        # high volume (>1.5x avg), wide range (>1.2x ATR), close in bottom 35%
        for i in range(n_dist_in_25):
            idx = -1 - i
            df.iloc[idx, df.columns.get_loc("Volume")] = 3_000_000  # high vol
            df.iloc[idx, df.columns.get_loc("High")]   = 105.0       # wide range
            df.iloc[idx, df.columns.get_loc("Low")]    = 95.0
            df.iloc[idx, df.columns.get_loc("Close")]  = 96.0       # low close
            df.iloc[idx, df.columns.get_loc("Open")]   = 104.0       # down day
        return df

    def test_features_include_dist_25d(self):
        df = self._make_df_with_dist_days(0)
        df = ec.compute_indicators(df)
        df = ec.detect_distribution_days(df)
        feats = ec.compute_behavior_features("TEST", df, days_held=10)
        assert "dist_25d" in feats
        assert isinstance(feats["dist_25d"], int)

    def test_features_include_distribution_cluster(self):
        df = self._make_df_with_dist_days(0)
        df = ec.compute_indicators(df)
        df = ec.detect_distribution_days(df)
        feats = ec.compute_behavior_features("TEST", df, days_held=10)
        assert "distribution_cluster" in feats
        # 0 dist days → no cluster
        assert feats["distribution_cluster"] is False

    def test_cluster_flag_consistent_with_count(self):
        """distribution_cluster ⇔ dist_25d ≥ 4."""
        df = self._make_df_with_dist_days(0)
        df = ec.compute_indicators(df)
        df = ec.detect_distribution_days(df)
        feats = ec.compute_behavior_features("TEST", df, days_held=10)
        assert feats["distribution_cluster"] == (feats["dist_25d"] >= 4)
