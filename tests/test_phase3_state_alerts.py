"""
Phase 3 — State-change alert template tests.

Tests the new alert message functions added to risk_monitor.py and
the enriched checkpoint alert with Phase 1 values.  All tests are
pure string-assertion tests — no Telegram, no DB, no yfinance.

We import the functions directly after patching out the external
module-level imports that would fail in the test environment.
"""

import sys
import types
import pytest

# ── Stub heavy dependencies before importing risk_monitor ────────────────────
for mod_name in ["telebot", "supabase", "dotenv"]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

# supabase needs create_client to be importable
sys.modules["supabase"].create_client = lambda *a, **k: None  # type: ignore

# dotenv needs load_dotenv
sys.modules["dotenv"].load_dotenv = lambda *a, **k: None  # type: ignore

# telebot needs TeleBot + types (InlineKeyboardMarkup/Button)
class _FakeBot:
    def __init__(self, *a, **k): pass

class _FakeMarkup:
    def __init__(self, *a, **k): self.buttons = []
    def add(self, *btns): self.buttons.extend(btns)

class _FakeButton:
    def __init__(self, text, callback_data=None, *a, **k):
        self.text = text
        self.callback_data = callback_data or ""

_telebot_mod = sys.modules["telebot"]
_telebot_mod.TeleBot = _FakeBot  # type: ignore
_fake_types = types.ModuleType("telebot.types")
_fake_types.InlineKeyboardMarkup = _FakeMarkup  # type: ignore
_fake_types.InlineKeyboardButton = _FakeButton  # type: ignore
_telebot_mod.types = _fake_types  # type: ignore

import risk_monitor as rm


# ── _runner_state_alert ───────────────────────────────────────────────────────

class TestRunnerStateAlert:
    def _call(self, open_r=5.5, protected_profit=500, giveback_usd=200,
              giveback_pct=28.5, current_stop=48.0, days_to_earnings=None):
        return rm._runner_state_alert(
            "MRVL", "VCP", open_r, protected_profit,
            giveback_usd, giveback_pct, current_stop, days_to_earnings
        )

    def test_contains_symbol(self):
        assert "MRVL" in self._call()

    def test_contains_runner_label(self):
        assert "Runner" in self._call()

    def test_contains_open_r(self):
        assert "5.5" in self._call()

    def test_contains_protected_profit(self):
        assert "500" in self._call()

    def test_contains_giveback_usd(self):
        assert "200" in self._call()

    def test_contains_giveback_pct(self):
        assert "28" in self._call()

    def test_contains_stop(self):
        assert "48" in self._call()

    def test_no_earnings_line_when_none(self):
        text = self._call(days_to_earnings=None)
        assert "דוחות" not in text

    def test_earnings_line_when_within_30_days(self):
        text = self._call(days_to_earnings=10)
        assert "דוחות" in text
        assert "10" in text

    def test_earnings_line_suppressed_beyond_30_days(self):
        text = self._call(days_to_earnings=35)
        assert "דוחות" not in text

    def test_forbidden_action_present(self):
        assert "לא" in self._call()

    def test_returns_string(self):
        assert isinstance(self._call(), str)


# ── _broken_state_alert ───────────────────────────────────────────────────────

class TestBrokenStateAlert:
    def _call(self, open_r=-0.9, reason="מחיר עבר את הסטופ"):
        return rm._broken_state_alert("CAT", "EP", open_r, reason)

    def test_contains_symbol(self):
        assert "CAT" in self._call()

    def test_contains_broken_label(self):
        assert "שבור" in self._call()

    def test_contains_reason(self):
        assert "מחיר עבר" in self._call()

    def test_contains_open_r(self):
        assert "-0.9" in self._call()

    def test_action_line_present(self):
        assert "פעולה" in self._call() or "תוכנית" in self._call()

    def test_returns_string(self):
        assert isinstance(self._call(), str)


# ── _dead_money_alert ─────────────────────────────────────────────────────────

class TestDeadMoneyAlert:
    def _call(self, age_days=12.0, open_r=0.3):
        return rm._dead_money_alert("PWR", "VCP", age_days, open_r)

    def test_contains_symbol(self):
        assert "PWR" in self._call()

    def test_contains_dead_money_label(self):
        assert "Dead Money" in self._call()

    def test_contains_age_days(self):
        assert "12" in self._call()

    def test_contains_open_r(self):
        assert "0.3" in self._call()

    def test_forbidden_action_present(self):
        assert "לא" in self._call()

    def test_returns_string(self):
        assert isinstance(self._call(), str)


# ── _breakeven_protocol_alert ─────────────────────────────────────────────────

class TestBreakevenProtocolAlert:
    def _call(self, open_r=3.2, capital_at_risk=85.0):
        return rm._breakeven_protocol_alert("WCC", 3.2, 85.0)

    def test_contains_symbol(self):
        assert "WCC" in self._call()

    def test_contains_breakeven_label(self):
        assert "Breakeven" in self._call()

    def test_contains_capital_at_risk(self):
        assert "85" in self._call()

    def test_contains_open_r(self):
        assert "3.2" in self._call()

    def test_forbidden_action_present(self):
        assert "לא" in self._call()

    def test_risk_first_mention(self):
        assert "Risk First" in self._call()

    def test_returns_string(self):
        assert isinstance(self._call(), str)


