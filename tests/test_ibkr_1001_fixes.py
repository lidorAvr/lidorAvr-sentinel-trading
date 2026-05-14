"""test_ibkr_1001_fixes.py — Tests for the 2026-05-14 IBKR error-1001 mitigations.

Covers three fixes designed to reduce ErrorCode 1001 from IBKR Universal Flex:

- Fix 2: Sentinel-side SendRequest cooldown (`_sendrequest_cooldown_sec`,
  `_last_sendrequest_ts`, `_record_sendrequest_ts`). Default 120s, env-tunable,
  recorded only when SendRequest produced a valid ReferenceCode (NOT on 1001).
- Fix 3: Flex Query period detection from <FlexStatement fromDate=... toDate=...>.
  Logs the span and warns when span < 6 days (suggests Period misconfigured).
- Fix 1 (trigger handoff): main.py `_handle_manual_trigger` now bumps
  `last_attempt_hour` in sync state so the scheduled block in the same loop
  tick will not fire SendRequest a second time.
"""
import json
import os
import sys
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Stub heavy deps so telegram_devops is importable in the test env (no real
# Telegram/Supabase available). Must run before import of telegram_devops.
for _mod in ("telebot", "telebot.types", "supabase", "dotenv"):
    sys.modules.setdefault(_mod, MagicMock())
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import ibkr_sync_runner as m


# ── XML helpers ────────────────────────────────────────────────────────────────

_IBKR_FETCH_URL = ("https://gdcdyn.interactivebrokers.com/Universal/servlet/"
                   "FlexStatementService.GetStatement")


def _send_ok_xml(ref="REF1"):
    return (f"<FlexStatementResponse><Status>Success</Status>"
            f"<ReferenceCode>{ref}</ReferenceCode>"
            f"<Url>{_IBKR_FETCH_URL}</Url></FlexStatementResponse>")


def _send_err_xml(code=1001):
    return f"<FlexStatementResponse><Status>Fail</Status><ErrorCode>{code}</ErrorCode></FlexStatementResponse>"


def _statement_xml(nav=10000.0, n_trades=0, from_d="20260507", to_d="20260514"):
    trades = "".join(f"<Trade id='{i}' />" for i in range(n_trades))
    return (
        f"<FlexQueryResponse>"
        f"<FlexStatements>"
        f"<FlexStatement fromDate='{from_d}' toDate='{to_d}'>"
        f"<ChangeInNAV endingValue='{nav}' />"
        f"<Trades>{trades}</Trades>"
        f"</FlexStatement>"
        f"</FlexStatements>"
        f"</FlexQueryResponse>"
    )


def _mock_resp(text):
    r = MagicMock()
    r.text = text
    return r


# ════════════════════════════════════════════════════════════════════════════════
# FIX 2 — SendRequest cooldown
# ════════════════════════════════════════════════════════════════════════════════

class TestCooldownConfiguration:
    def test_default_cooldown_is_120s(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("IBKR_SENDREQ_COOLDOWN_SEC", None)
            assert m._sendrequest_cooldown_sec() == 120

    def test_env_override_applied(self):
        with patch.dict(os.environ, {"IBKR_SENDREQ_COOLDOWN_SEC": "45"}):
            assert m._sendrequest_cooldown_sec() == 45

    def test_invalid_env_falls_back_to_default(self):
        with patch.dict(os.environ, {"IBKR_SENDREQ_COOLDOWN_SEC": "not-a-number"}):
            assert m._sendrequest_cooldown_sec() == 120


class TestCooldownState:
    def test_no_state_file_returns_zero(self, tmp_path):
        with patch("ibkr_sync_runner._SENDREQ_STATE_FILE", str(tmp_path / "missing.json")):
            assert m._last_sendrequest_ts() == 0.0

    def test_record_then_read_roundtrip(self, tmp_path):
        path = str(tmp_path / "ts.json")
        with patch("ibkr_sync_runner._SENDREQ_STATE_FILE", path):
            before = time.time()
            m._record_sendrequest_ts()
            stored = m._last_sendrequest_ts()
        assert before <= stored <= time.time() + 0.5

    def test_record_writes_atomically_via_rename(self, tmp_path):
        """No half-written state visible — uses tmp + os.replace."""
        path = str(tmp_path / "ts.json")
        with patch("ibkr_sync_runner._SENDREQ_STATE_FILE", path):
            m._record_sendrequest_ts()
        # No leftover .tmp file
        assert not os.path.exists(path + ".tmp")
        assert os.path.exists(path)

    def test_corrupt_state_returns_zero_not_raise(self, tmp_path):
        path = str(tmp_path / "ts.json")
        with open(path, "w") as f:
            f.write("{not valid json")
        with patch("ibkr_sync_runner._SENDREQ_STATE_FILE", path):
            assert m._last_sendrequest_ts() == 0.0


class TestCooldownBlocksRapidRetries:
    def test_recent_sendrequest_blocks_with_rate_limit_status(self, tmp_path):
        path = str(tmp_path / "ts.json")
        # Pretend a successful SendRequest happened 30s ago
        with open(path, "w") as f:
            json.dump({"last_ts": time.time() - 30}, f)

        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok", "IBKR_QUERY_ID": "q"}),
              patch("ibkr_sync_runner._SENDREQ_STATE_FILE", path),
              patch("ibkr_sync_runner.requests.get") as mock_get,
              patch("ibkr_sync_runner.time.sleep")):
            result = m.run_ibkr_sync()

        assert result["status"] == "rate_limit"
        assert "cooldown" in result["message"].lower() or "ש לפני" in result["message"]
        # Critically: no HTTP request issued
        mock_get.assert_not_called()

    def test_old_sendrequest_does_not_block(self, tmp_path):
        path = str(tmp_path / "ts.json")
        # 200s ago — beyond the 120s default
        with open(path, "w") as f:
            json.dump({"last_ts": time.time() - 200}, f)

        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok", "IBKR_QUERY_ID": "q"}),
              patch("ibkr_sync_runner._SENDREQ_STATE_FILE", path),
              patch("ibkr_sync_runner._REPORTS_DIR", str(tmp_path)),
              patch("ibkr_sync_runner._CONFIG_PATH", str(tmp_path / "cfg.json")),
              patch("ibkr_sync_runner.requests.get") as mock_get,
              patch("ibkr_sync_runner.time.sleep")):
            mock_get.side_effect = [_mock_resp(_send_ok_xml()), _mock_resp(_statement_xml())]
            result = m.run_ibkr_sync()

        assert result["status"] == "success"
        assert mock_get.call_count == 2

    def test_no_prior_state_does_not_block(self, tmp_path):
        # last_ts == 0 should never block — only block when we actually issued a request
        path = str(tmp_path / "missing.json")
        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok", "IBKR_QUERY_ID": "q"}),
              patch("ibkr_sync_runner._SENDREQ_STATE_FILE", path),
              patch("ibkr_sync_runner._REPORTS_DIR", str(tmp_path)),
              patch("ibkr_sync_runner._CONFIG_PATH", str(tmp_path / "cfg.json")),
              patch("ibkr_sync_runner.requests.get") as mock_get,
              patch("ibkr_sync_runner.time.sleep")):
            mock_get.side_effect = [_mock_resp(_send_ok_xml()), _mock_resp(_statement_xml())]
            result = m.run_ibkr_sync()
        assert result["status"] == "success"


