"""
Tests for developer menu helpers:
  - _dev_sync_check() rate-limiting logic
  - _dev_sync_record() state tracking
  - _read_last_log_lines() log reader
All deterministic; no network, no Telegram, no IBKR calls.
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Mock all heavy dependencies before importing telegram_bot ──────────────────
from unittest.mock import MagicMock, patch

for _mod in ("telebot", "telebot.types", "supabase", "dotenv",
             "adaptive_risk_engine", "engine_core", "telegram_formatters"):
    sys.modules.setdefault(_mod, MagicMock())

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import telegram_bot as tb
from datetime import datetime, timedelta


# ── _dev_sync_check ────────────────────────────────────────────────────────────

class TestDevSyncCheck:
    def _write_state(self, tmpdir, count=0, last_ts=None, date=None):
        state = {}
        today = datetime.now().strftime("%Y-%m-%d")
        if date is None:
            date = today
        if count > 0:
            state["date"] = date
            state["count_today"] = count
        if last_ts is not None:
            state["last_ts"] = last_ts
        path = os.path.join(tmpdir, "ibkr_dev_state.json")
        with open(path, "w") as f:
            json.dump(state, f)
        return path

    def test_fresh_state_is_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._write_state(td)
            with patch.object(tb, "_DEV_STATE_FILE", path):
                allowed, reason, _ = tb._dev_sync_check()
        assert allowed is True
        assert reason == ""

    def test_daily_limit_reached_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._write_state(td, count=tb._DEV_SYNC_MAX_PER_DAY)
            with patch.object(tb, "_DEV_STATE_FILE", path):
                allowed, reason, _ = tb._dev_sync_check()
        assert allowed is False
        assert "מגבלה" in reason

    def test_count_from_yesterday_does_not_block(self):
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        with tempfile.TemporaryDirectory() as td:
            path = self._write_state(td, count=tb._DEV_SYNC_MAX_PER_DAY, date=yesterday)
            with patch.object(tb, "_DEV_STATE_FILE", path):
                allowed, _, _ = tb._dev_sync_check()
        assert allowed is True

    def test_cooldown_active_within_3h_blocks(self):
        recent_ts = (datetime.now() - timedelta(hours=1)).isoformat()
        with tempfile.TemporaryDirectory() as td:
            path = self._write_state(td, last_ts=recent_ts)
            with patch.object(tb, "_DEV_STATE_FILE", path):
                allowed, reason, _ = tb._dev_sync_check()
        assert allowed is False
        assert "Cooldown" in reason

    def test_cooldown_expired_after_3h_allows(self):
        old_ts = (datetime.now() - timedelta(hours=tb._DEV_SYNC_COOLDOWN_HOURS + 0.1)).isoformat()
        with tempfile.TemporaryDirectory() as td:
            path = self._write_state(td, last_ts=old_ts)
            with patch.object(tb, "_DEV_STATE_FILE", path):
                allowed, _, _ = tb._dev_sync_check()
        assert allowed is True

    def test_exactly_at_cooldown_boundary_blocks(self):
        # 2.9 hours ago — still within 3h cooldown
        recent_ts = (datetime.now() - timedelta(hours=2.9)).isoformat()
        with tempfile.TemporaryDirectory() as td:
            path = self._write_state(td, last_ts=recent_ts)
            with patch.object(tb, "_DEV_STATE_FILE", path):
                allowed, _, _ = tb._dev_sync_check()
        assert allowed is False

    def test_missing_state_file_is_allowed(self):
        with patch.object(tb, "_DEV_STATE_FILE", "/nonexistent/dev_state.json"):
            allowed, reason, _ = tb._dev_sync_check()
        assert allowed is True

    def test_returns_state_dict(self):
        with patch.object(tb, "_DEV_STATE_FILE", "/nonexistent/dev_state.json"):
            allowed, _, state = tb._dev_sync_check()
        assert isinstance(state, dict)

    def test_reason_empty_when_allowed(self):
        with patch.object(tb, "_DEV_STATE_FILE", "/nonexistent/dev_state.json"):
            allowed, reason, _ = tb._dev_sync_check()
        assert allowed is True
        assert reason == ""


# ── _dev_sync_record ───────────────────────────────────────────────────────────

class TestDevSyncRecord:
    def test_creates_state_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dev_state.json")
            with patch.object(tb, "_DEV_STATE_FILE", path):
                tb._dev_sync_record({})
            assert os.path.exists(path)

    def test_count_increments_from_zero(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dev_state.json")
            with patch.object(tb, "_DEV_STATE_FILE", path):
                tb._dev_sync_record({})
                state = json.load(open(path))
            assert state["count_today"] == 1

    def test_count_increments_from_existing(self):
        today = datetime.now().strftime("%Y-%m-%d")
        initial = {"date": today, "count_today": 1, "last_ts": datetime.now().isoformat()}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dev_state.json")
            with patch.object(tb, "_DEV_STATE_FILE", path):
                tb._dev_sync_record(initial)
                state = json.load(open(path))
            assert state["count_today"] == 2

    def test_last_ts_is_set(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dev_state.json")
            with patch.object(tb, "_DEV_STATE_FILE", path):
                tb._dev_sync_record({})
                state = json.load(open(path))
            assert "last_ts" in state
            ts = datetime.fromisoformat(state["last_ts"])
            assert (datetime.now() - ts).total_seconds() < 5

    def test_date_is_today(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dev_state.json")
            with patch.object(tb, "_DEV_STATE_FILE", path):
                tb._dev_sync_record({})
                state = json.load(open(path))
            assert state["date"] == datetime.now().strftime("%Y-%m-%d")

    def test_record_then_check_shows_count(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dev_state.json")
            with patch.object(tb, "_DEV_STATE_FILE", path):
                tb._dev_sync_record({})
                tb._dev_sync_record(json.load(open(path)))
                _, _, state = tb._dev_sync_check()
                assert state["count_today"] == 2


# ── _read_last_log_lines ───────────────────────────────────────────────────────

class TestReadLastLogLines:
    def test_nonexistent_file_returns_graceful_message(self):
        result = tb._read_last_log_lines("/nonexistent/log.txt", 50)
        assert "לא קיים" in result or "קובץ" in result

    def test_returns_last_n_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            for i in range(100):
                f.write(f"line {i}\n")
            path = f.name
        try:
            result = tb._read_last_log_lines(path, 10)
            lines = result.strip().splitlines()
            assert len(lines) == 10
            assert "line 99" in lines[-1]
            assert "line 90" in lines[0]
        finally:
            os.unlink(path)

    def test_fewer_lines_than_n_returns_all(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("only one line\n")
            path = f.name
        try:
            result = tb._read_last_log_lines(path, 50)
            assert "only one line" in result
        finally:
            os.unlink(path)

    def test_empty_file_returns_empty_marker(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            path = f.name
        try:
            result = tb._read_last_log_lines(path, 50)
            assert result in ("", "(ריק)")
        finally:
            os.unlink(path)

    def test_returns_string(self):
        result = tb._read_last_log_lines("/nonexistent", 10)
        assert isinstance(result, str)
