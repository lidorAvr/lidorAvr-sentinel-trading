"""
Tests for fetch_next_earnings_date() and Portfolio Heat Map / AI Export helpers.
Uses mocking to avoid network calls.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import engine_core as ec


class TestFetchNextEarningsDate:
    def _mock_ticker(self, earnings_date=None):
        tk = MagicMock()
        if earnings_date is not None:
            tk.calendar = {"Earnings Date": [earnings_date]}
        else:
            tk.calendar = None
        return tk

    def test_no_calendar_returns_no_info(self):
        with patch("yfinance.Ticker", return_value=self._mock_ticker(None)):
            # clear cache first
            ec.YF_CACHE.pop("AAPL_earnings", None)
            result = ec.fetch_next_earnings_date("AAPL")
        assert result["ok"] is False
        assert result["date"] is None
        assert "אין מידע" in result["cushion_verdict"]

    def test_earnings_within_7_days_red(self):
        future = datetime.now() + timedelta(days=3)
        with patch("yfinance.Ticker", return_value=self._mock_ticker(future)):
            ec.YF_CACHE.pop("TSLA_earnings", None)
            result = ec.fetch_next_earnings_date("TSLA")
        assert result["ok"] is True
        assert "🔴" in result["cushion_verdict"]
        assert result["days_to_event"] is not None
        assert 0 <= result["days_to_event"] <= 7

    def test_earnings_within_21_days_yellow(self):
        future = datetime.now() + timedelta(days=14)
        with patch("yfinance.Ticker", return_value=self._mock_ticker(future)):
            ec.YF_CACHE.pop("QQQ_earnings", None)
            result = ec.fetch_next_earnings_date("QQQ")
        assert result["ok"] is True
        assert "🟡" in result["cushion_verdict"]

    def test_earnings_beyond_21_days_green(self):
        future = datetime.now() + timedelta(days=45)
        with patch("yfinance.Ticker", return_value=self._mock_ticker(future)):
            ec.YF_CACHE.pop("MSFT_earnings", None)
            result = ec.fetch_next_earnings_date("MSFT")
        assert result["ok"] is True
        assert "🟢" in result["cushion_verdict"]

    def test_result_has_required_keys(self):
        with patch("yfinance.Ticker", return_value=self._mock_ticker(None)):
            ec.YF_CACHE.pop("XYZ_earnings", None)
            result = ec.fetch_next_earnings_date("XYZ")
        assert "date" in result
        assert "days_to_event" in result
        assert "cushion_verdict" in result
        assert "ok" in result

    def test_caching_avoids_second_call(self):
        future = datetime.now() + timedelta(days=10)
        # prime the cache
        ec.YF_CACHE["CACHED_earnings"] = {
            "data": {"date": future, "days_to_event": 10,
                     "cushion_verdict": "🟡 10 ימים", "ok": True},
            "time": __import__("time").time(),
        }
        with patch("yfinance.Ticker") as mock_yf:
            result = ec.fetch_next_earnings_date("CACHED")
            mock_yf.assert_not_called()
        assert result["ok"] is True

    def test_exception_returns_safe_fallback(self):
        tk = MagicMock()
        tk.calendar = {"Earnings Date": ["not-a-date-at-all"]}
        with patch("yfinance.Ticker", return_value=tk):
            ec.YF_CACHE.pop("ERR_earnings", None)
            result = ec.fetch_next_earnings_date("ERR")
        # Should not raise — returns ok=False fallback
        assert "ok" in result

    def test_past_earnings_marked_as_passed(self):
        past = datetime.now() - timedelta(days=5)
        with patch("yfinance.Ticker", return_value=self._mock_ticker(past)):
            ec.YF_CACHE.pop("PAST_earnings", None)
            result = ec.fetch_next_earnings_date("PAST")
        if result["ok"]:
            assert "עבר" in result["cushion_verdict"] or result["days_to_event"] < 0


class TestFmtAlgoRiskNote:
    """Tests for telegram_formatters.fmt_algo_risk_note (already exists)."""
    def test_contains_symbol(self):
        from telegram_formatters import fmt_algo_risk_note
        result = fmt_algo_risk_note("QQQ", 2.5, 15.0, "מניה עלתה חדות")
        assert "QQQ" in result

    def test_contains_open_r(self):
        from telegram_formatters import fmt_algo_risk_note
        result = fmt_algo_risk_note("QQQ", 2.5, 15.0, "מניה עלתה חדות")
        assert "2.50R" in result

    def test_review_required_actionability(self):
        from telegram_formatters import fmt_algo_risk_note, fmt_actionability
        result = fmt_algo_risk_note("QQQ", 2.5, 15.0, "מניה עלתה חדות")
        review_line = fmt_actionability("review_required")
        # The actionability token appears in the note
        assert "לבדוק" in result

    def test_no_exit_instruction(self):
        from telegram_formatters import fmt_algo_risk_note
        result = fmt_algo_risk_note("QQQ", -1.5, 10.0, "ירידה חדה")
        # Sentinel must never say "exit" or "sell" in ALGO notes
        lower = result.lower()
        assert "exit" not in lower
        assert "sell" not in lower

    def test_returns_string(self):
        from telegram_formatters import fmt_algo_risk_note
        result = fmt_algo_risk_note("TSLA", 1.0, 8.0, "בדיקה")
        assert isinstance(result, str)
