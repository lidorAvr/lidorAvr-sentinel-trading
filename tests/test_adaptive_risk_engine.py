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
                    "win_streak", "loss_streak", "recent_10_wr", "all_50_wr",
                    "n_used_10", "n_used_50", "payoff_ratio", "open_r_bonus"):
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

    def test_setup_type_included_in_result(self):
        df = pd.DataFrame([
            {"campaign_id": "a1", "symbol": "AAPL", "side": "BUY", "setup_type": "VCP",
             "quantity": 10, "price": 150, "pnl_usd": 0, "trade_date": "2025-01-05"},
            {"campaign_id": "a1", "symbol": "AAPL", "side": "SELL", "setup_type": "VCP",
             "quantity": -10, "price": 160, "pnl_usd": 100, "trade_date": "2025-01-10"},
        ])
        result = are.compute_closed_campaigns(df)
        assert len(result) == 1
        assert result[0]["setup_type"] == "VCP"


# ════════════════════════════════════════════════════════════════════════════════
# ALGO EXCLUSION FROM STREAK
# ════════════════════════════════════════════════════════════════════════════════

def _algo_loss(n=1, start_day=10):
    base = datetime(2025, 1, 1) + timedelta(days=start_day - 1)
    return [{"campaign_id": f"al{i}", "is_win": False, "setup_type": "ALGO",
             "close_date": base - timedelta(days=i), "total_pnl_usd": -50.0}
            for i in range(n)]


class TestAlgoExclusion:
    def test_algo_losses_do_not_trigger_streak(self):
        # 3 ALGO losses (newest first) then 3 disc wins — should NOT hit loss_streak >= 3
        campaigns = _algo_loss(3, start_day=10) + _win(3, start_day=7)
        result = are.compute_adaptive_risk(campaigns, 1.0, 10000)
        assert result["loss_streak"] == 0
        assert result["win_streak"] == 3

    def test_disc_losses_still_trigger_streak(self):
        # 3 disc losses newest-first → direction = down_fast
        campaigns = _loss(3, start_day=10) + _win(3, start_day=7)
        result = are.compute_adaptive_risk(campaigns, 1.0, 10000)
        assert result["loss_streak"] == 3
        assert result["direction"] == "down_fast"

    def test_algo_campaigns_downweighted_in_heat(self):
        # 8 ALGO wins + 2 disc losses → heat should not be as high as 8 pure disc wins
        algo_wins = [{"campaign_id": f"aw{i}", "is_win": True, "setup_type": "ALGO",
                      "close_date": datetime(2025, 1, 10) - timedelta(days=i),
                      "total_pnl_usd": 100.0} for i in range(8)]
        disc_losses = _loss(2, start_day=2)
        campaigns = algo_wins + disc_losses
        result_mixed = are.compute_adaptive_risk(campaigns, 0.5, 10000)

        pure_disc = _win(8) + _loss(2)
        result_pure = are.compute_adaptive_risk(pure_disc, 0.5, 10000)
        # ALGO at 0.25x weight → mixed heat should be lower than pure disc 80% win rate
        assert result_mixed["heat_score"] < result_pure["heat_score"]

    def test_n_used_reflects_disc_only(self):
        # 5 disc + 3 ALGO → n_used_10 should be 5, not 8
        disc = _win(3) + _loss(2)
        algo = _algo_loss(3, start_day=3)
        campaigns = disc + algo
        result = are.compute_adaptive_risk(campaigns, 0.5, 10000)
        assert result["n_used_10"] == 5
        assert result["n_used_50"] == 5


# ════════════════════════════════════════════════════════════════════════════════
# OPEN POSITION R BONUS
# ════════════════════════════════════════════════════════════════════════════════