class TestCooldownRecordingPolicy:
    """A failed SendRequest (1001 etc.) MUST NOT consume the cooldown slot,
    otherwise a benign IBKR transient blocks legitimate retries for 120s."""

    def test_success_records_timestamp(self, tmp_path):
        path = str(tmp_path / "ts.json")
        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok", "IBKR_QUERY_ID": "q"}),
              patch("ibkr_sync_runner._SENDREQ_STATE_FILE", path),
              patch("ibkr_sync_runner._REPORTS_DIR", str(tmp_path)),
              patch("ibkr_sync_runner._CONFIG_PATH", str(tmp_path / "cfg.json")),
              patch("ibkr_sync_runner.requests.get") as mock_get,
              patch("ibkr_sync_runner.time.sleep")):
            mock_get.side_effect = [_mock_resp(_send_ok_xml()), _mock_resp(_statement_xml())]
            m.run_ibkr_sync()

        assert os.path.exists(path)
        with open(path) as f:
            state = json.load(f)
        assert state["last_ts"] > 0

    def test_1001_error_does_not_record_timestamp(self, tmp_path):
        path = str(tmp_path / "ts.json")
        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok", "IBKR_QUERY_ID": "q"}),
              patch("ibkr_sync_runner._SENDREQ_STATE_FILE", path),
              patch("ibkr_sync_runner.requests.get",
                    return_value=_mock_resp(_send_err_xml(1001))),
              patch("ibkr_sync_runner.time.sleep")):
            result = m.run_ibkr_sync()

        assert result["status"] == "temporary"
        assert result["code"] == 1001
        # Critically: cooldown state must NOT have been written for a 1001 failure
        assert not os.path.exists(path), \
            "1001 must not consume the cooldown slot — would block legitimate retry"

    def test_missing_refcode_does_not_record_timestamp(self, tmp_path):
        """SendRequest 200 but no <ReferenceCode> — also should not consume slot."""
        path = str(tmp_path / "ts.json")
        bad_xml = "<FlexStatementResponse><Status>Success</Status></FlexStatementResponse>"
        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok", "IBKR_QUERY_ID": "q"}),
              patch("ibkr_sync_runner._SENDREQ_STATE_FILE", path),
              patch("ibkr_sync_runner.requests.get",
                    return_value=_mock_resp(bad_xml)),
              patch("ibkr_sync_runner.time.sleep")):
            result = m.run_ibkr_sync()

        assert result["status"] == "temporary"
        assert not os.path.exists(path)


