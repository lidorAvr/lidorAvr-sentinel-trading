"""test_morning_briefing.py — Sprint 11 pre-market summary feature.

Covers:
  - _morning_briefing_text rendering (positions / exposure / urgent tasks /
    pending risk count / empty cases)
  - _send_morning_briefing_if_due timing gate (weekday-only, hour window,
    once-per-day idempotence)
"""
import os
import sys
import types as py_types
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

import risk_monitor as rm


# ════════════════════════════════════════════════════════════════════════════════
# _morning_briefing_text
# ════════════════════════════════════════════════════════════════════════════════

class TestMorningBriefingText:
    def test_minimal_briefing_with_no_tasks(self):
        text = rm._morning_briefing_text(
            date_str="14/05/2026",
            regime_status="🔥 Hot",
            n_positions=6,
            total_exposure_pct=39.1,
            total_pnl_usd=301.5,
            urgent_tasks=[],
            pending_risk_count=0,
        )
        assert "14/05/2026" in text
        assert "🔥 Hot" in text
        assert "6" in text  # n_positions
        assert "39.1%" in text
        assert "$302" in text or "$301" in text  # %.0f rounding
        assert "אין משימות דחופות" in text

    def test_briefing_with_urgent_tasks(self):
        tasks = [
            ("CAT",  "🛡️ הגיע ל-2R — קדם סטופ ל-BE"),
            ("MRVL", "📈 +9.97R Runner — בחר hold/tighten/partial"),
        ]
        text = rm._morning_briefing_text(
            "14/05/2026", "🔥 Hot", 6, 39.1, 301.5, tasks, 0
        )
        assert "משימות דחופות" in text
        assert "(2)" in text
        assert "CAT" in text and "MRVL" in text

    def test_truncates_long_task_list_with_count(self):
        tasks = [(f"S{i}", f"task {i}") for i in range(8)]
        text = rm._morning_briefing_text(
            "14/05/2026", "🔥 Hot", 8, 50.0, 0.0, tasks, 0
        )
        assert "+3 נוספות" in text  # 8 - 5 = 3
        assert "/t" in text  # hint to open task review

    def test_negative_pnl_shows_red_icon(self):
        text = rm._morning_briefing_text(
            "14/05/2026", "🟡 Neutral", 3, 25.0, -150.0, [], 0
        )
        assert "🔴" in text  # red icon for negative
        assert "$-150" in text

    def test_pending_risk_count_shown_when_positive(self):
        text = rm._morning_briefing_text(
            "14/05/2026", "🔥 Hot", 4, 30.0, 100.0, [], pending_risk_count=3
        )
        assert "המלצות סיכון פתוחות" in text
        assert "3" in text
        assert "/r" in text  # link to /stats

    def test_pending_risk_zero_hides_line(self):
        text = rm._morning_briefing_text(
            "14/05/2026", "🔥 Hot", 4, 30.0, 100.0, [], pending_risk_count=0
        )
        # No "המלצות סיכון" line when count is 0
        assert "המלצות סיכון" not in text

    def test_market_close_hint(self):
        """The briefing tells the user when US market opens."""
        text = rm._morning_briefing_text(
            "14/05/2026", "🔥 Hot", 1, 10.0, 0.0, [], 0
        )
        assert "16:30 IL" in text  # US open in Israel time

    def test_empty_regime_falls_back_to_placeholder(self):
        text = rm._morning_briefing_text(
            "14/05/2026", "", 0, 0.0, 0.0, [], 0
        )
        assert "מחושב" in text or "🌡️" in text


# ════════════════════════════════════════════════════════════════════════════════
# _israel_now
# ════════════════════════════════════════════════════════════════════════════════

class TestIsraelNow:
    def test_returns_datetime(self):
        now = rm._israel_now()
        assert isinstance(now, datetime)

    def test_tz_aware_or_fallback(self):
        """Should be either tz-aware (zoneinfo path) or naive (fallback)."""
        now = rm._israel_now()
        # Must work whichever path was taken
        assert now.year >= 2024


# ════════════════════════════════════════════════════════════════════════════════
# _send_morning_briefing_if_due — timing gate
# ════════════════════════════════════════════════════════════════════════════════

def _fake_il_dt(weekday: int, hour: int):
    """Build a datetime that lands on a given weekday + hour. Used to
    inject specific times via patching _israel_now."""
    # 2026-05-11 is Monday (weekday 0). Step from there.
    base = datetime(2026, 5, 11)
    return base + timedelta(days=weekday, hours=hour)