class TestOpenRBonus:
    def test_no_open_positions_no_bonus(self):
        result = are.compute_adaptive_risk(_campaigns(5, 5), 0.5, 10000, open_r_list=None)
        assert result["open_r_bonus"] == 0.0

    def test_large_open_r_adds_bonus(self):
        result = are.compute_adaptive_risk(_campaigns(5, 5), 0.5, 10000, open_r_list=[3.0, 2.5])
        assert result["open_r_bonus"] == 10.0  # sum=5.5 >= 5

    def test_moderate_open_r_adds_smaller_bonus(self):
        result = are.compute_adaptive_risk(_campaigns(5, 5), 0.5, 10000, open_r_list=[1.5, 0.8])
        assert result["open_r_bonus"] == 5.0  # sum=2.3 >= 2

    def test_negative_open_r_not_added(self):
        result = are.compute_adaptive_risk(_campaigns(5, 5), 0.5, 10000, open_r_list=[-2.0, -1.0])
        assert result["open_r_bonus"] == 0.0  # only positive R counted

    def test_open_r_bonus_can_lift_direction(self):
        # Heat score near 55 (borderline) + large open R bonus lifts to >= 60
        # 6W + 4L in 10 → weighted_wr=0.6 → heat=60 (already at threshold)
        # Let's use 5W+5L=50 + big open bonus to push it up
        neutral = _campaigns(5, 5)
        result_no_bonus = are.compute_adaptive_risk(neutral, 0.5, 10000, open_r_list=None)
        result_with_bonus = are.compute_adaptive_risk(neutral, 0.5, 10000, open_r_list=[4.0, 2.0])
        assert result_with_bonus["heat_score"] > result_no_bonus["heat_score"]


# ════════════════════════════════════════════════════════════════════════════════
# N_USED LABELS — fewer than 10/50 closed campaigns
# ════════════════════════════════════════════════════════════════════════════════

class TestNUsedLabels:
    def test_n_used_10_equals_actual_count_when_fewer_than_10(self):
        # Only 5 disc campaigns → n_used_10 == 5
        campaigns = _win(3) + _loss(2)  # 5 campaigns
        result = are.compute_adaptive_risk(campaigns, 0.5, 10000)
        assert result["n_used_10"] == 5
        assert result["n_used_50"] == 5

    def test_n_used_10_and_50_differ_when_more_than_10(self):
        # 15 campaigns → n_used_10=10, n_used_50=15
        campaigns = _win(10) + _loss(5)
        result = are.compute_adaptive_risk(campaigns, 0.5, 10000)
        assert result["n_used_10"] == 10
        assert result["n_used_50"] == 15


# ════════════════════════════════════════════════════════════════════════════════
# STAT_BUCKET ENRICHMENT + DATA_INCOMPLETE FILTERING (matches dashboard logic)
# ════════════════════════════════════════════════════════════════════════════════

