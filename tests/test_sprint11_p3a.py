"""test_sprint11_p3a.py — HIGH 5 + HIGH 9 from the research audit.

HIGH 5 — Market regime gating:
  compute_adaptive_risk forces direction=hold when SPY/QQQ regime is
  Cold, regardless of heat. Down steps NOT gated (safety net stays fast).

HIGH 9 — Power/Weak age gate:
  map_score_to_status downgrades 🔥 Power → 🟢 Healthy when days_held < 10
  and 🟠 Weak → 🔍 Proving when days_held < 15. Hard rules (Broken) still
  surface immediately.
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

import engine_core as ec
import adaptive_risk_engine as are


# ════════════════════════════════════════════════════════════════════════════════
# HIGH 9 — map_score_to_status age gate
# ════════════════════════════════════════════════════════════════════════════════

class TestPowerWeakAgeGate:
    def test_power_label_at_day_10_or_later_intact(self):
        """A 10-day-old position scoring 90 must show 🔥 Power."""
        assert ec.map_score_to_status(90, days_held=10) == "🔥 Power"
        assert ec.map_score_to_status(90, days_held=21) == "🔥 Power"

    def test_power_downgraded_when_days_held_under_10(self):
        """A 3-day-old position can't be Power yet — downgrade to Healthy."""
        result = ec.map_score_to_status(90, days_held=3)
        assert result == "🟢 Healthy"

    def test_power_at_boundary_9_downgraded(self):
        """Boundary: day 9 still downgrades."""
        assert ec.map_score_to_status(90, days_held=9) == "🟢 Healthy"

    def test_weak_downgraded_when_days_held_under_15(self):
        """An 8-day-old position scoring 45 (Weak band) downgrades to Proving."""
        assert ec.map_score_to_status(45, days_held=8) == "🔍 Proving"

    def test_weak_label_at_day_15_or_later_intact(self):
        assert ec.map_score_to_status(45, days_held=15) == "🟠 Weak"
        assert ec.map_score_to_status(45, days_held=30) == "🟠 Weak"

    def test_healthy_label_unaffected_by_age(self):
        """Healthy/Yellow Flag are noise-tolerant labels — no age gate."""
        assert ec.map_score_to_status(75, days_held=3)  == "🟢 Healthy"
        assert ec.map_score_to_status(75, days_held=15) == "🟢 Healthy"
        assert ec.map_score_to_status(60, days_held=3)  == "🟡 Yellow Flag"

    def test_broken_fires_at_any_age(self):
        """Hard-rule failures (Broken) surface immediately — no grace."""
        assert ec.map_score_to_status(20, days_held=1)  == "🔴 Broken"
        assert ec.map_score_to_status(20, days_held=15) == "🔴 Broken"

    def test_hard_rule_overrides_age_gate(self):
        """If a hard rule says Broken, age doesn't matter."""
        hard_rule = {"status": "🔴 Broken", "trigger": "test"}
        assert ec.map_score_to_status(90, hard_rule=hard_rule,
                                       days_held=21) == "🔴 Broken"

    def test_default_days_held_is_old_enough(self):
        """Existing callers (which don't pass days_held) get the OLD behavior."""
        # default days_held=999 → no downgrade
        assert ec.map_score_to_status(90) == "🔥 Power"
        assert ec.map_score_to_status(45) == "🟠 Weak"

    def test_healthy_to_watch_label_preserved(self):
        """The existing 'תקין אך במעקב' downgrade based on bad_closes_10
        still fires alongside the age gate."""
        features = {"bad_closes_10": 3, "good_closes_10": 1}
        # Healthy score, mature age, but bad closes → "תקין אך במעקב"
        assert ec.map_score_to_status(75, features=features, days_held=20) \
               == "🟡 תקין אך במעקב"


# ════════════════════════════════════════════════════════════════════════════════
# HIGH 5 — Market regime gating in adaptive_risk_engine
# ════════════════════════════════════════════════════════════════════════════════

def _make_hot_camps(n: int):
    """n winning campaigns to push heat above 60 → direction=up."""
    from datetime import datetime as dt, timedelta as td
    import pandas as pd
    out = []
    for i in range(n):
        out.append({
            "campaign_id": f"X_{i}", "symbol": "X",
            "setup_type": "EP", "total_pnl_usd": 200.0,
            "close_date": pd.Timestamp(dt.now() - td(days=i)),
            "is_win": True, "original_campaign_risk": 50.0,
            "stat_bucket": ec.classify_stat_bucket("EP", 50.0),
        })
    return out


