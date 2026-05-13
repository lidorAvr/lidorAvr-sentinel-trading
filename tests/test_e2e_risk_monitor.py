"""
tests/test_e2e_risk_monitor.py — integration tests for risk_monitor alert pipeline.

Tests the cross-module chain:
    engine_core (trail stop / state) → risk_monitor (alert formatting) → send_telegram

Uses module-level stubs (same pattern as test_healthcheck.py) so no real Telegram
or Supabase connection is required.
"""
import os
import sys
import types
import pytest

# ── Stub heavy deps before any project import ─────────────────────────────────
for _mod in ("telebot", "supabase", "dotenv"):
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

sys.modules["supabase"].create_client = lambda *a, **k: None   # type: ignore
sys.modules["dotenv"].load_dotenv     = lambda *a, **k: None   # type: ignore

class _FakeBot:
    def __init__(self, *a, **k): pass
    class types:
        class InlineKeyboardMarkup:
            def __init__(self, **k): self.buttons = []
            def add(self, *b): self.buttons.extend(b)
        class InlineKeyboardButton:
            def __init__(self, text="", callback_data=""): pass

sys.modules["telebot"].TeleBot = _FakeBot          # type: ignore
sys.modules["telebot"].types   = _FakeBot.types    # type: ignore

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import risk_monitor as rm
import engine_core as ec


# ── Helper ────────────────────────────────────────────────────────────────────

def _capture_send(monkeypatch):
    """Patch send_telegram and return the captured list."""
    sent = []
    monkeypatch.setattr(rm, "send_telegram", lambda msg: sent.append(msg))
    monkeypatch.setattr(rm, "send_telegram_with_keyboard", lambda msg, kb: sent.append(msg))
    return sent


# ── Runner alert + trailing stop integration ──────────────────────────────────

@pytest.mark.integration
class TestRunnerAlertWithTrailingStop:
    """Cross-module: compute_suggested_trail_stop → _runner_state_alert."""

    def test_long_8r_ma21_trail_appears_in_alert(self):
        trail = ec.compute_suggested_trail_stop(
            side="LONG", current_price=200.0,
            ma21=180.0, ma50=160.0,
            open_r=8.5, entry_price=100.0,
        )
        alert = rm._runner_state_alert(
            sym="NVDA", setup="SEPA", open_r=8.5,
            protected_profit=8000.0, giveback_usd=1600.0, giveback_pct=20.0,
            current_stop=176.4, days_to_earnings=None,
            trail_stop=trail,
        )
        assert "Trailing Stop" in alert
        assert "MA21" in alert
        assert "176.40" in alert      # current_stop shown
        assert "Runner" in alert
        assert "8.5" in alert         # open_r echoed

    def test_long_5r_ma50_trail_appears_in_alert(self):
        trail = ec.compute_suggested_trail_stop(
            side="LONG", current_price=150.0,
            ma21=None, ma50=130.0,
            open_r=5.5, entry_price=100.0,
        )
        alert = rm._runner_state_alert(
            sym="AAPL", setup="SEPA", open_r=5.5,
            protected_profit=3000.0, giveback_usd=1500.0, giveback_pct=50.0,
            current_stop=127.4, days_to_earnings=None,
            trail_stop=trail,
        )
        assert "MA50" in alert
        assert "Trailing Stop" in alert

    def test_no_trail_data_omits_trail_line(self):
        trail = {"suggested_stop": None, "basis": "none", "note": "לא ניתן"}
        alert = rm._runner_state_alert(
            sym="TEST", setup="SEPA", open_r=3.0,
            protected_profit=500.0, giveback_usd=200.0, giveback_pct=40.0,
            current_stop=100.0, days_to_earnings=None,
            trail_stop=trail,
        )
        assert "Trailing Stop" not in alert   # basis=none suppresses the line

    def test_earnings_warning_appears_when_within_30_days(self):
        trail = ec.compute_suggested_trail_stop(
            side="LONG", current_price=200.0,
            ma21=180.0, ma50=160.0,
            open_r=6.0, entry_price=100.0,
        )
        alert = rm._runner_state_alert(
            sym="MSFT", setup="SEPA", open_r=6.0,
            protected_profit=5000.0, giveback_usd=1000.0, giveback_pct=20.0,
            current_stop=175.0, days_to_earnings=15,
            trail_stop=trail,
        )
        assert "דוחות" in alert
        assert "15" in alert

    def test_short_side_8r_ma21_above_price(self):
        trail = ec.compute_suggested_trail_stop(
            side="SHORT", current_price=80.0,
            ma21=100.0, ma50=110.0,
            open_r=9.0, entry_price=120.0,
        )
        assert trail["basis"] == "MA21"
        assert trail["suggested_stop"] > 80.0    # stop above price for SHORT


# ── Alert content integrity ───────────────────────────────────────────────────

@pytest.mark.integration
class TestAlertContentIntegrity:
    """Verify alert functions produce RTL-safe Hebrew output."""

    def test_broken_alert_contains_symbol(self):
        alert = rm._broken_state_alert("TSLA", "SEPA", -2.5, "חצה סטופ")
        assert "TSLA" in alert
        assert "2.5" in alert

    def test_dead_money_alert_contains_age(self):
        alert = rm._dead_money_alert("QQQ", "ALGO", 45.0, 0.3)
        assert "45" in alert
        assert "QQQ" in alert

    def test_runner_alert_symbol_is_required(self):
        trail = ec.compute_suggested_trail_stop(
            side="LONG", current_price=100.0,
            ma21=None, ma50=None,
            open_r=4.0, entry_price=90.0,
        )
        alert = rm._runner_state_alert(
            sym="MRVL", setup="SEPA", open_r=4.0,
            protected_profit=1000.0, giveback_usd=400.0, giveback_pct=40.0,
            current_stop=90.0, days_to_earnings=None,
            trail_stop=trail,
        )
        assert "MRVL" in alert


# ── send_telegram path via monkeypatch ────────────────────────────────────────

@pytest.mark.integration
class TestSendTelegramPath:
    """Verify send_telegram is called with the right content."""

    def test_runner_alert_reaches_send_telegram(self, monkeypatch):
        sent = _capture_send(monkeypatch)
        trail = ec.compute_suggested_trail_stop(
            side="LONG", current_price=200.0,
            ma21=180.0, ma50=None,
            open_r=8.0, entry_price=100.0,
        )
        msg = rm._runner_state_alert(
            sym="NVDA", setup="SEPA", open_r=8.0,
            protected_profit=8000.0, giveback_usd=1600.0, giveback_pct=20.0,
            current_stop=176.4, days_to_earnings=None,
            trail_stop=trail,
        )
        rm.send_telegram(msg)
        assert len(sent) == 1
        assert "NVDA" in sent[0]
        assert "MA21" in sent[0]
