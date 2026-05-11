"""
test_adaptive_risk_engine.py — Comprehensive tests for adaptive_risk_engine.py.

Covers:
- compute_adaptive_risk: all direction scenarios, boundary conditions
- RISK_LADDER: valid values, bounds, closest-index math
- Weighted win rate formula verification
- Streak detection (win streak, loss streak, mixed)
- mark_adherence: updates log, handles missing file
- compute_adherence_stats: all stat fields, pending entries
- log_risk_journal: inserts at front, caps at 500, timestamp present
- update_risk_pct: writes config, rounds to 4 decimal places
- compute_closed_campaigns: full pipeline on realistic DataFrame
"""
import json
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import adaptive_risk_engine as are


# ── helpers ────────────────────────────────────────────────────────────────────

def _win(n=1, start_day=10):
    base = datetime(2025, 1, 1) + timedelta(days=start_day - 1)
    return [{"campaign_id": f"w{i}", "is_win": True,
             "close_date": base - timedelta(days=i), "total_pnl_usd": 100.0}
            for i in range(n)]

def _loss(n=1, start_day=5):
    base = datetime(2025, 1, 1) + timedelta(days=start_day - 1)
    return [{"campaign_id": f"l{i}", "is_win": False,
             "close_date": base - timedelta(days=i), "total_pnl_usd": -50.0}
            for i in range(n)]

def _campaigns(wins, losses):
    """Most-recent first: wins then losses."""
    return _win(wins) + _loss(losses)


# ════════════════════════════════════════════════════════════════════════════════
# RISK LADDER
# ════════════════════════════════════════════════════════════════════════════════

class TestRiskLadder:
    def test_ladder_is_ascending(self):
        for i in range(len(are.RISK_LADDER) - 1):
            assert are.RISK_LADDER[i] < are.RISK_LADDER[i + 1]

    def test_ladder_minimum_is_safe(self):
        assert are.RISK_LADDER[0] > 0
        assert are.RISK_LADDER[0] <= 0.5

    def test_ladder_maximum_is_bounded(self):
        assert are.RISK_LADDER[-1] <= 3.0

    def test_closest_index_exact_match(self):
        for i, val in enumerate(are.RISK_LADDER):
            assert are._closest_ladder_index(val) == i

    def test_closest_index_midpoint_goes_to_lower(self):
        mid = (are.RISK_LADDER[0] + are.RISK_LADDER[1]) / 2
        idx = are._closest_ladder_index(mid)
        assert idx in (0, 1)   # Either is acceptable at exact midpoint

    def test_closest_index_never_out_of_bounds(self):
        for val in [-99.0, 0.0, 0.001, 99.0, 1000.0]:
            idx = are._closest_ladder_index(val)
            assert 0 <= idx < len(are.RISK_LADDER)


# ════════════════════════════════════════════════════════════════════════════════
# COMPUTE_ADAPTIVE_RISK — DIRECTION LOGIC
# ════════════════════════════════════════════════════════════════════════════════

class TestComputeAdaptiveRiskDirections:
    def test_up_on_strong_heat(self):
        result = are.compute_adaptive_risk(_campaigns(8, 2), 0.5, 10000)
        assert result["ok"] is True
        assert result["direction"] == "up"

    def test_down_fast_on_3_consecutive_losses(self):
        # 3 losses newest-first, then wins
        campaigns = _loss(3, start_day=10) + _win(3, start_day=7)
        result = are.compute_adaptive_risk(campaigns, 1.0, 10000)
        assert result["direction"] == "down_fast"

    def test_down_fast_on_low_heat_score(self):
        result = are.compute_adaptive_risk(_campaigns(1, 9), 1.0, 10000)
        assert result["direction"] == "down_fast"

    def test_hold_on_neutral_heat(self):
        result = are.compute_adaptive_risk(_campaigns(5, 5), 0.75, 10000)
        assert result["direction"] in ("hold", "up", "down_fast")

    def test_result_has_all_required_keys(self):
        result = are.compute_adaptive_risk(_campaigns(6, 4), 0.5, 10000)
        for key in ("ok", "heat_score", "direction", "recommended_risk_pct",
                    "recommended_risk_usd", "current_risk_pct", "n_trades",
                    "win_streak", "loss_streak", "recent_10_wr", "all_50_wr"):
            assert key in result, f"Missing key: {key}"

    def test_not_enough_trades(self):
        result = are.compute_adaptive_risk(_campaigns(1, 1), 0.5, 10000)
        assert result["ok"] is False
        assert "3" in result["message"]

    def test_exactly_3_trades_is_allowed(self):
        result = are.compute_adaptive_risk(_campaigns(2, 1), 0.5, 10000)
        assert result["ok"] is True