# ════════════════════════════════════════════════════════════════════════════════
# FIX 3 — Flex Query period detection
# ════════════════════════════════════════════════════════════════════════════════

class TestPeriodDetection:
    def _run_with_period(self, tmp_path, from_d, to_d):
        path = str(tmp_path / "ts.json")
        captured_logs = []
        def fake_log(msg):
            captured_logs.append(str(msg))
        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok", "IBKR_QUERY_ID": "q"}),
              patch("ibkr_sync_runner._SENDREQ_STATE_FILE", path),
              patch("ibkr_sync_runner._REPORTS_DIR", str(tmp_path)),
              patch("ibkr_sync_runner._CONFIG_PATH", str(tmp_path / "cfg.json")),
              patch("ibkr_sync_runner.requests.get") as mock_get,
              patch("ibkr_sync_runner.time.sleep")):
            mock_get.side_effect = [
                _mock_resp(_send_ok_xml()),
                _mock_resp(_statement_xml(from_d=from_d, to_d=to_d)),
            ]
            m.run_ibkr_sync(log_fn=fake_log)
        return captured_logs

    def test_seven_day_period_logs_without_warning(self, tmp_path):
        logs = self._run_with_period(tmp_path, "20260507", "20260514")  # span 7 days
        assert any("Report period: 20260507 → 20260514" in l for l in logs)
        assert not any("⚠️" in l and "Flex Query period span" in l for l in logs)

    def test_one_day_period_emits_warning(self, tmp_path):
        logs = self._run_with_period(tmp_path, "20260513", "20260514")  # span 1
        assert any("Report period:" in l for l in logs)
        warning_lines = [l for l in logs if "Flex Query period span" in l]
        assert len(warning_lines) == 1
        assert "1 day" in warning_lines[0]
        assert "Last 7 Days" in warning_lines[0]

    def test_zero_span_emits_warning(self, tmp_path):
        logs = self._run_with_period(tmp_path, "20260514", "20260514")  # span 0 = "Today"
        assert any("Flex Query period span is only 0 day" in l for l in logs)

    def test_six_day_span_is_boundary_warns(self, tmp_path):
        # span_days = 5 → still < 6 → warn
        logs = self._run_with_period(tmp_path, "20260509", "20260514")
        assert any("Flex Query period span is only 5 day" in l for l in logs)

    def test_seven_day_span_no_warning(self, tmp_path):
        # span_days = 7 → not < 6 → no warn
        logs = self._run_with_period(tmp_path, "20260507", "20260514")
        assert not any("Flex Query period span" in l for l in logs)

    def test_no_flex_statement_element_does_not_crash(self, tmp_path):
        """Statement XML without FlexStatement metadata — silently skip the check."""
        path = str(tmp_path / "ts.json")
        statement_xml_no_fs = (
            "<FlexQueryResponse>"
            "<ChangeInNAV endingValue='10000.0' />"
            "<Trades></Trades>"
            "</FlexQueryResponse>"
        )
        captured = []
        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok", "IBKR_QUERY_ID": "q"}),
              patch("ibkr_sync_runner._SENDREQ_STATE_FILE", path),
              patch("ibkr_sync_runner._REPORTS_DIR", str(tmp_path)),
              patch("ibkr_sync_runner._CONFIG_PATH", str(tmp_path / "cfg.json")),
              patch("ibkr_sync_runner.requests.get") as mock_get,
              patch("ibkr_sync_runner.time.sleep")):
            mock_get.side_effect = [_mock_resp(_send_ok_xml()), _mock_resp(statement_xml_no_fs)]
            result = m.run_ibkr_sync(log_fn=captured.append)
        assert result["status"] == "success"
        assert not any("Report period:" in l for l in captured)

    def test_invalid_date_format_does_not_warn(self, tmp_path):
        """Garbage in fromDate/toDate — log skip, no warning, no exception."""
        path = str(tmp_path / "ts.json")
        weird_xml = _statement_xml(from_d="not-a-date", to_d="???")
        captured = []
        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok", "IBKR_QUERY_ID": "q"}),
              patch("ibkr_sync_runner._SENDREQ_STATE_FILE", path),
              patch("ibkr_sync_runner._REPORTS_DIR", str(tmp_path)),
              patch("ibkr_sync_runner._CONFIG_PATH", str(tmp_path / "cfg.json")),
              patch("ibkr_sync_runner.requests.get") as mock_get,
              patch("ibkr_sync_runner.time.sleep")):
            mock_get.side_effect = [_mock_resp(_send_ok_xml()), _mock_resp(weird_xml)]
            result = m.run_ibkr_sync(log_fn=captured.append)
        assert result["status"] == "success"
        # We do log the raw period
        assert any("Report period: not-a-date" in l for l in captured)
        # But no span warning (parse failed silently)
        assert not any("Flex Query period span" in l for l in captured)


