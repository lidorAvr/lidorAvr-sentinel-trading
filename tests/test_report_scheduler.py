"""Tests for report_scheduler.py — period helpers, dedup state, weekly breakdown."""
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import report_scheduler as m

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")


class TestWeeklyPeriod:
    def _saturday(self, year, month, day):
        return datetime(year, month, day, 8, 30, 0, tzinfo=ISRAEL_TZ)

    def test_period_start_is_sunday(self):
        sat = self._saturday(2025, 1, 11)
        start, _ = m._weekly_period(sat)
        assert start.weekday() == 6  # Sunday

    def test_period_spans_seven_days(self):
        sat = self._saturday(2025, 1, 11)
        start, end = m._weekly_period(sat)
        # end is Saturday 23:59:59, start is Sunday 00:00:00 — span = 6 days + ~24h
        assert (end.date() - start.date()).days == 6

    def test_end_is_saturday_23_59(self):
        sat = self._saturday(2025, 1, 11)
        _, end = m._weekly_period(sat)
        assert end.hour == 23 and end.minute == 59

    def test_cross_month_boundary(self):
        sat = self._saturday(2025, 2, 1)
        start, end = m._weekly_period(sat)
        assert start.month == 1   # previous month
        assert end.month == 2


class TestMonthlyPeriod:
    def _first_of_month(self, year, month):
        return datetime(year, month, 1, 8, 40, tzinfo=ISRAEL_TZ)

    def test_returns_previous_month(self):
        ref = self._first_of_month(2025, 2)
        start, end = m._monthly_period(ref)
        assert start.month == 1
        assert end.month == 1

    def test_full_month_january(self):
        ref = self._first_of_month(2025, 2)
        start, end = m._monthly_period(ref)
        assert start.day == 1
        assert end.day == 31

    def test_full_month_february_non_leap(self):
        ref = self._first_of_month(2025, 3)
        start, end = m._monthly_period(ref)
        assert start.month == 2
        assert end.day == 28

    def test_full_month_february_leap(self):
        ref = self._first_of_month(2024, 3)
        start, end = m._monthly_period(ref)
        assert start.month == 2
        assert end.day == 29   # 2024 is leap year

    def test_year_rollover(self):
        ref = self._first_of_month(2025, 1)
        start, end = m._monthly_period(ref)
        assert start.year == 2024
        assert start.month == 12


class TestSchedulerState:
    def test_already_ran_false_when_no_entry(self):
        assert m._already_ran({}, "weekly", "2025-01-11") is False

    def test_already_ran_true_when_same_date(self):
        state = {"weekly": "2025-01-11"}
        assert m._already_ran(state, "weekly", "2025-01-11") is True

    def test_already_ran_false_when_different_date(self):
        state = {"weekly": "2025-01-04"}
        assert m._already_ran(state, "weekly", "2025-01-11") is False

    def test_mark_ran_writes_file(self, tmp_path):
        with patch.object(m, "STATE_FILE", str(tmp_path / "state.json")):
            state = {}
            m._mark_ran(state, "weekly", "2025-01-11")
        with open(str(tmp_path / "state.json")) as f:
            saved = json.load(f)
        assert saved["weekly"] == "2025-01-11"

    def test_mark_ran_updates_state_dict(self, tmp_path):
        with patch.object(m, "STATE_FILE", str(tmp_path / "state.json")):
            state = {}
            m._mark_ran(state, "monthly", "2025-01-01")
        assert state["monthly"] == "2025-01-01"

    def test_load_state_returns_empty_when_missing(self, tmp_path):
        with patch.object(m, "STATE_FILE", str(tmp_path / "no_file.json")):
            result = m._load_state()
        assert result == {}

    def test_load_state_reads_existing(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text(json.dumps({"weekly": "2025-01-04"}))
        with patch.object(m, "STATE_FILE", str(path)):
            result = m._load_state()
        assert result["weekly"] == "2025-01-04"


class TestBuildWeeklyBreakdown:
    def _snap(self, ps, pe, net_r, wr, n):
        return {
            "period_start": ps.isoformat(),
            "period_end":   pe.isoformat(),
            "analytics": {"total_r_net": net_r, "win_rate": wr, "campaigns_closed": n},
        }

    def test_includes_weeks_inside_month(self):
        month_start = datetime(2025, 1, 1)
        month_end   = datetime(2025, 1, 31)
        snaps = [
            self._snap(datetime(2025, 1, 5), datetime(2025, 1, 11), 1.5, 0.6, 3),
            self._snap(datetime(2025, 1, 12), datetime(2025, 1, 18), 0.5, 0.5, 2),
        ]
        result = m._build_weekly_breakdown(snaps, month_start, month_end)
        assert len(result) == 2

    def test_excludes_weeks_outside_month(self):
        month_start = datetime(2025, 1, 1)
        month_end   = datetime(2025, 1, 31)
        snaps = [
            self._snap(datetime(2024, 12, 29), datetime(2025, 1,  4), 1.0, 0.6, 2),  # straddles boundary
            self._snap(datetime(2025, 1, 12),  datetime(2025, 1, 18), 0.5, 0.5, 2),
        ]
        result = m._build_weekly_breakdown(snaps, month_start, month_end)
        assert len(result) == 1

    def test_breakdown_has_required_keys(self):
        snaps = [
            self._snap(datetime(2025, 1, 5), datetime(2025, 1, 11), 1.5, 0.6, 3),
        ]
        result = m._build_weekly_breakdown(snaps, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert len(result) == 1
        row = result[0]
        for k in ("label", "campaigns", "net_r", "win_rate"):
            assert k in row

    def test_empty_snaps_returns_empty_list(self):
        result = m._build_weekly_breakdown([], datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result == []

    def test_invalid_snap_skipped(self):
        snaps = [{"period_start": "bad-date", "period_end": "bad", "analytics": {}}]
        result = m._build_weekly_breakdown(snaps, datetime(2025, 1, 1), datetime(2025, 1, 31))
        assert result == []


class TestCoachingInsights:
    def _ana(self, **kw):
        base = {"win_rate": 0.5, "expectancy_r": 0.3, "missing_stop_rate": 0.0,
                "oversized_rate": 0.0, "campaigns_closed": 5, "dev_score": 70,
                "profit_factor": 1.5}
        base.update(kw)
        return base

    def test_weekly_returns_list(self):
        result = m._weekly_coaching_insights(self._ana())
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_weekly_mentions_stop_when_high_missing(self):
        result = m._weekly_coaching_insights(self._ana(missing_stop_rate=0.3))
        assert any("סטופ" in i or "stop" in i.lower() for i in result)

    def test_weekly_mentions_oversized(self):
        result = m._weekly_coaching_insights(self._ana(oversized_rate=0.4))
        assert any("Oversized" in i or "sizing" in i.lower() for i in result)

    def test_monthly_returns_list(self):
        result = m._monthly_coaching_insights(self._ana())
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_monthly_mentions_pf_when_below_one(self):
        result = m._monthly_coaching_insights(self._ana(profit_factor=0.7, campaigns_closed=8))
        assert any("Profit Factor" in i or "1" in i for i in result)