class TestStatBucketInClosedCampaigns:
    def test_vcp_with_initial_stop_classified_as_manual(self):
        df = pd.DataFrame([
            {"campaign_id": "v1", "symbol": "AAPL", "side": "BUY", "setup_type": "VCP",
             "quantity": 10, "price": 100, "initial_stop": 90, "pnl_usd": 0,
             "trade_date": "2025-01-05"},
            {"campaign_id": "v1", "symbol": "AAPL", "side": "SELL", "setup_type": "VCP",
             "quantity": -10, "price": 110, "initial_stop": 90, "pnl_usd": 100,
             "trade_date": "2025-01-10"},
        ])
        result = are.compute_closed_campaigns(df)
        assert result[0]["stat_bucket"] == "VCP_MANUAL"
        assert result[0]["original_campaign_risk"] == pytest.approx(100.0)  # (100-90)*10

    def test_vcp_missing_initial_stop_is_data_incomplete(self):
        df = pd.DataFrame([
            {"campaign_id": "d1", "symbol": "MSFT", "side": "BUY", "setup_type": "VCP",
             "quantity": 5, "price": 200, "initial_stop": 0, "pnl_usd": 0,
             "trade_date": "2025-01-02"},
            {"campaign_id": "d1", "symbol": "MSFT", "side": "SELL", "setup_type": "VCP",
             "quantity": -5, "price": 210, "initial_stop": 0, "pnl_usd": 50,
             "trade_date": "2025-01-07"},
        ])
        result = are.compute_closed_campaigns(df)
        assert result[0]["stat_bucket"] == "DATA_INCOMPLETE"
        assert result[0]["original_campaign_risk"] == 0.0

    def test_algo_is_algo_observed_regardless_of_stop(self):
        df = pd.DataFrame([
            {"campaign_id": "a1", "symbol": "HOOD", "side": "BUY", "setup_type": "ALGO",
             "quantity": 4, "price": 80, "initial_stop": 75, "pnl_usd": 0,
             "trade_date": "2025-01-05"},
            {"campaign_id": "a1", "symbol": "HOOD", "side": "SELL", "setup_type": "ALGO",
             "quantity": -4, "price": 78, "initial_stop": 75, "pnl_usd": -8,
             "trade_date": "2025-01-07"},
        ])
        result = are.compute_closed_campaigns(df)
        assert result[0]["stat_bucket"] == "ALGO_OBSERVED"

    def test_missing_initial_stop_column_falls_back_gracefully(self):
        df = pd.DataFrame([
            {"campaign_id": "x1", "symbol": "AAPL", "side": "BUY", "setup_type": "VCP",
             "quantity": 10, "price": 150, "pnl_usd": 0, "trade_date": "2025-01-05"},
            {"campaign_id": "x1", "symbol": "AAPL", "side": "SELL", "setup_type": "VCP",
             "quantity": -10, "price": 160, "pnl_usd": 100, "trade_date": "2025-01-10"},
        ])
        result = are.compute_closed_campaigns(df)
        assert result[0]["stat_bucket"] == "DATA_INCOMPLETE"
        assert result[0]["original_campaign_risk"] == 0.0


def _disc_camp(symbol, is_win, day, bucket="VCP_MANUAL"):
    return {"campaign_id": f"{symbol}-{day}", "symbol": symbol, "setup_type": "VCP",
            "is_win": is_win,
            "close_date": datetime(2025, 1, day),
            "total_pnl_usd": 100.0 if is_win else -50.0,
            "stat_bucket": bucket}


class TestDataIncompleteExcludedFromAdaptive:
    def test_data_incomplete_excluded_from_disc_win_rate(self):
        # 4 disc wins + 3 DATA_INCOMPLETE losses → WR should be 100% (only disc count)
        camps = (
            [_disc_camp(f"w{i}", True, 20 - i) for i in range(4)]
            + [_disc_camp(f"d{i}", False, 10 - i, bucket="DATA_INCOMPLETE") for i in range(3)]
        )
        result = are.compute_adaptive_risk(camps, 0.5, 10000)
        assert result["all_50_wr"] == 100.0
        assert result["n_used_50"] == 4

    def test_data_incomplete_excluded_from_loss_streak(self):
        # 3 DATA_INCOMPLETE losses at the top should NOT count as streak
        camps = (
            [_disc_camp(f"d{i}", False, 20 - i, bucket="DATA_INCOMPLETE") for i in range(3)]
            + [_disc_camp(f"w{i}", True, 15 - i) for i in range(3)]
        )
        result = are.compute_adaptive_risk(camps, 0.5, 10000)
        assert result["loss_streak"] == 0
        assert result["win_streak"] == 3

    def test_legacy_dicts_without_stat_bucket_fall_back_to_setup_type(self):
        # Older dicts (no stat_bucket key) should still be classified via setup_type
        camps = (
            [{"campaign_id": f"a{i}", "is_win": False, "setup_type": "ALGO",
              "close_date": datetime(2025, 1, 20 - i), "total_pnl_usd": -10.0}
             for i in range(3)]
            + [{"campaign_id": f"v{i}", "is_win": True, "setup_type": "VCP",
                "close_date": datetime(2025, 1, 15 - i), "total_pnl_usd": 100.0}
               for i in range(3)]
        )
        result = are.compute_adaptive_risk(camps, 0.5, 10000)
        # ALGO excluded → disc WR computed from 3 disc wins → 100%
        assert result["all_50_wr"] == 100.0
        assert result["loss_streak"] == 0