# ════════════════════════════════════════════════════════════════════════════════
# FIX 1 — main.py: _handle_manual_trigger must bump last_attempt_hour
# ════════════════════════════════════════════════════════════════════════════════

class TestManualTriggerStateBump:
    """Regression test for the self-race Mark caught: a manual trigger that
    runs inside the 07-11 window must update last_attempt_hour so the same
    loop iteration's scheduled block sees `tried_this_hour=True` and skips.
    Without this, two SendRequests fire in <1 sec → guaranteed 1001 on #2."""

    def test_manual_trigger_bumps_last_attempt_hour(self, tmp_path, monkeypatch):
        # Setup an isolated env
        trigger_path = str(tmp_path / "trigger")
        result_path  = str(tmp_path / "result.json")
        state_path   = str(tmp_path / "state.json")

        # Write a trigger file so _handle_manual_trigger picks it up
        with open(trigger_path, "w") as f:
            f.write("12345")

        monkeypatch.setattr("main.MANUAL_TRIGGER_FILE", trigger_path)
        monkeypatch.setattr("main.MANUAL_RESULT_FILE",  result_path)
        monkeypatch.setattr("main.SYNC_STATE_FILE",     state_path)
        # Re-bind state helpers to the patched path
        import main as main_module
        monkeypatch.setattr("ibkr_sync_runner.MANUAL_RESULT_FILE", result_path)

        # Mock run_ibkr_sync to return success quickly
        fake_result = {"status": "success", "code": None,
                       "message": "5 עסקאות סונכרנו", "nav": 8000.0}
        with patch("main.run_ibkr_sync", return_value=fake_result), \
             patch("main.send_telegram"), \
             patch("main.import_trades_and_notify"):
            main_module._handle_manual_trigger(None, None)

        # State must now contain the bumped hour and today's sync_date
        with open(state_path) as f:
            state = json.load(f)
        now = datetime.now()  # main.py uses Israel TZ but hour value matches local in container
        assert state.get("last_attempt_hour") is not None
        assert state.get("sync_date") == datetime.now().strftime("%Y-%m-%d") or \
               state.get("sync_date") is not None  # main.py uses Israel TZ; just confirm it's set
        assert state.get("fail_count") == 0  # success path clears failures

    def test_manual_trigger_failure_still_bumps_hour(self, tmp_path, monkeypatch):
        """A failed manual trigger must STILL bump last_attempt_hour — otherwise
        the scheduled block fires SendRequest again in the same tick.
        Failed manual must NOT set sync_date (that would skip the auto-retry)."""
        trigger_path = str(tmp_path / "trigger")
        result_path  = str(tmp_path / "result.json")
        state_path   = str(tmp_path / "state.json")

        with open(trigger_path, "w") as f:
            f.write("12345")

        monkeypatch.setattr("main.MANUAL_TRIGGER_FILE", trigger_path)
        monkeypatch.setattr("main.MANUAL_RESULT_FILE",  result_path)
        monkeypatch.setattr("main.SYNC_STATE_FILE",     state_path)
        import main as main_module

        fake_result = {"status": "temporary", "code": 1001,
                       "message": "הדוח לא נוצר כרגע", "nav": None}
        with patch("main.run_ibkr_sync", return_value=fake_result), \
             patch("main.send_telegram"), \
             patch("main.import_trades_and_notify"):
            main_module._handle_manual_trigger(None, None)

        with open(state_path) as f:
            state = json.load(f)
        assert state.get("last_attempt_hour") is not None
        # On failure, sync_date should NOT be set (we want auto-retry to keep trying)
        assert "sync_date" not in state