def _patch_cold_regime():
    """Patch ec.compute_market_regime to return Cold."""
    return patch.object(ec, "compute_market_regime",
                         return_value={"ok": True, "data": {"status": "🔴 Cold"}})


def _patch_hot_regime():
    return patch.object(ec, "compute_market_regime",
                         return_value={"ok": True, "data": {"status": "🔥 Hot"}})


class TestMarketRegimeGate:
    def test_cold_regime_blocks_up_step(self, tmp_path, monkeypatch):
        """Heat is high + 5+ closed campaigns since change, but Cold
        regime overrides → direction = hold with explanation."""
        # Set up config with old risk change so closed-campaigns gate passes
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text(
            '{"risk_pct_input": 0.60, "risk_changed_ts": 0, "risk_changed_dir": ""}'
        )
        monkeypatch.setattr("adaptive_risk_engine.SENTINEL_CONFIG_FILE", str(cfg))
        camps = _make_hot_camps(6)
        with _patch_cold_regime(), \
             patch.object(ec, "get_cached_history", return_value=None):
            result = are.compute_adaptive_risk(camps, current_risk_pct=0.60,
                                                 nav=8000.0)
        assert result["ok"]
        assert result["direction"] == "hold"
        assert "משטר שוק קר" in result["step_type"]
        assert result["recommended_risk_pct"] == pytest.approx(0.60)

    def test_hot_regime_does_not_block(self, tmp_path, monkeypatch):
        """Hot regime + heat-driven up direction → step up proceeds."""
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text(
            '{"risk_pct_input": 0.60, "risk_changed_ts": 0, "risk_changed_dir": ""}'
        )
        monkeypatch.setattr("adaptive_risk_engine.SENTINEL_CONFIG_FILE", str(cfg))
        camps = _make_hot_camps(6)
        with _patch_hot_regime(), \
             patch.object(ec, "get_cached_history", return_value=None):
            result = are.compute_adaptive_risk(camps, current_risk_pct=0.60,
                                                 nav=8000.0)
        assert "משטר שוק קר" not in result.get("step_type", "")

    def test_cold_regime_does_not_block_down(self, tmp_path, monkeypatch):
        """Safety net: a Cold regime + cold heat → down step stays fast."""
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text('{"risk_pct_input": 0.60}')
        monkeypatch.setattr("adaptive_risk_engine.SENTINEL_CONFIG_FILE", str(cfg))
        # 3 losses in a row → loss streak ≥ 3 → direction=down_fast
        from datetime import datetime as dt, timedelta as td
        import pandas as pd
        losing = [{
            "campaign_id": f"L_{i}", "symbol": "L", "setup_type": "EP",
            "total_pnl_usd": -100.0,
            "close_date": pd.Timestamp(dt.now() - td(days=i)),
            "is_win": False, "original_campaign_risk": 100.0,
            "stat_bucket": ec.classify_stat_bucket("EP", 100.0),
        } for i in range(3)]
        with _patch_cold_regime(), \
             patch.object(ec, "get_cached_history", return_value=None):
            result = are.compute_adaptive_risk(losing, current_risk_pct=0.60,
                                                 nav=8000.0)
        # Down direction never gated by regime — message is about loss streak,
        # NOT about cold regime
        assert "משטר שוק קר" not in result.get("step_type", "")

    def test_regime_fetch_failure_does_not_block(self, tmp_path, monkeypatch):
        """If get_cached_history raises (e.g., network down + cache empty),
        the regime check fails open — don't trap the user."""
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text(
            '{"risk_pct_input": 0.60, "risk_changed_ts": 0, "risk_changed_dir": ""}'
        )
        monkeypatch.setattr("adaptive_risk_engine.SENTINEL_CONFIG_FILE", str(cfg))
        camps = _make_hot_camps(6)
        with patch.object(ec, "get_cached_history",
                          side_effect=Exception("network down")):
            result = are.compute_adaptive_risk(camps, current_risk_pct=0.60,
                                                 nav=8000.0)
        assert "משטר שוק קר" not in result.get("step_type", "")
