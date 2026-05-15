"""
Behavioral tests for telegram_bot_secure_runner observability (Issue P)
plus regression guards that the security gate logic is unchanged.

The module imports only stdlib at module level (telebot is imported lazily
inside install_telegram_hardening), so it is safe to import directly.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import telegram_bot_secure_runner as sr


@pytest.fixture(autouse=True)
def _clean_guard_state():
    """Reset the in-memory rate-limit state around every test."""
    sr._events.clear()
    sr._cooldown_until.clear()
    yield
    sr._events.clear()
    sr._cooldown_until.clear()


class TestLogHelper:
    def test_log_emits_prefixed_line(self, capsys):
        sr._log("hello world")
        out = capsys.readouterr().out
        assert "[secure_runner] hello world" in out

    def test_log_never_raises(self):
        # Even if print blows up, _log must swallow it.
        import builtins
        orig = builtins.print
        builtins.print = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            sr._log("should not raise")
        finally:
            builtins.print = orig


class TestGuardDecisionLogging:
    def test_unauthorized_is_logged(self, capsys, monkeypatch):
        monkeypatch.setattr(sr, "ADMIN_ID", "999")
        allowed, reason = sr.guard_decision("12345")
        assert (allowed, reason) == (False, "unauthorized")
        assert "REJECT unauthorized" in capsys.readouterr().out

    def test_authorized_ok_is_silent(self, capsys, monkeypatch):
        monkeypatch.setattr(sr, "ADMIN_ID", "777")
        allowed, reason = sr.guard_decision("777")
        assert (allowed, reason) == (True, "ok")
        assert capsys.readouterr().out == ""   # no log noise on the happy path

    def test_rate_limit_trip_is_logged(self, capsys, monkeypatch):
        monkeypatch.setattr(sr, "ADMIN_ID", "777")
        monkeypatch.setattr(sr, "MAX_MESSAGES", 3)
        for _ in range(3):
            assert sr.guard_decision("777") == (True, "ok")
        capsys.readouterr()  # drain the silent OKs
        allowed, reason = sr.guard_decision("777")
        assert (allowed, reason) == (False, "rate_limited")
        out = capsys.readouterr().out
        assert "RATE LIMIT tripped" in out

    def test_cooldown_window_not_logged_per_message(self, capsys, monkeypatch):
        monkeypatch.setattr(sr, "ADMIN_ID", "777")
        monkeypatch.setattr(sr, "MAX_MESSAGES", 2)
        for _ in range(2):
            sr.guard_decision("777")
        sr.guard_decision("777")          # trips → sets cooldown
        capsys.readouterr()               # drain
        # Subsequent messages during cooldown must NOT each emit a log line
        sr.guard_decision("777")
        sr.guard_decision("777")
        assert capsys.readouterr().out == ""


class TestGuardDecisionRegression:
    """Security gate behavior must be identical to before Issue P."""

    def test_no_admin_id_rejects_everything(self, monkeypatch):
        monkeypatch.setattr(sr, "ADMIN_ID", None)
        assert sr.guard_decision("anything") == (False, "unauthorized")

    def test_admin_allowed_until_limit(self, monkeypatch):
        monkeypatch.setattr(sr, "ADMIN_ID", "42")
        monkeypatch.setattr(sr, "MAX_MESSAGES", 5)
        results = [sr.guard_decision("42") for _ in range(5)]
        assert all(r == (True, "ok") for r in results)
        assert sr.guard_decision("42") == (False, "rate_limited")

    def test_guard_message_text_unchanged(self):
        assert sr.guard_message("unauthorized") == "⛔ אין הרשאה להשתמש בבוט הזה."
        assert "קצב הודעות" in sr.guard_message("rate_limited")


class TestTruthSuffixLogging:
    _DISCLAIMER = "מקור נתונים:"

    def test_marker_appends_disclaimer_and_logs(self, capsys):
        out_text = sr.truth_suffix("חדר מצב — דו\"ח")
        assert self._DISCLAIMER in out_text
        assert "data-source disclaimer appended" in capsys.readouterr().out

    def test_plain_text_untouched_and_silent(self, capsys):
        assert sr.truth_suffix("שלום") == "שלום"
        assert capsys.readouterr().out == ""

    def test_existing_disclaimer_not_doubled_or_logged(self, capsys):
        already = "חדר מצב\n\nℹ️ מקור נתונים: Live"
        assert sr.truth_suffix(already) == already
        assert capsys.readouterr().out == ""

    def test_non_string_passthrough(self, capsys):
        assert sr.truth_suffix({"k": 1}) == {"k": 1}
        assert capsys.readouterr().out == ""