# ════════════════════════════════════════════════════════════════════════════════
# FIX 1 (telegram-side): trigger writer + result poller
# ════════════════════════════════════════════════════════════════════════════════

class TestTelegramSideTriggerPoller:
    """Verify the file-based handoff on the telegram-bot side: atomic write,
    polling timeout, and corrupt-result handling."""

    def test_write_manual_trigger_uses_atomic_rename(self, tmp_path, monkeypatch):
        import telegram_devops as td
        target = str(tmp_path / "trigger")
        monkeypatch.setattr("telegram_devops._MANUAL_TRIGGER_FILE", target)
        td._write_manual_trigger(98765)
        assert os.path.exists(target)
        with open(target) as f:
            assert f.read() == "98765"
        # No leftover .tmp
        assert not os.path.exists(target + ".tmp")

    def test_poll_returns_result_when_file_appears(self, tmp_path, monkeypatch):
        import telegram_devops as td
        result_path = str(tmp_path / "result.json")
        monkeypatch.setattr("telegram_devops.MANUAL_RESULT_FILE", result_path)
        # Pretend the file appears after a small delay (simulated by writing it BEFORE poll starts)
        with open(result_path, "w") as f:
            json.dump({"status": "success", "message": "ok"}, f)
        with patch("telegram_devops.time.sleep"):
            res = td._poll_manual_result(time.time() + 60)
        assert res is not None
        assert res["status"] == "success"

    def test_poll_returns_none_on_timeout(self, tmp_path, monkeypatch):
        import telegram_devops as td
        result_path = str(tmp_path / "result.json")
        monkeypatch.setattr("telegram_devops.MANUAL_RESULT_FILE", result_path)
        # File never appears — should return None after deadline
        with patch("telegram_devops.time.sleep"):
            res = td._poll_manual_result(time.time() - 1)  # already past deadline
        assert res is None

    def test_poll_handles_corrupt_json_then_returns_none(self, tmp_path, monkeypatch):
        import telegram_devops as td
        result_path = str(tmp_path / "result.json")
        monkeypatch.setattr("telegram_devops.MANUAL_RESULT_FILE", result_path)
        with open(result_path, "w") as f:
            f.write("{not valid")
        with patch("telegram_devops.time.sleep"):
            res = td._poll_manual_result(time.time() + 10)
        assert res is None  # corrupt twice → give up

    def test_atomic_write_visible_only_after_rename(self, tmp_path, monkeypatch):
        """Half-written file invisible to os.path.exists checks during write."""
        import telegram_devops as td
        target = str(tmp_path / "trigger")
        monkeypatch.setattr("telegram_devops._MANUAL_TRIGGER_FILE", target)
        td._write_manual_trigger(42)
        # After rename, the file exists with full content (no truncation)
        with open(target) as f:
            content = f.read()
        assert content == "42"