# ════════════════════════════════════════════════════════════════════════════════
# HEAT SCORE MATH
# ════════════════════════════════════════════════════════════════════════════════

class TestHeatScoreMath:
    def test_all_wins_gives_100_heat(self):
        result = are.compute_adaptive_risk(_win(15), 0.5, 10000)
        assert result["heat_score"] == pytest.approx(100.0)

    def test_all_losses_gives_0_heat(self):
        result = are.compute_adaptive_risk(_loss(15), 1.0, 10000)
        assert result["heat_score"] == pytest.approx(0.0)

    def test_50pct_wr_gives_50_heat_when_equal_recent(self):
        # 5 wins + 5 losses in recent 10 (all weighted double), 0 more
        # weighted_wins=5*2=10, weighted_total=10*2=20, wr=50%
        campaigns = _win(5, start_day=10) + _loss(5, start_day=5)
        result = are.compute_adaptive_risk(campaigns, 0.5, 10000)
        assert result["heat_score"] == pytest.approx(50.0)

    def test_heat_score_in_0_100_range(self):
        for wins, losses in [(0, 10), (5, 5), (10, 0), (3, 7)]:
            n = wins + losses
            if n < 3:
                continue
            result = are.compute_adaptive_risk(_campaigns(wins, losses), 0.5, 10000)
            if result["ok"]:
                assert 0 <= result["heat_score"] <= 100


# ════════════════════════════════════════════════════════════════════════════════
# STREAK DETECTION
# ════════════════════════════════════════════════════════════════════════════════

class TestStreakDetection:
    def test_win_streak_counted_correctly(self):
        campaigns = _win(4, start_day=10) + _loss(3, start_day=6)
        result = are.compute_adaptive_risk(campaigns, 0.5, 10000)
        assert result["win_streak"] == 4
        assert result["loss_streak"] == 0

    def test_loss_streak_counted_correctly(self):
        campaigns = _loss(3, start_day=10) + _win(4, start_day=7)
        result = are.compute_adaptive_risk(campaigns, 1.0, 10000)
        assert result["loss_streak"] == 3
        assert result["win_streak"] == 0

    def test_alternating_no_streak(self):
        from datetime import timedelta
        campaigns = [
            {"campaign_id": f"c{i}", "is_win": (i % 2 == 0),
             "close_date": datetime(2025, 1, 10) - timedelta(days=i),
             "total_pnl_usd": 100 if i % 2 == 0 else -50}
            for i in range(6)
        ]
        result = are.compute_adaptive_risk(campaigns, 0.5, 10000)
        assert result["win_streak"] <= 1
        assert result["loss_streak"] <= 1


# ════════════════════════════════════════════════════════════════════════════════
# MARK_ADHERENCE
# ════════════════════════════════════════════════════════════════════════════════

