"""test_risk_monitor_log_tee.py — Tests for github issue #33 fix.

Covers the _StdoutTee class and _rotate_log_file helper added to
risk_monitor.py so that the Telegram developer-menu log viewer
("📋 לוגים → risk-monitor") has a file to read.

The tee is installed only inside __main__ — these tests exercise the
class directly without running the main loop.
"""
import io
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Stub heavy deps so risk_monitor is importable in the test env (no real
# Telegram / Supabase / dotenv available).
for _mod in ("telebot", "telebot.types", "supabase", "dotenv"):
    sys.modules.setdefault(_mod, MagicMock())
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import risk_monitor as rm


# ════════════════════════════════════════════════════════════════════════════════
# _StdoutTee — duplicate stdout to a file
# ════════════════════════════════════════════════════════════════════════════════

class TestStdoutTee:
    def test_writes_to_both_stream_and_file(self, tmp_path):
        path = tmp_path / "out.log"
        underlying = io.StringIO()
        tee = rm._StdoutTee(underlying, str(path))
        tee.write("hello\n")
        tee.write("world\n")
        assert underlying.getvalue() == "hello\nworld\n"
        assert path.read_text() == "hello\nworld\n"

    def test_empty_writes_do_not_touch_file(self, tmp_path):
        path = tmp_path / "out.log"
        underlying = io.StringIO()
        tee = rm._StdoutTee(underlying, str(path))
        tee.write("")
        assert not path.exists()  # empty payload, no file created

    def test_file_failure_does_not_break_stdout(self, tmp_path):
        """If the log path is unwritable, the stream write must still succeed.
        Logging must never block the engine."""
        underlying = io.StringIO()
        bad_path = "/proc/this/cannot/exist/log.txt"
        tee = rm._StdoutTee(underlying, bad_path)
        tee.write("important")
        assert underlying.getvalue() == "important"

    def test_stream_failure_swallowed(self, tmp_path):
        """If the underlying stream raises, the file write should still happen."""
        path = tmp_path / "out.log"
        broken = MagicMock()
        broken.write.side_effect = IOError("stdout closed")
        tee = rm._StdoutTee(broken, str(path))
        tee.write("survives\n")
        assert path.read_text() == "survives\n"

    def test_flush_forwards_to_underlying(self):
        underlying = MagicMock()
        tee = rm._StdoutTee(underlying, "/tmp/unused")
        tee.flush()
        underlying.flush.assert_called_once()

    def test_attribute_passthrough(self):
        """Some libraries probe attributes like isatty(). Pass them through."""
        underlying = MagicMock()
        underlying.isatty.return_value = False
        tee = rm._StdoutTee(underlying, "/tmp/unused")
        assert tee.isatty() is False

    def test_appends_not_overwrites(self, tmp_path):
        path = tmp_path / "out.log"
        path.write_text("existing\n")
        underlying = io.StringIO()
        tee = rm._StdoutTee(underlying, str(path))
        tee.write("new\n")
        assert path.read_text() == "existing\nnew\n"


# ════════════════════════════════════════════════════════════════════════════════
# _rotate_log_file — keep only last _LOG_MAX_LINES
# ════════════════════════════════════════════════════════════════════════════════

class TestRotateLogFile:
    def test_no_op_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("risk_monitor._LOG_FILE", str(tmp_path / "missing.log"))
        rm._rotate_log_file()  # must not raise

    def test_no_op_when_under_max_lines(self, tmp_path, monkeypatch):
        path = tmp_path / "short.log"
        path.write_text("\n".join(f"line{i}" for i in range(100)) + "\n")
        monkeypatch.setattr("risk_monitor._LOG_FILE", str(path))
        monkeypatch.setattr("risk_monitor._LOG_MAX_LINES", 2000)
        rm._rotate_log_file()
        # File unchanged
        assert len(path.read_text().splitlines()) == 100

    def test_truncates_to_last_n_lines(self, tmp_path, monkeypatch):
        path = tmp_path / "long.log"
        path.write_text("\n".join(f"line{i}" for i in range(3000)) + "\n")
        monkeypatch.setattr("risk_monitor._LOG_FILE", str(path))
        monkeypatch.setattr("risk_monitor._LOG_MAX_LINES", 100)
        rm._rotate_log_file()
        lines = path.read_text().splitlines()
        assert len(lines) == 100
        # Kept the LAST 100, not the first
        assert lines[0]  == "line2900"
        assert lines[-1] == "line2999"

    def test_unwritable_target_is_silent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("risk_monitor._LOG_FILE", "/proc/never/writable")
        rm._rotate_log_file()  # must not raise
