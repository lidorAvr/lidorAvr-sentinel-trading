"""test_b3_closed_campaigns_gate.py — Closed-campaigns gate on UP steps.

Covers the B3 fix from the 2026-05-14 session feedback ("המערכת בעיקרון
ממליצה לי להעלות שוב סיכון... בקצב הזה אני יכול להגיע מהר מאוד ל 1.5%
2% ויותר רק בכלל שעובר זמן"). The adaptive risk ladder may not step UP
unless at least RISK_STEP_UP_MIN_CLOSED_CAMPAIGNS (5) stat-countable
campaigns have closed since the last confirmed risk change.

Gate properties:
  - Applies ONLY to UP steps. DOWN steps are not gated (safety net stays
    fast).
  - Counts only stat-countable closed campaigns (excludes ALGO_OBSERVED
    and DATA_INCOMPLETE — those don't represent tested user discretion).
  - Bypassed when `risk_changed_ts` is absent (fresh install with no
    prior change to anchor against).
  - Bypassed when the gate would have allowed step up anyway (e.g., heat
    direction is "hold" or "down_fast").
"""
import json
import os
import sys
import time
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

import adaptive_risk_engine as are


# ── Helpers ──────────────────────────────────────────────────────────────────

def _config_with_risk_changed(tmp_path, monkeypatch, ts: float = None,
                              risk_pct=0.60):
    """Write a sentinel_config.json that records a recent risk change."""
    cfg = {"risk_pct_input": risk_pct, "total_deposited": 7500.0}
    if ts is not None:
        cfg["risk_changed_ts"] = ts
        cfg["risk_changed_dir"] = "up"
    path = tmp_path / "sentinel_config.json"
    path.write_text(json.dumps(cfg))
    monkeypatch.setattr("adaptive_risk_engine.SENTINEL_CONFIG_FILE", str(path))
    return path


def _make_closed_camp(setup_type="EP", is_win=True, close_date=None,
                      risk_usd=50.0):
    """Build a campaign dict matching compute_closed_campaigns output."""
    if close_date is None:
        close_date = datetime.now()
    import pandas as pd
    if not isinstance(close_date, pd.Timestamp):
        close_date = pd.Timestamp(close_date)
    pnl = 100.0 if is_win else -50.0
    import engine_core as ec
    return {
        "campaign_id": f"X_{int(close_date.timestamp())}",
        "symbol": "X",
        "setup_type": setup_type,
        "total_pnl_usd": pnl,
        "close_date": close_date,
        "is_win": is_win,
        "original_campaign_risk": risk_usd,
        "stat_bucket": ec.classify_stat_bucket(setup_type, risk_usd),
    }


# ════════════════════════════════════════════════════════════════════════════════
# _last_risk_change_ts — read config
# ════════════════════════════════════════════════════════════════════════════════

class TestLastRiskChangeTs:
    def test_returns_value_from_config(self, tmp_path, monkeypatch):
        _config_with_risk_changed(tmp_path, monkeypatch, ts=12345.0)
        assert are._last_risk_change_ts() == pytest.approx(12345.0)

    def test_returns_zero_when_key_missing(self, tmp_path, monkeypatch):
        path = tmp_path / "sentinel_config.json"
        path.write_text(json.dumps({"risk_pct_input": 0.5}))
        monkeypatch.setattr("adaptive_risk_engine.SENTINEL_CONFIG_FILE", str(path))
        assert are._last_risk_change_ts() == 0.0

    def test_returns_zero_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("adaptive_risk_engine.SENTINEL_CONFIG_FILE",
                            str(tmp_path / "nonexistent.json"))
        assert are._last_risk_change_ts() == 0.0


# ════════════════════════════════════════════════════════════════════════════════
# _count_stat_countable_closed_since — count helper
# ════════════════════════════════════════════════════════════════════════════════

class TestCountStatCountableSince:
    def test_counts_only_campaigns_after_anchor(self):
        anchor = (datetime.now() - timedelta(days=7)).timestamp()
        camps = [
            _make_closed_camp(close_date=datetime.now() - timedelta(days=1)),
            _make_closed_camp(close_date=datetime.now() - timedelta(days=3)),
            _make_closed_camp(close_date=datetime.now() - timedelta(days=10)),
        ]
        # 2 campaigns after anchor (days=1, days=3); 1 before (days=10)
        assert are._count_stat_countable_closed_since(camps, anchor) == 2

    def test_excludes_algo_observed(self):
        anchor = (datetime.now() - timedelta(days=7)).timestamp()
        camps = [
            _make_closed_camp(setup_type="EP",
                              close_date=datetime.now() - timedelta(days=1)),
            _make_closed_camp(setup_type="ALGO",
                              close_date=datetime.now() - timedelta(days=2)),
            _make_closed_camp(setup_type="VCP_MANUAL",  # stat-countable
                              close_date=datetime.now() - timedelta(days=3)),
        ]
        # EP + VCP_MANUAL count; ALGO doesn't
        assert are._count_stat_countable_closed_since(camps, anchor) == 2

    def test_zero_anchor_returns_zero(self):
        camps = [_make_closed_camp()]
        assert are._count_stat_countable_closed_since(camps, 0.0) == 0

    def test_empty_list_returns_zero(self):
        anchor = time.time()
        assert are._count_stat_countable_closed_since([], anchor) == 0

    def test_handles_missing_close_date(self):
        anchor = time.time() - 3600
        camps = [{"stat_bucket": "EP", "close_date": None}]
        assert are._count_stat_countable_closed_since(camps, anchor) == 0