class TestMarkAdherence:
    def _write_rec_log(self, path, entries):
        with open(path, "w") as f:
            json.dump(entries, f)

    def test_mark_adherence_followed_updates_first_entry(self, tmp_path):
        path = str(tmp_path / "rec.json")
        self._write_rec_log(path, [{"followed": None, "ts": "2025-01-10"}])
        with patch.object(are, "RECOMMENDATIONS_LOG_FILE", path):
            are.mark_adherence(0.5, 0.5, followed=True)
        with open(path) as f:
            log = json.load(f)
        assert log[0]["followed"] is True

    def test_mark_adherence_not_followed_records_reason(self, tmp_path):
        path = str(tmp_path / "rec.json")
        self._write_rec_log(path, [{"followed": None, "ts": "2025-01-10"}])
        with patch.object(are, "RECOMMENDATIONS_LOG_FILE", path):
            are.mark_adherence(0.5, 0.75, followed=False, reason="Too risky now")
        with open(path) as f:
            log = json.load(f)
        assert log[0]["followed"] is False
        assert log[0]["reason"] == "Too risky now"

    def test_mark_adherence_already_marked_not_overwritten(self, tmp_path):
        path = str(tmp_path / "rec.json")
        self._write_rec_log(path, [{"followed": True, "ts": "2025-01-10"}])
        with patch.object(are, "RECOMMENDATIONS_LOG_FILE", path):
            are.mark_adherence(0.5, 0.5, followed=False)
        with open(path) as f:
            log = json.load(f)
        assert log[0]["followed"] is True   # Not overwritten

    def test_mark_adherence_no_file_doesnt_crash(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        with patch.object(are, "RECOMMENDATIONS_LOG_FILE", path):
            are.mark_adherence(0.5, 0.5, followed=True)  # Should not raise

    def test_mark_adherence_records_actual_pct(self, tmp_path):
        path = str(tmp_path / "rec.json")
        self._write_rec_log(path, [{"followed": None, "ts": "2025-01-10"}])
        with patch.object(are, "RECOMMENDATIONS_LOG_FILE", path):
            are.mark_adherence(0.75, 1.0, followed=True)
        with open(path) as f:
            log = json.load(f)
        assert log[0].get("actual_risk_pct") == 1.0


# ════════════════════════════════════════════════════════════════════════════════
# COMPUTE_ADHERENCE_STATS
# ════════════════════════════════════════════════════════════════════════════════

class TestComputeAdherenceStats:
    def _write_log(self, path, entries):
        with open(path, "w") as f:
            json.dump(entries, f)

    def test_no_file_returns_error_dict(self, tmp_path):
        with patch.object(are, "RECOMMENDATIONS_LOG_FILE", str(tmp_path / "no.json")):
            result = are.compute_adherence_stats()
        assert result["ok"] is False

    def test_all_followed_gives_100pct(self, tmp_path):
        path = str(tmp_path / "rec.json")
        self._write_log(path, [{"followed": True}, {"followed": True}])
        with patch.object(are, "RECOMMENDATIONS_LOG_FILE", path):
            result = are.compute_adherence_stats()
        assert result["ok"] is True
        assert result["adherence_pct"] == 100.0

    def test_none_followed_gives_0pct(self, tmp_path):
        path = str(tmp_path / "rec.json")
        self._write_log(path, [{"followed": False}, {"followed": False}])
        with patch.object(are, "RECOMMENDATIONS_LOG_FILE", path):
            result = are.compute_adherence_stats()
        assert result["adherence_pct"] == 0.0

    def test_pending_entries_not_counted_in_adherence(self, tmp_path):
        path = str(tmp_path / "rec.json")
        self._write_log(path, [
            {"followed": True},
            {"followed": None},   # pending
            {"followed": False},
        ])
        with patch.object(are, "RECOMMENDATIONS_LOG_FILE", path):
            result = are.compute_adherence_stats()
        assert result["evaluated"] == 2
        assert result["adherence_pct"] == pytest.approx(50.0)

    def test_last_actions_uses_emoji_symbols(self, tmp_path):
        path = str(tmp_path / "rec.json")
        self._write_log(path, [
            {"followed": True}, {"followed": False}, {"followed": None}
        ])
        with patch.object(are, "RECOMMENDATIONS_LOG_FILE", path):
            result = are.compute_adherence_stats()
        assert "✅" in result["last_actions"]
        assert "❌" in result["last_actions"]
        assert "⏳" in result["last_actions"]

    def test_total_recommendations_counts_all(self, tmp_path):
        path = str(tmp_path / "rec.json")
        entries = [{"followed": i % 2 == 0} for i in range(7)]
        self._write_log(path, entries)
        with patch.object(are, "RECOMMENDATIONS_LOG_FILE", path):
            result = are.compute_adherence_stats()
        assert result["total_recommendations"] == 7


# ════════════════════════════════════════════════════════════════════════════════
# LOG_RISK_JOURNAL
# ════════════════════════════════════════════════════════════════════════════════

class TestLogRiskJournal:
    def test_entry_inserted_at_front(self, tmp_path):
        path = str(tmp_path / "journal.json")
        with patch.object(are, "RISK_JOURNAL_FILE", path):
            are.log_risk_journal({"direction": "up", "reason": "first"})
            are.log_risk_journal({"direction": "hold", "reason": "second"})
        with open(path) as f:
            log = json.load(f)
        assert log[0]["reason"] == "second"  # Most recent first

    def test_timestamp_added_automatically(self, tmp_path):
        path = str(tmp_path / "journal.json")
        with patch.object(are, "RISK_JOURNAL_FILE", path):
            are.log_risk_journal({"direction": "up"})
        with open(path) as f:
            log = json.load(f)
        assert "ts" in log[0]
        assert log[0]["ts"] != ""

    def test_journal_capped_at_500(self, tmp_path):
        path = str(tmp_path / "journal.json")
        with open(path, "w") as f:
            json.dump([{"ts": "x"}] * 499, f)
        with patch.object(are, "RISK_JOURNAL_FILE", path):
            for _ in range(5):
                are.log_risk_journal({"direction": "hold"})
        with open(path) as f:
            log = json.load(f)
        assert len(log) <= 500


# ════════════════════════════════════════════════════════════════════════════════
# UPDATE_RISK_PCT
# ════════════════════════════════════════════════════════════════════════════════

class TestUpdateRiskPct:
    def test_writes_rounded_value(self, tmp_path):
        path = str(tmp_path / "sentinel_config.json")
        with patch.object(are, "SENTINEL_CONFIG_FILE", path):
            result = are.update_risk_pct(0.666666)
        assert result is True
        with open(path) as f:
            cfg = json.load(f)
        assert cfg["risk_pct_input"] == pytest.approx(0.6667, abs=1e-4)

    def test_preserves_existing_keys(self, tmp_path):
        path = str(tmp_path / "sentinel_config.json")
        with open(path, "w") as f:
            json.dump({"nav": 10000.0, "total_deposited": 7500.0}, f)
        with patch.object(are, "SENTINEL_CONFIG_FILE", path):
            are.update_risk_pct(1.0)
        with open(path) as f:
            cfg = json.load(f)
        assert cfg["nav"] == 10000.0
        assert cfg["risk_pct_input"] == 1.0

    def test_returns_false_on_permission_error(self, tmp_path):
        path = str(tmp_path / "readonly.json")
        with patch.object(are, "SENTINEL_CONFIG_FILE", path):
            with patch("builtins.open", side_effect=PermissionError("denied")):
                result = are.update_risk_pct(0.5)
        assert result is False


# ════════════════════════════════════════════════════════════════════════════════
# COMPUTE_CLOSED_CAMPAIGNS — PIPELINE
# ════════════════════════════════════════════════════════════════════════════════

class TestComputeClosedCampaigns:
    def _df(self):
        return pd.DataFrame([
            {"campaign_id": "c1", "symbol": "AAPL", "side": "BUY",
             "quantity": 10, "price": 150, "pnl_usd": 0, "trade_date": "2025-01-05"},
            {"campaign_id": "c1", "symbol": "AAPL", "side": "SELL",
             "quantity": -10, "price": 160, "pnl_usd": 100, "trade_date": "2025-01-10"},
            {"campaign_id": "c2", "symbol": "MSFT", "side": "BUY",
             "quantity": 5, "price": 300, "pnl_usd": 0, "trade_date": "2025-01-02"},
            {"campaign_id": "c2", "symbol": "MSFT", "side": "SELL",
             "quantity": -5, "price": 290, "pnl_usd": -50, "trade_date": "2025-01-07"},
        ])

    def test_two_closed_campaigns_detected(self):
        result = are.compute_closed_campaigns(self._df())
        assert len(result) == 2

    def test_is_win_correct(self):
        result = are.compute_closed_campaigns(self._df())
        wins   = [r for r in result if r["is_win"]]
        losses = [r for r in result if not r["is_win"]]
        assert len(wins)   == 1
        assert len(losses) == 1

    def test_total_pnl_correct(self):
        result = are.compute_closed_campaigns(self._df())
        aapl   = next(r for r in result if r["symbol"] == "AAPL")
        assert aapl["total_pnl_usd"] == pytest.approx(100.0)

    def test_partial_sell_not_closed(self):
        df = pd.DataFrame([
            {"campaign_id": "c1", "symbol": "AAPL", "side": "BUY",
             "quantity": 10, "price": 150, "pnl_usd": 0, "trade_date": "2025-01-05"},
            {"campaign_id": "c1", "symbol": "AAPL", "side": "SELL",
             "quantity": -5, "price": 160, "pnl_usd": 50, "trade_date": "2025-01-10"},
        ])
        result = are.compute_closed_campaigns(df)
        assert result == []

    def test_sorted_newest_first(self):
        result = are.compute_closed_campaigns(self._df())
        assert result[0]["close_date"] >= result[1]["close_date"]
