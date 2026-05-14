"""test_telegram_tasks.py — UI wiring for the 📋 סקירת משימות feature.

Verifies the data-prep helper (_build_task_input) and the manual-edit
text-input validation. The Telegram bot side is mocked — we don't run
real bot.send_message calls; we assert on what the module computes.
"""
import os
import sys
import types as py_types
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Stub external deps before importing telegram_tasks
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

import telegram_tasks as tt
import task_engine as te
import task_state as ts


# ── _build_task_input ──────────────────────────────────────────────────────────

class TestBuildTaskInput:
    def _trades_df(self, **overrides):
        """Build a single-trade DataFrame matching what supabase_repository returns."""
        row = {
            "trade_id": "T1", "symbol": "CAT", "campaign_id": "CAT_T1",
            "side": "BUY", "quantity": 10, "price": 870.0,
            "stop_loss": 840.0, "initial_stop": 840.0, "pnl_usd": 0,
            "trade_date": (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d"),
            "setup_type": "EP", "management_state": "full_position",
            "risk_pct_at_entry": 0.35, "nav_at_entry": 7500.0,
        }
        row.update(overrides)
        return pd.DataFrame([row])

    def test_handles_empty_df(self):
        out = tt._build_task_input(pd.DataFrame(), acc_size=10000.0)
        assert out == []

    def test_returns_dict_with_required_keys(self):
        df = self._trades_df()
        with patch("telegram_tasks.ec.get_live_price", return_value=900.0), \
             patch("telegram_tasks.ec.get_ma_levels", return_value={"ma21": 880.0}):
            out = tt._build_task_input(df, acc_size=8000.0)
        assert len(out) == 1
        p = out[0]
        assert p["campaign_id"] == "CAT_T1"
        assert p["symbol"] == "CAT"
        assert p["setup_type"] == "EP"
        assert p["current_price"] == 900.0
        assert p["entry_price"] == 870.0
        assert p["stop_loss"] == 840.0
        # 1R = 30, gain = 30 → open_r ≈ 1.0
        assert p["open_r"] == pytest.approx(1.0, rel=0.01)
        assert p["days_held"] == 10
        assert p["ma21"] == 880.0

    def test_missing_initial_stop_yields_zero_open_r(self):
        df = self._trades_df(initial_stop=0)
        with patch("telegram_tasks.ec.get_live_price", return_value=900.0), \
             patch("telegram_tasks.ec.get_ma_levels", return_value={}):
            out = tt._build_task_input(df, acc_size=8000.0)
        assert out[0]["open_r"] == 0

    def test_live_price_failure_falls_back_to_entry(self):
        df = self._trades_df()
        with patch("telegram_tasks.ec.get_live_price", return_value=None), \
             patch("telegram_tasks.ec.get_ma_levels", return_value={}):
            out = tt._build_task_input(df, acc_size=8000.0)
        assert out[0]["current_price"] == 870.0

    def test_ma_levels_exception_yields_none(self):
        df = self._trades_df()
        with patch("telegram_tasks.ec.get_live_price", return_value=900.0), \
             patch("telegram_tasks.ec.get_ma_levels",
                   side_effect=Exception("rate limited")):
            out = tt._build_task_input(df, acc_size=8000.0)
        assert out[0]["ma21"] is None

    def test_no_open_campaigns_yields_empty(self):
        """Campaign with net qty 0 (closed) → no row in get_open_positions_campaign."""
        df = pd.DataFrame([
            {"trade_id": "T1", "symbol": "OLD", "campaign_id": "OLD_T1",
             "side": "BUY", "quantity": 10, "price": 100.0,
             "stop_loss": 90.0, "initial_stop": 90.0, "pnl_usd": 0,
             "trade_date": "2026-01-01", "setup_type": "EP",
             "management_state": "full_position"},
            {"trade_id": "T2", "symbol": "OLD", "campaign_id": "OLD_T1",
             "side": "SELL", "quantity": -10, "price": 110.0,
             "stop_loss": 90.0, "initial_stop": 90.0, "pnl_usd": 100,
             "trade_date": "2026-01-15", "setup_type": "EP",
             "management_state": "full_position"},
        ])
        out = tt._build_task_input(df, acc_size=8000.0)
        assert out == []


# ── apply_manual_edit_value — text input validation ────────────────────────────

class TestManualEditValidation:
    def _setup_state(self, monkeypatch):
        """Patch in a fake user_state and stub out apply_confirmed_value."""
        user_state = {}
        chat_id = 12345
        user_state[chat_id] = {
            "action": "task_edit_value",
            "campaign_id": "CAT_T1",
            "kind": "break_even_2r",
            "symbol": "CAT",
        }
        return user_state, chat_id

    def test_valid_value_dispatches_apply(self, monkeypatch):
        user_state, chat_id = self._setup_state(monkeypatch)
        with patch("telegram_tasks.apply_confirmed_value") as mock_apply, \
             patch("telegram_tasks.bot") as mock_bot:
            handled = tt.apply_manual_edit_value(chat_id, "875.50", user_state)
        assert handled
        mock_apply.assert_called_once_with(chat_id, "CAT_T1", "break_even_2r", 875.5)
        # State cleared
        assert chat_id not in user_state

    def test_value_with_dollar_sign_stripped(self, monkeypatch):
        user_state, chat_id = self._setup_state(monkeypatch)
        with patch("telegram_tasks.apply_confirmed_value") as mock_apply, \
             patch("telegram_tasks.bot"):
            tt.apply_manual_edit_value(chat_id, "$875", user_state)
        mock_apply.assert_called_once_with(chat_id, "CAT_T1", "break_even_2r", 875.0)

    def test_value_with_comma_stripped(self, monkeypatch):
        user_state, chat_id = self._setup_state(monkeypatch)
        with patch("telegram_tasks.apply_confirmed_value") as mock_apply, \
             patch("telegram_tasks.bot"):
            tt.apply_manual_edit_value(chat_id, "1,250.00", user_state)
        mock_apply.assert_called_once_with(chat_id, "CAT_T1", "break_even_2r", 1250.0)

    def test_non_numeric_keeps_state(self, monkeypatch):
        user_state, chat_id = self._setup_state(monkeypatch)
        with patch("telegram_tasks.apply_confirmed_value") as mock_apply, \
             patch("telegram_tasks.bot") as mock_bot:
            handled = tt.apply_manual_edit_value(chat_id, "abc", user_state)
        assert handled  # consumed the message
        mock_apply.assert_not_called()
        # State remains so user can re-enter
        assert chat_id in user_state

    def test_zero_or_negative_rejected(self, monkeypatch):
        user_state, chat_id = self._setup_state(monkeypatch)
        with patch("telegram_tasks.apply_confirmed_value") as mock_apply, \
             patch("telegram_tasks.bot"):
            tt.apply_manual_edit_value(chat_id, "0", user_state)
            tt.apply_manual_edit_value(chat_id, "-100", user_state)
        mock_apply.assert_not_called()

    def test_no_active_state_returns_false(self):
        user_state = {}
        with patch("telegram_tasks.bot"):
            handled = tt.apply_manual_edit_value(99999, "100", user_state)
        assert handled is False


# ── _apply_approve — Supabase write + audit ────────────────────────────────────

class TestApplyApprove:
    def _make_task(self, action="update_stop", suggested=870.0):
        return te.Task(
            campaign_id="CAT_T1", symbol="CAT",
            kind=te.KIND_BREAK_EVEN_2R, urgency=60,
            title="t", detail="d",
            suggested_level=suggested,
            suggested_action=action,
        )

    def test_update_stop_writes_to_supabase(self, tmp_path, monkeypatch):
        monkeypatch.setattr("task_state.TASK_STATE_FILE",
                            str(tmp_path / "ts.json"))
        t = self._make_task()
        with patch("telegram_tasks.repo.update_stop_for_campaign") as mock_upd, \
             patch("telegram_tasks.audit_logger.log_action") as mock_audit, \
             patch("telegram_tasks.bot"):
            tt._apply_approve(12345, t, new_stop=870.0)
        mock_upd.assert_called_once_with(tt.supabase, "CAT_T1", 870.0)
        mock_audit.assert_called_once()

    def test_supabase_failure_aborts_audit_and_state(self, tmp_path, monkeypatch):
        state_path = str(tmp_path / "ts.json")
        monkeypatch.setattr("task_state.TASK_STATE_FILE", state_path)
        t = self._make_task()
        with patch("telegram_tasks.repo.update_stop_for_campaign",
                   side_effect=Exception("connection lost")), \
             patch("telegram_tasks.audit_logger.log_action") as mock_audit, \
             patch("telegram_tasks.bot") as mock_bot, \
             patch("telegram_tasks.ts.approve_task") as mock_approve:
            tt._apply_approve(12345, t, new_stop=870.0)
        # Audit must NOT be written if Supabase write failed
        mock_audit.assert_not_called()
        # And approve_task must NOT have been called
        mock_approve.assert_not_called()

    def test_exit_type_does_not_call_supabase(self, tmp_path, monkeypatch):
        monkeypatch.setattr("task_state.TASK_STATE_FILE",
                            str(tmp_path / "ts.json"))
        t = self._make_task(action="exit", suggested=None)
        with patch("telegram_tasks.repo.update_stop_for_campaign") as mock_upd, \
             patch("telegram_tasks.audit_logger.log_action") as mock_audit, \
             patch("telegram_tasks.bot"):
            tt._apply_approve(12345, t, new_stop=None)
        mock_upd.assert_not_called()
        # Still acked
        mock_audit.assert_called_once()


# ── Snooze / dismiss
class TestSnoozeDismiss:
    def test_snooze_short_persists_24h(self, tmp_path, monkeypatch):
        monkeypatch.setattr("task_state.TASK_STATE_FILE",
                            str(tmp_path / "ts.json"))
        with patch("telegram_tasks.bot"):
            tt.snooze_short(123, "CAT_T1", "break_even_2r")
        snoozes = ts.get_snoozes()
        assert "CAT_T1|break_even_2r" in snoozes

    def test_dismiss_persists_30d(self, tmp_path, monkeypatch):
        import time as _time
        monkeypatch.setattr("task_state.TASK_STATE_FILE",
                            str(tmp_path / "ts.json"))
        with patch("telegram_tasks.bot"):
            tt.dismiss_long(123, "CAT_T1", "break_even_2r")
        snoozes = ts.get_snoozes()
        # 30d ≈ 2.5M seconds, must be at least 25d in future
        assert snoozes["CAT_T1|break_even_2r"] > _time.time() + 25 * 24 * 3600