# ════════════════════════════════════════════════════════════════════════════════
# Gate integration via compute_adaptive_risk
# ════════════════════════════════════════════════════════════════════════════════

def _make_hot_camps(n: int, days_since_change: int = 0):
    """Build n winning campaigns closed within the last `days_since_change` days
    (or yesterday by default). Used to push heat score high (≥ 60)."""
    now = datetime.now()
    return [
        _make_closed_camp(setup_type="EP", is_win=True,
                          close_date=now - timedelta(days=max(0, days_since_change - i)))
        for i in range(n)
    ]


class TestGateBlocksUpStep:
    def test_blocks_up_when_fewer_than_5_closed_since_change(
            self, tmp_path, monkeypatch):
        # User changed risk 1 day ago. Only 2 campaigns closed since then.
        change_ts = (datetime.now() - timedelta(days=1)).timestamp()
        _config_with_risk_changed(tmp_path, monkeypatch, ts=change_ts,
                                  risk_pct=0.60)
        # 10 winning campaigns — 2 after change, 8 before
        camps = (_make_hot_camps(2, days_since_change=0) +
                 [_make_closed_camp(setup_type="EP", is_win=True,
                                    close_date=datetime.now() - timedelta(days=5 + i))
                  for i in range(8)])
        result = are.compute_adaptive_risk(camps, current_risk_pct=0.60,
                                            nav=8000.0)
        assert result["ok"]
        # Gate blocked the up step — direction held
        assert result["direction"] == "hold"
        assert "גייט קמפיינים סגורים" in result["step_type"]
        # The pct didn't move
        assert result["recommended_risk_pct"] == pytest.approx(0.60)

    def test_allows_up_when_5_or_more_closed_since_change(
            self, tmp_path, monkeypatch):
        # User changed risk 7 days ago. 6 campaigns closed since then.
        change_ts = (datetime.now() - timedelta(days=7)).timestamp()
        _config_with_risk_changed(tmp_path, monkeypatch, ts=change_ts,
                                  risk_pct=0.60)
        # 6 winners after the change, all stat-countable
        camps = [_make_closed_camp(setup_type="EP", is_win=True,
                                   close_date=datetime.now() - timedelta(days=i))
                 for i in range(6)]
        result = are.compute_adaptive_risk(camps, current_risk_pct=0.60,
                                            nav=8000.0)
        # Either up step happened, or direction is hold/down for OTHER reason
        # (heat too low). Either way, the gate text must NOT appear.
        assert "גייט קמפיינים סגורים" not in result.get("step_type", "")

    def test_does_not_gate_down_step(self, tmp_path, monkeypatch):
        # Recent change + only 1 closed campaign. Heat is COLD (3 losses).
        change_ts = (datetime.now() - timedelta(days=1)).timestamp()
        _config_with_risk_changed(tmp_path, monkeypatch, ts=change_ts,
                                  risk_pct=0.60)
        camps = [_make_closed_camp(setup_type="EP", is_win=False,
                                    close_date=datetime.now() - timedelta(days=i))
                 for i in range(3)]
        result = are.compute_adaptive_risk(camps, current_risk_pct=0.60,
                                            nav=8000.0)
        # Down direction must NOT be gated by closed-campaign count
        # (gate text never appears for down)
        assert "גייט קמפיינים סגורים" not in result.get("step_type", "")
        # Direction could be down_fast or hold depending on streak — either is fine

    def test_bypassed_when_no_prior_risk_change(self, tmp_path, monkeypatch):
        """Fresh install — risk_changed_ts is absent. Gate must not apply."""
        path = tmp_path / "sentinel_config.json"
        path.write_text(json.dumps({"risk_pct_input": 0.60,
                                    "total_deposited": 7500.0}))
        monkeypatch.setattr("adaptive_risk_engine.SENTINEL_CONFIG_FILE",
                            str(path))
        # Only 1 closed campaign — would normally gate, but no anchor
        camps = _make_hot_camps(1)
        result = are.compute_adaptive_risk(camps, current_risk_pct=0.60,
                                            nav=8000.0)
        # No anchor → gate bypassed; result depends on heat only.
        # Gate-specific text must NOT appear.
        assert "גייט קמפיינים סגורים" not in result.get("step_type", "")


# ════════════════════════════════════════════════════════════════════════════════
# Constants pinning — catch silent changes that break user expectations
# ════════════════════════════════════════════════════════════════════════════════

class TestConstantPinning:
    def test_min_closed_campaigns_is_five(self):
        """User-facing contract: documented as 5 in WAKE_UP_BRIEF + chat
        decision. Changing this requires updating both."""
        assert are.RISK_STEP_UP_MIN_CLOSED_CAMPAIGNS == 5

    def test_settle_hours_unchanged(self):
        """B3 adds the closed-campaigns gate — the existing 48h settle
        cooldown stays in place (defense in depth)."""
        assert are.RISK_SETTLE_HOURS == 48.0
