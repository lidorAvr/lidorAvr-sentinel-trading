"""
Tests for developer menu helpers:
  - _dev_sync_check() rate-limiting logic
  - _dev_sync_record() state tracking
  - _read_last_log_lines() log reader
All deterministic; no network, no Telegram, no IBKR calls.
"""
import sys, os, json, tempfile
import pytest
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
import telegram_devops as devops
from datetime import datetime, timedelta

# After Phase 4 Step 8, dev-menu helpers live in telegram_devops.py.
# tb still re-exports them for backwards compatibility, but patch.object
# must target the module that owns the lexical scope — telegram_devops.
# The alias below lets us keep tb.* attribute references in test bodies
# while patching where the function actually reads the constant.


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
            with patch.object(devops, "_DEV_STATE_FILE", path):
                allowed, reason, _ = tb._dev_sync_check()
        assert allowed is True
        assert reason == ""

    def test_daily_limit_reached_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._write_state(td, count=tb._DEV_SYNC_MAX_PER_DAY)
            with patch.object(devops, "_DEV_STATE_FILE", path):
                allowed, reason, _ = tb._dev_sync_check()
        assert allowed is False
        assert "מגבלה" in reason

    def test_count_from_yesterday_does_not_block(self):
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        with tempfile.TemporaryDirectory() as td:
            path = self._write_state(td, count=tb._DEV_SYNC_MAX_PER_DAY, date=yesterday)
            with patch.object(devops, "_DEV_STATE_FILE", path):
                allowed, _, _ = tb._dev_sync_check()
        assert allowed is True

    def test_cooldown_active_within_3h_blocks(self):
        recent_ts = (datetime.now() - timedelta(hours=1)).isoformat()
        with tempfile.TemporaryDirectory() as td:
            path = self._write_state(td, last_ts=recent_ts)
            with patch.object(devops, "_DEV_STATE_FILE", path):
                allowed, reason, _ = tb._dev_sync_check()
        assert allowed is False
        assert "Cooldown" in reason

    def test_cooldown_expired_after_3h_allows(self):
        old_ts = (datetime.now() - timedelta(hours=tb._DEV_SYNC_COOLDOWN_HOURS + 0.1)).isoformat()
        with tempfile.TemporaryDirectory() as td:
            path = self._write_state(td, last_ts=old_ts)
            with patch.object(devops, "_DEV_STATE_FILE", path):
                allowed, _, _ = tb._dev_sync_check()
        assert allowed is True

    def test_exactly_at_cooldown_boundary_blocks(self):
        # 2.9 hours ago — still within 3h cooldown
        recent_ts = (datetime.now() - timedelta(hours=2.9)).isoformat()
        with tempfile.TemporaryDirectory() as td:
            path = self._write_state(td, last_ts=recent_ts)
            with patch.object(devops, "_DEV_STATE_FILE", path):
                allowed, _, _ = tb._dev_sync_check()
        assert allowed is False

    def test_missing_state_file_is_allowed(self):
        with patch.object(devops, "_DEV_STATE_FILE", "/nonexistent/dev_state.json"):
            allowed, reason, _ = tb._dev_sync_check()
        assert allowed is True

    def test_returns_state_dict(self):
        with patch.object(devops, "_DEV_STATE_FILE", "/nonexistent/dev_state.json"):
            allowed, _, state = tb._dev_sync_check()
        assert isinstance(state, dict)

    def test_reason_empty_when_allowed(self):
        with patch.object(devops, "_DEV_STATE_FILE", "/nonexistent/dev_state.json"):
            allowed, reason, _ = tb._dev_sync_check()
        assert allowed is True
        assert reason == ""


# ── _dev_sync_record ───────────────────────────────────────────────────────────