class TestSendMorningBriefingIfDue:
    def test_skipped_on_saturday(self):
        state = {}
        with patch("risk_monitor._israel_now",
                   return_value=_fake_il_dt(5, 7)), \
             patch("risk_monitor._gather_morning_briefing_data") as g, \
             patch("risk_monitor.send_telegram") as st:
            rm._send_morning_briefing_if_due(state, now_ts=0)
        g.assert_not_called()
        st.assert_not_called()
        assert "last_morning_briefing_date" not in state

    def test_skipped_on_sunday(self):
        state = {}
        with patch("risk_monitor._israel_now",
                   return_value=_fake_il_dt(6, 7)), \
             patch("risk_monitor._gather_morning_briefing_data") as g, \
             patch("risk_monitor.send_telegram") as st:
            rm._send_morning_briefing_if_due(state, now_ts=0)
        g.assert_not_called()
        st.assert_not_called()

    def test_skipped_outside_window_before(self):
        """6:59 IL — too early."""
        state = {}
        with patch("risk_monitor._israel_now",
                   return_value=datetime(2026, 5, 13, 6, 59)), \
             patch("risk_monitor._gather_morning_briefing_data") as g, \
             patch("risk_monitor.send_telegram") as st:
            rm._send_morning_briefing_if_due(state, now_ts=0)
        st.assert_not_called()

    def test_skipped_outside_window_after(self):
        """8:00 IL — past the window."""
        state = {}
        with patch("risk_monitor._israel_now",
                   return_value=datetime(2026, 5, 13, 8, 0)), \
             patch("risk_monitor._gather_morning_briefing_data") as g, \
             patch("risk_monitor.send_telegram") as st:
            rm._send_morning_briefing_if_due(state, now_ts=0)
        st.assert_not_called()

    def test_fires_in_window_on_weekday(self):
        state = {}
        with patch("risk_monitor._israel_now",
                   return_value=datetime(2026, 5, 13, 7, 15)), \
             patch("risk_monitor._gather_morning_briefing_data",
                   return_value={
                       "regime_status": "🔥 Hot", "n_positions": 3,
                       "total_exposure_pct": 30.0, "total_pnl_usd": 100.0,
                       "urgent_tasks": [("CAT", "BE@2R")], "pending_risk_count": 0,
                   }), \
             patch("risk_monitor.send_telegram") as st:
            rm._send_morning_briefing_if_due(state, now_ts=0)
        st.assert_called_once()
        assert state["last_morning_briefing_date"] == "2026-05-13"

    def test_does_not_double_fire_same_day(self):
        state = {"last_morning_briefing_date": "2026-05-13"}
        with patch("risk_monitor._israel_now",
                   return_value=datetime(2026, 5, 13, 7, 45)), \
             patch("risk_monitor._gather_morning_briefing_data") as g, \
             patch("risk_monitor.send_telegram") as st:
            rm._send_morning_briefing_if_due(state, now_ts=0)
        st.assert_not_called()
        g.assert_not_called()

    def test_marks_date_even_when_nothing_to_send(self):
        """Empty portfolio → suppress send but still mark date so we don't
        re-call _gather_morning_briefing_data every cycle in the window."""
        state = {}
        with patch("risk_monitor._israel_now",
                   return_value=datetime(2026, 5, 13, 7, 30)), \
             patch("risk_monitor._gather_morning_briefing_data",
                   return_value={
                       "regime_status": "", "n_positions": 0,
                       "total_exposure_pct": 0.0, "total_pnl_usd": 0.0,
                       "urgent_tasks": [], "pending_risk_count": 0,
                   }), \
             patch("risk_monitor.send_telegram") as st:
            rm._send_morning_briefing_if_due(state, now_ts=0)
        st.assert_not_called()
        # But date is marked to prevent re-gather
        assert state["last_morning_briefing_date"] == "2026-05-13"


# ════════════════════════════════════════════════════════════════════════════════
# _gather_morning_briefing_data — best-effort partial data
# ════════════════════════════════════════════════════════════════════════════════

class TestGatherData:
    def test_no_trades_returns_zeros(self):
        with patch("supabase_repository.get_all_trades", return_value=[]):
            out = rm._gather_morning_briefing_data()
        assert out["n_positions"] == 0
        assert out["urgent_tasks"] == []

    def test_partial_failure_does_not_crash(self):
        """Repo raises, briefing returns the empty skeleton, no exception."""
        with patch("supabase_repository.get_all_trades",
                   side_effect=Exception("connection lost")):
            out = rm._gather_morning_briefing_data()
        assert out["n_positions"] == 0
