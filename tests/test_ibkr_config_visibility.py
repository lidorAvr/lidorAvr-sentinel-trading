"""test_ibkr_config_visibility.py — Verify IBKR config is observable.

Regression cover for the 2026-05-14 incident where IBKR_QUERY_ID was missing
from the Pi's .env, the code silently fell back to a hardcoded default that
queried someone else's account, and there was no way to see this from the
Telegram bot without SSH.

Covers:
  1. run_ibkr_sync logs Query ID + last-4 of token at every sync start.
  2. When IBKR_QUERY_ID env is missing, the log line marks query_id as DEFAULT.
  3. bot_health check #11 surfaces actual Query ID when set, RED when missing.
  4. bot_health check #15 (NEW) — Flex Period detection from last XML.
"""
import json
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch
import types as py_types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Stub heavy deps before any imports
for _mod in ("telebot", "telebot.types", "supabase", "dotenv"):
    sys.modules.setdefault(_mod, MagicMock())
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

if "bot_core" not in sys.modules:
    _bc = py_types.ModuleType("bot_core")
    _bc.bot = MagicMock(); _bc.supabase = MagicMock()
    _bc.user_state = {}; _bc.RTL = "‏"
    _bc.TOKEN = ""; _bc.ADMIN_ID = ""
    sys.modules["bot_core"] = _bc

import ibkr_sync_runner as runner
import bot_health as bh


# ── Helpers ──────────────────────────────────────────────────────────────────

_IBKR_FETCH_URL = ("https://gdcdyn.interactivebrokers.com/Universal/servlet/"
                   "FlexStatementService.GetStatement")


def _send_ok_xml(ref="REF1"):
    return (f"<FlexStatementResponse><Status>Success</Status>"
            f"<ReferenceCode>{ref}</ReferenceCode>"
            f"<Url>{_IBKR_FETCH_URL}</Url></FlexStatementResponse>")


def _send_err_xml(code=1001):
    return f"<FlexStatementResponse><Status>Fail</Status><ErrorCode>{code}</ErrorCode></FlexStatementResponse>"


def _statement_xml(nav=10000.0, from_d="20260414", to_d="20260514"):
    return (f"<FlexQueryResponse><FlexStatements>"
            f"<FlexStatement fromDate='{from_d}' toDate='{to_d}'>"
            f"<ChangeInNAV endingValue='{nav}' /><Trades></Trades>"
            f"</FlexStatement></FlexStatements></FlexQueryResponse>")


def _mock_resp(text):
    r = MagicMock(); r.text = text
    return r


# ════════════════════════════════════════════════════════════════════════════════
# Sync-start config log line
# ════════════════════════════════════════════════════════════════════════════════

class TestSyncStartConfigLog:
    def _capture_run(self, tmp_path, env_overrides):
        captured = []
        with (patch.dict(os.environ, env_overrides, clear=False),
              patch("ibkr_sync_runner._SENDREQ_STATE_FILE", str(tmp_path / "sr.json")),
              patch("ibkr_sync_runner._REPORTS_DIR", str(tmp_path)),
              patch("ibkr_sync_runner._CONFIG_PATH", str(tmp_path / "cfg.json")),
              patch("ibkr_sync_runner.requests.get") as mock_get,
              patch("ibkr_sync_runner.time.sleep")):
            mock_get.side_effect = [_mock_resp(_send_ok_xml()), _mock_resp(_statement_xml())]
            runner.run_ibkr_sync(log_fn=captured.append)
        return captured

    def test_logs_query_id_on_start(self, tmp_path, monkeypatch):
        monkeypatch.delenv("IBKR_QUERY_ID", raising=False)
        captured = self._capture_run(
            tmp_path,
            {"IBKR_TOKEN": "exampletokenABCD1234Bxc",
             "IBKR_QUERY_ID": "1446152"},
        )
        config_lines = [l for l in captured if "config:" in l]
        assert len(config_lines) == 1
        assert "query_id=1446152" in config_lines[0]

    def test_logs_token_last_four_redacted(self, tmp_path, monkeypatch):
        monkeypatch.delenv("IBKR_QUERY_ID", raising=False)
        captured = self._capture_run(
            tmp_path,
            {"IBKR_TOKEN": "exampletokenABCD1234Bxc",
             "IBKR_QUERY_ID": "1446152"},
        )
        config_lines = [l for l in captured if "config:" in l]
        assert "token=...4Bxc" in config_lines[0]
        # Token body must not be exposed in the log
        assert "exampletokenABCD1234" not in config_lines[0]

    def test_marks_default_query_id_loudly(self, tmp_path, monkeypatch):
        """When IBKR_QUERY_ID is absent, the log line must contain DEFAULT
        so a passing grep flags the silent misconfiguration."""
        monkeypatch.delenv("IBKR_QUERY_ID", raising=False)
        captured = self._capture_run(
            tmp_path,
            {"IBKR_TOKEN": "exampletokenABCD1234Bxc"},
        )
        config_lines = [l for l in captured if "config:" in l]
        assert len(config_lines) == 1
        assert "DEFAULT" in config_lines[0]
        assert "1501352" in config_lines[0]  # the hardcoded fallback

    def test_marks_missing_token_explicitly(self, tmp_path, monkeypatch):
        """Missing IBKR_TOKEN must be visible in the log line."""
        monkeypatch.delenv("IBKR_TOKEN", raising=False)
        monkeypatch.delenv("IBKR_QUERY_ID", raising=False)
        captured = []
        with (patch("ibkr_sync_runner._SENDREQ_STATE_FILE", str(tmp_path / "sr.json")),
              patch("ibkr_sync_runner.requests.get",
                    return_value=_mock_resp(_send_err_xml(1015))),
              patch("ibkr_sync_runner.time.sleep")):
            runner.run_ibkr_sync(log_fn=captured.append)
        config_lines = [l for l in captured if "config:" in l]
        assert config_lines and "(missing!)" in config_lines[0]