class TestDevSyncRecord:
    def test_creates_state_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dev_state.json")
            with patch.object(devops, "_DEV_STATE_FILE", path):
                tb._dev_sync_record({})
            assert os.path.exists(path)

    def test_count_increments_from_zero(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dev_state.json")
            with patch.object(devops, "_DEV_STATE_FILE", path):
                tb._dev_sync_record({})
                state = json.load(open(path))
            assert state["count_today"] == 1

    def test_count_increments_from_existing(self):
        today = datetime.now().strftime("%Y-%m-%d")
        initial = {"date": today, "count_today": 1, "last_ts": datetime.now().isoformat()}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dev_state.json")
            with patch.object(devops, "_DEV_STATE_FILE", path):
                tb._dev_sync_record(initial)
                state = json.load(open(path))
            assert state["count_today"] == 2

    def test_last_ts_is_set(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dev_state.json")
            with patch.object(devops, "_DEV_STATE_FILE", path):
                tb._dev_sync_record({})
                state = json.load(open(path))
            assert "last_ts" in state
            ts = datetime.fromisoformat(state["last_ts"])
            assert (datetime.now() - ts).total_seconds() < 5

    def test_date_is_today(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dev_state.json")
            with patch.object(devops, "_DEV_STATE_FILE", path):
                tb._dev_sync_record({})
                state = json.load(open(path))
            assert state["date"] == datetime.now().strftime("%Y-%m-%d")

    def test_record_then_check_shows_count(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "dev_state.json")
            with patch.object(devops, "_DEV_STATE_FILE", path):
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


# ── _process_uploaded_ibkr_xml ────────────────────────────────────────────────

_VALID_XML = (
    "<FlexQueryResponse>"
    "<ChangeInNAV endingValue='8500.50' />"
    "<Trades><Trade id='1' /><Trade id='2' /></Trades>"
    "</FlexQueryResponse>"
)

_NO_NAV_NO_TRADES_XML = "<FlexQueryResponse><SomeOtherSection /></FlexQueryResponse>"


def _make_message(file_name="report.xml", xml_bytes=_VALID_XML.encode()):
    msg = MagicMock()
    msg.chat.id = 99
    msg.document.file_name = file_name
    msg.document.file_id = "fid123"
    tb.bot.get_file.return_value = MagicMock(file_path="path/to/file")
    tb.bot.download_file.return_value = xml_bytes
    return msg


class TestProcessUploadedIbkrXml:
    def setup_method(self):
        tb.bot.reset_mock()

    def test_success_sends_success_message(self, tmp_path):
        msg = _make_message()
        with (patch.object(devops, "_REPORTS_DIR", str(tmp_path)),
              patch.object(devops, "_CONFIG_PATH", str(tmp_path / "cfg.json")),
              patch.object(devops, "MANUAL_RESULT_FILE", str(tmp_path / "result.json"))):
            tb._process_uploaded_ibkr_xml(99, msg)
        calls = [str(c) for c in tb.bot.send_message.call_args_list]
        assert any("✅" in c or "הצלחה" in c for c in calls)

    def test_success_creates_xml_file(self, tmp_path):
        msg = _make_message()
        with (patch.object(devops, "_REPORTS_DIR", str(tmp_path)),
              patch.object(devops, "_CONFIG_PATH", str(tmp_path / "cfg.json")),
              patch.object(devops, "MANUAL_RESULT_FILE", str(tmp_path / "result.json"))):
            tb._process_uploaded_ibkr_xml(99, msg)
        xml_files = list(tmp_path.glob("ibkr_*.xml"))
        assert len(xml_files) == 1

    def test_success_updates_nav_in_config(self, tmp_path):
        cfg_path = tmp_path / "cfg.json"
        cfg_path.write_text('{"total_deposited": 5000.0}')
        msg = _make_message()
        with (patch.object(devops, "_REPORTS_DIR", str(tmp_path)),
              patch.object(devops, "_CONFIG_PATH", str(cfg_path)),
              patch.object(devops, "MANUAL_RESULT_FILE", str(tmp_path / "result.json"))):
            tb._process_uploaded_ibkr_xml(99, msg)
        import json as _json
        cfg = _json.load(open(cfg_path))
        assert cfg["nav"] == pytest.approx(8500.50)
        assert "nav_updated_at" in cfg

    def test_success_writes_manual_result_file(self, tmp_path):
        msg = _make_message()
        result_path = tmp_path / "result.json"
        with (patch.object(devops, "_REPORTS_DIR", str(tmp_path)),
              patch.object(devops, "_CONFIG_PATH", str(tmp_path / "cfg.json")),
              patch.object(devops, "MANUAL_RESULT_FILE", str(result_path))):
            tb._process_uploaded_ibkr_xml(99, msg)
        import json as _json
        result = _json.load(open(result_path))
        assert result["status"] == "success"
        assert result["nav"] == pytest.approx(8500.50)
        assert result.get("source") == "manual_upload"

    def test_non_xml_file_rejected(self, tmp_path):
        msg = _make_message(file_name="report.csv")
        with patch.object(devops, "_REPORTS_DIR", str(tmp_path)):
            tb._process_uploaded_ibkr_xml(99, msg)
        calls = [str(c) for c in tb.bot.send_message.call_args_list]
        assert any("XML" in c or "❌" in c for c in calls)
        assert not list(tmp_path.glob("ibkr_*.xml"))

    def test_no_nav_no_trades_rejected(self, tmp_path):
        msg = _make_message(xml_bytes=_NO_NAV_NO_TRADES_XML.encode())
        with (patch.object(devops, "_REPORTS_DIR", str(tmp_path)),
              patch.object(devops, "_CONFIG_PATH", str(tmp_path / "cfg.json"))):
            tb._process_uploaded_ibkr_xml(99, msg)
        calls = [str(c) for c in tb.bot.send_message.call_args_list]
        assert any("⚠️" in c or "תקין" in c for c in calls)

    def test_invalid_xml_returns_error(self, tmp_path):
        msg = _make_message(xml_bytes=b"<not valid xml <<>>")
        with (patch.object(devops, "_REPORTS_DIR", str(tmp_path)),
              patch.object(devops, "_CONFIG_PATH", str(tmp_path / "cfg.json"))):
            tb._process_uploaded_ibkr_xml(99, msg)
        calls = [str(c) for c in tb.bot.send_message.call_args_list]
        assert any("❌" in c for c in calls)

    def test_old_reports_cleaned_up(self, tmp_path):
        for i in range(5):
            (tmp_path / f"ibkr_2025-01-0{i+1}_00-00.xml").write_text("<old/>")
        msg = _make_message()
        with (patch.object(devops, "_REPORTS_DIR", str(tmp_path)),
              patch.object(devops, "_CONFIG_PATH", str(tmp_path / "cfg.json")),
              patch.object(devops, "MANUAL_RESULT_FILE", str(tmp_path / "result.json")),
              patch.object(devops, "_REPORTS_TO_KEEP", 3)):
            tb._process_uploaded_ibkr_xml(99, msg)
        xml_files = list(tmp_path.glob("ibkr_*.xml"))
        assert len(xml_files) <= 3