# ── _checkpoint_alert_text (enriched) ────────────────────────────────────────

class TestCheckpointAlertEnriched:
    def test_basic_without_phase1_values(self):
        text = rm._checkpoint_alert_text("MRVL", "VCP", 2.0, 2.3, is_algo=False)
        assert "2.3R" in text or "2.30" in text
        assert "MRVL" in text

    def test_enriched_with_protected_profit(self):
        text = rm._checkpoint_alert_text(
            "MRVL", "VCP", 2.0, 2.3, is_algo=False,
            protected_profit=450, giveback_usd=180, giveback_pct=30.0
        )
        assert "450" in text
        assert "180" in text
        assert "30" in text

    def test_algo_checkpoint_no_exit_instruction(self):
        text = rm._checkpoint_alert_text("PLTR", "ALGO", 2.0, 2.1, is_algo=True)
        assert "Sentinel אינה" in text or "פיקוח" in text
        # Crucially, should NOT say "למכור" or "יציאה ידנית" as a command
        assert "למכור" not in text

    def test_enriched_protected_profit_optional(self):
        # Without Phase 1 values, extra line should not appear
        text = rm._checkpoint_alert_text("X", "EP", 2.0, 2.0, is_algo=False)
        assert "רווח מוגן" not in text


# ── Integration: state-change detection logic ─────────────────────────────────
# These tests exercise the state-transition alert decision logic directly,
# without running the full risk_monitor main() loop.

class TestStateTransitionDecisions:
    """
    Verify that the correct alert function is selected for each transition.
    We test by calling the alert text functions and checking they return
    the right content — we cannot run main() in tests.
    """

    def test_runner_alert_fires_for_runner_state(self):
        # When new_state == RUNNER and mgt_mode != algo_observed, runner alert fires
        text = rm._runner_state_alert(
            "MRVL", "VCP", 5.2, 600.0, 200.0, 25.0, 49.0, 14
        )
        assert "Runner" in text
        assert "MRVL" in text

    def test_broken_alert_fires_for_broken_state(self):
        text = rm._broken_state_alert("AXGN", "EP", -1.1, "מחיר עבר את הסטופ")
        assert "שבור" in text
        assert "AXGN" in text

    def test_dead_money_alert_fires_for_dead_money(self):
        text = rm._dead_money_alert("RVMD", "VCP", 14.0, 0.2)
        assert "Dead Money" in text
        assert "RVMD" in text

    def test_breakeven_alert_fires_at_3r_with_capital_at_risk(self):
        text = rm._breakeven_protocol_alert("CAT", 3.4, 95.0)
        assert "Breakeven" in text
        assert "95" in text

    def test_no_algo_exit_instruction_in_any_alert(self):
        """Sentinel must never issue exit/stop commands to ALGO positions."""
        algo_checkpoint = rm._checkpoint_alert_text(
            "QQQ", "ALGO", 2.0, 2.2, is_algo=True
        )
        # Only oversight language allowed
        assert "למכור" not in algo_checkpoint
        assert "לצאת" not in algo_checkpoint
        assert "הכנס" not in algo_checkpoint


# ── _runner_decision_keyboard ─────────────────────────────────────────────────

class TestRunnerDecisionKeyboard:
    def _kb(self, sym="MRVL", cid="C123"):
        return rm._runner_decision_keyboard(sym, cid)

    def test_returns_markup(self):
        assert self._kb() is not None

    def test_has_three_buttons(self):
        assert len(self._kb().buttons) == 3

    def test_hold_callback_data(self):
        cb = [b.callback_data for b in self._kb().buttons]
        assert any("runner_decision|hold|MRVL|C123" in s for s in cb)

    def test_tighten_callback_data(self):
        cb = [b.callback_data for b in self._kb().buttons]
        assert any("runner_decision|tighten|MRVL|C123" in s for s in cb)

    def test_partial_callback_data(self):
        cb = [b.callback_data for b in self._kb().buttons]
        assert any("runner_decision|partial|MRVL|C123" in s for s in cb)

    def test_hold_button_text_hebrew(self):
        texts = [b.text for b in self._kb().buttons]
        assert any("להחזיק" in t for t in texts)

    def test_tighten_button_text_hebrew(self):
        texts = [b.text for b in self._kb().buttons]
        assert any("הדק" in t for t in texts)

    def test_partial_button_text_hebrew(self):
        texts = [b.text for b in self._kb().buttons]
        assert any("מימוש" in t for t in texts)

    def test_campaign_id_embedded_in_callback(self):
        kb = rm._runner_decision_keyboard("TSLA", "CAMP-999")
        cb = [b.callback_data for b in kb.buttons]
        assert all("CAMP-999" in s for s in cb)