# ════════════════════════════════════════════════════════════════════════════════
# bot_health check #11 — IBKR Query ID
# ════════════════════════════════════════════════════════════════════════════════

def _make_supabase(trades=None):
    sb = MagicMock()
    trades = trades or [{"trade_date": "2026-05-14"}]
    def _table(name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.order.return_value  = chain
        chain.limit.return_value  = chain
        chain.execute.return_value = MagicMock(data=trades)
        return chain
    sb.table.side_effect = _table
    return sb


def _run_health(env=None, monkeypatch=None, supabase_mock=None):
    supabase_mock = supabase_mock or _make_supabase()
    ec_mock = MagicMock()
    ec_mock.get_nav_with_freshness.return_value = {
        "ok": True, "is_critical": False, "is_stale": False,
        "freshness_label": "NAV fresh", "nav": 10000.0,
    }
    cfg = {"total_deposited": 10000.0, "risk_pct_input": 0.5}
    env_overrides = env or {}
    if monkeypatch is not None:
        for k in ("IBKR_QUERY_ID", "IBKR_TOKEN", "TELEGRAM_ADMIN_ID"):
            if k not in env_overrides:
                monkeypatch.delenv(k, raising=False)
    with patch.object(bh, 'supabase', supabase_mock), \
         patch.object(bh, 'ec', ec_mock), \
         patch.object(bh, 'get_account_settings', lambda: cfg), \
         patch.dict(os.environ, env_overrides, clear=False):
        return bh.build_health_report()


class TestBotHealthQueryIdCheck:
    def test_query_id_set_shows_value(self, monkeypatch):
        report = _run_health(
            env={"IBKR_QUERY_ID": "1446152", "IBKR_TOKEN": "t",
                 "TELEGRAM_ADMIN_ID": "1"},
            monkeypatch=monkeypatch,
        )
        assert "IBKR Query ID — 1446152" in report
        # Must NOT report the missing-config flag
        assert "IBKR_QUERY_ID חסר" not in report

    def test_query_id_missing_is_red(self, monkeypatch):
        report = _run_health(
            env={"IBKR_TOKEN": "t", "TELEGRAM_ADMIN_ID": "1"},
            monkeypatch=monkeypatch,
        )
        # New behavior: RED, not just warn — silent default is dangerous
        assert "🔴" in report
        assert "IBKR_QUERY_ID חסר" in report
        # Mentions "default" to explain
        assert "default" in report.lower() or "DEFAULT" in report


# ════════════════════════════════════════════════════════════════════════════════
# bot_health check #15 — Flex Period detection from last XML
# ════════════════════════════════════════════════════════════════════════════════

class TestBotHealthFlexPeriodCheck:
    def _make_report(self, tmp_path, from_d, to_d):
        rdir = tmp_path / "reports"
        rdir.mkdir()
        xml = (f"<FlexQueryResponse><FlexStatements>"
               f"<FlexStatement fromDate='{from_d}' toDate='{to_d}'>"
               f"<ChangeInNAV endingValue='10000' /><Trades></Trades>"
               f"</FlexStatement></FlexStatements></FlexQueryResponse>")
        path = rdir / "ibkr_20260514_test.xml"
        path.write_text(xml)
        return str(path)

    def test_wide_period_is_green(self, tmp_path, monkeypatch):
        self._make_report(tmp_path, "20260414", "20260514")  # 30 days
        with patch("bot_health.glob.glob",
                   return_value=[str(p) for p in (tmp_path / "reports").glob("*.xml")]):
            report = _run_health(
                env={"IBKR_QUERY_ID": "1446152", "IBKR_TOKEN": "t",
                     "TELEGRAM_ADMIN_ID": "1"},
                monkeypatch=monkeypatch,
            )
        assert "Flex Period — 30 ימים" in report
        # Must be ✅ not ⚠️ or 🔴
        period_line = [l for l in report.split("\n") if "Flex Period" in l][0]
        assert period_line.lstrip("‏").startswith("✅")

    def test_narrow_period_is_red(self, tmp_path, monkeypatch):
        self._make_report(tmp_path, "20260513", "20260514")  # 1 day
        with patch("bot_health.glob.glob",
                   return_value=[str(p) for p in (tmp_path / "reports").glob("*.xml")]):
            report = _run_health(
                env={"IBKR_QUERY_ID": "1446152", "IBKR_TOKEN": "t",
                     "TELEGRAM_ADMIN_ID": "1"},
                monkeypatch=monkeypatch,
            )
        period_line = [l for l in report.split("\n") if "Flex Period" in l][0]
        assert period_line.lstrip("‏").startswith("🔴")
        assert "Last 30 Calendar Days" in period_line

    def test_medium_period_is_yellow(self, tmp_path, monkeypatch):
        self._make_report(tmp_path, "20260507", "20260514")  # 7 days (< 14)
        with patch("bot_health.glob.glob",
                   return_value=[str(p) for p in (tmp_path / "reports").glob("*.xml")]):
            report = _run_health(
                env={"IBKR_QUERY_ID": "1446152", "IBKR_TOKEN": "t",
                     "TELEGRAM_ADMIN_ID": "1"},
                monkeypatch=monkeypatch,
            )
        period_line = [l for l in report.split("\n") if "Flex Period" in l][0]
        assert period_line.lstrip("‏").startswith("⚠️")
        assert "7 ימים" in period_line

    def test_no_reports_warns(self, tmp_path, monkeypatch):
        with patch("bot_health.glob.glob", return_value=[]):
            report = _run_health(
                env={"IBKR_QUERY_ID": "1446152", "IBKR_TOKEN": "t",
                     "TELEGRAM_ADMIN_ID": "1"},
                monkeypatch=monkeypatch,
            )
        assert "Flex Period — אין דוחות" in report

    def test_malformed_xml_warns_does_not_crash(self, tmp_path, monkeypatch):
        rdir = tmp_path / "reports"
        rdir.mkdir()
        (rdir / "broken.xml").write_text("<not</valid>")
        with patch("bot_health.glob.glob",
                   return_value=[str(p) for p in (tmp_path / "reports").glob("*.xml")]):
            report = _run_health(
                env={"IBKR_QUERY_ID": "1446152", "IBKR_TOKEN": "t",
                     "TELEGRAM_ADMIN_ID": "1"},
                monkeypatch=monkeypatch,
            )
        # Should produce a warn line but not crash the whole report
        assert "Flex Period" in report
        # Total report must still have the summary
        assert "Sentinel System Health" in report


# ════════════════════════════════════════════════════════════════════════════════
# Spec regression: the hardcoded default Query ID must remain 1501352 until
# explicitly changed (with documentation update). Pinning this prevents a
# silent change to the fallback that would query a different account.
# ════════════════════════════════════════════════════════════════════════════════

class TestHardcodedDefaultPinned:
    def test_default_query_id_value(self):
        """If you change this default, also update docs/IBKR_CONFIG_REFERENCE.md."""
        # Re-import the function so we look at the freshly-loaded module text.
        import inspect
        src = inspect.getsource(runner.run_ibkr_sync)
        assert 'os.getenv("IBKR_QUERY_ID", "1501352")' in src, (
            "The hardcoded default Query ID changed. This is a documented spec "
            "value (docs/IBKR_CONFIG_REFERENCE.md). Update the doc AND the "
            "test if intentional."
        )

    def test_default_url_endpoint(self):
        """SendRequest URL is part of the IBKR contract; pin it."""
        import inspect
        src = inspect.getsource(runner.run_ibkr_sync)
        assert "interactivebrokers.com/Universal/servlet" in src
        assert "FlexStatementService.SendRequest" in src
