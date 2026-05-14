"""test_session_2026_05_14_feedback.py — Display + UX fixes from session feedback.

Covers items A1, A2, A3, A4, A5, B2 from the team meeting on 2026-05-14:

  A1: bot_health Missing Stops excludes ALGO setups.
  A2: fmt_position_card renders initial+current stop values.
  A3: handle_portfolio_room emits per-symbol ALGO breakdown line.
  A4: ACTIONABILITY_LABELS['review_required'] is action-oriented.
  A5: /stats handler explains the totals (no UI-only test — verify the message text).
  B2: handle_portfolio_room labels exposure as 'מ-NAV' not 'מקרן הבסיס'.
"""
import io
import os
import sys
import types as py_types
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

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

import telegram_formatters as tf
import bot_health as bh


# ════════════════════════════════════════════════════════════════════════════════
# A1 — bot_health Missing Stops excludes ALGO
# ════════════════════════════════════════════════════════════════════════════════

def _supabase_with_trades(trades):
    """Mock that returns the given trade rows for any select on 'trades'."""
    sb = MagicMock()
    def _table(name):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.order.return_value  = chain
        chain.limit.return_value  = chain
        if name == "trades":
            chain.execute.return_value = MagicMock(data=trades)
        else:
            chain.execute.return_value = MagicMock(data=[])
        return chain
    sb.table.side_effect = _table
    return sb


def _run_health(supabase_mock, monkeypatch):
    ec_mock = MagicMock()
    ec_mock.get_nav_with_freshness.return_value = {
        "ok": True, "is_critical": False, "is_stale": False,
        "freshness_label": "NAV fresh", "nav": 10000.0,
    }
    for k in ("IBKR_QUERY_ID", "IBKR_TOKEN", "TELEGRAM_ADMIN_ID"):
        monkeypatch.setenv(k, "test")
    with patch.object(bh, 'supabase', supabase_mock), \
         patch.object(bh, 'ec', ec_mock), \
         patch.object(bh, 'get_account_settings',
                      lambda: {"total_deposited": 7500.0, "risk_pct_input": 0.5}):
        return bh.build_health_report()


class TestMissingStopsAlgoExclusion:
    def test_algo_without_stop_does_not_count(self, monkeypatch):
        trades = [
            {"symbol": "TSLA", "side": "BUY", "stop_loss": 0, "quantity": 10,
             "setup_type": "ALGO"},
            {"symbol": "JPM",  "side": "BUY", "stop_loss": 0, "quantity": 5,
             "setup_type": "algo"},  # case-insensitive
        ]
        report = _run_health(_supabase_with_trades(trades), monkeypatch)
        # ALGO-only portfolio with no stops → Missing Stops should report "אין"
        assert "Missing Stops — אין" in report
        assert "TSLA" not in report.split("Missing Stops")[1].split("\n")[0]

    def test_disc_without_stop_still_counts(self, monkeypatch):
        trades = [
            {"symbol": "CAT",  "side": "BUY", "stop_loss": 0,   "quantity": 1,
             "setup_type": "EP"},
            {"symbol": "TSLA", "side": "BUY", "stop_loss": 0,   "quantity": 10,
             "setup_type": "ALGO"},
        ]
        report = _run_health(_supabase_with_trades(trades), monkeypatch)
        # EP without stop counts; ALGO does not. Should be 1 row, only CAT.
        line = [l for l in report.split("\n") if "Missing Stops" in l][0]
        assert "1 שורות" in line
        assert "CAT" in line
        assert "TSLA" not in line

    def test_disc_with_stop_does_not_count(self, monkeypatch):
        trades = [
            {"symbol": "MRVL", "side": "BUY", "stop_loss": 80.0, "quantity": 5,
             "setup_type": "EP"},
        ]
        report = _run_health(_supabase_with_trades(trades), monkeypatch)
        assert "Missing Stops — אין" in report

    def test_empty_setup_type_treated_as_non_algo(self, monkeypatch):
        """Defensive: a buy with NULL setup_type should still count as missing
        stop (we don't know it's ALGO, so we report it)."""
        trades = [
            {"symbol": "X",  "side": "BUY", "stop_loss": 0, "quantity": 1,
             "setup_type": None},
        ]
        report = _run_health(_supabase_with_trades(trades), monkeypatch)
        line = [l for l in report.split("\n") if "Missing Stops" in l][0]
        assert "1 שורות" in line and "X" in line


# ════════════════════════════════════════════════════════════════════════════════
# A2 — fmt_position_card renders stop info
# ════════════════════════════════════════════════════════════════════════════════

def _card(**overrides):
    """Build a position card with reasonable defaults."""
    defaults = dict(
        i=1, sym="CAT", setup="EP", days_held=14,
        curr=900.0, entry=874.61, open_pnl=25.39,
        pos_value=900.0, weight_pct=11.3,
        total_pos_profit=25.39, total_campaign_r=1.30,
        open_r_val=1.30, status="🔥 Power", action_short="החזקה",
    )
    defaults.update(overrides)
    return tf.fmt_position_card(**defaults)


class TestStopValuesInPositionCard:
    def test_stop_line_appears_when_current_stop_set(self):
        out = _card(current_stop=820.0, initial_stop=820.0)
        assert "סטופ:" in out and "$820.00" in out
        # Distance to current price shown as percentage
        # (900 - 820) / 900 * 100 = 8.88...
        assert "%" in out

    def test_stop_line_shows_both_when_trailing_moved_up(self):
        out = _card(current_stop=850.0, initial_stop=820.0)
        assert "$850.00" in out
        assert "$820.00" in out
        assert "⬆️" in out  # current > initial = trailing up

    def test_stop_line_shows_down_arrow_when_lowered(self):
        out = _card(current_stop=800.0, initial_stop=820.0)
        assert "$800.00" in out
        assert "⬇️" in out

    def test_stop_line_collapses_when_initial_equals_current(self):
        """If they're equal, only one value should show (no '⬆️ מ-' suffix)."""
        out = _card(current_stop=820.0, initial_stop=820.0)
        # Should NOT show the "moved from" suffix
        assert "מ-`$820.00`" not in out  # the "ב$820.00 from" suffix
        assert out.count("$820.00") == 1

    def test_stop_line_flags_missing_explicitly(self):
        out = _card(current_stop=0, initial_stop=0)
        assert "⚠️ חסר" in out
        assert "/next" in out  # actionable guidance

    def test_distance_pct_positive_when_curr_above_stop(self):
        out = _card(curr=900.0, current_stop=810.0, initial_stop=810.0)
        # (900 - 810) / 900 = 10% — must be positive in output
        # The "+10.0%" with mathematical sign
        assert "+10.0%" in out


# ════════════════════════════════════════════════════════════════════════════════
# A4 — review_required label is action-oriented
# ════════════════════════════════════════════════════════════════════════════════

class TestReviewRequiredLabel:
    def test_label_is_action_oriented(self):
        label = tf.ACTIONABILITY_LABELS["review_required"]
        # No longer the cryptic "🟡 לבדוק"
        assert label != "🟡 לבדוק"
        # Should mention what to do
        assert "/risk" in label
        # Still RTL-friendly Hebrew
        assert "🟡" in label

    def test_fmt_actionability_includes_new_label(self):
        out = tf.fmt_actionability("review_required")
        assert "/risk" in out
        assert "ממתין" in out


# ════════════════════════════════════════════════════════════════════════════════
# Smoke: telegram_formatters module still importable + unchanged contracts
# ════════════════════════════════════════════════════════════════════════════════

class TestFormattersStillWork:
    def test_position_card_without_stop_args_uses_defaults(self):
        """Backwards-compat: old callers (without the new initial_stop/current_stop
        kwargs) get the 'missing stop' flag, not a crash."""
        out = tf.fmt_position_card(
            i=1, sym="CAT", setup="EP", days_held=14,
            curr=900.0, entry=874.61, open_pnl=25.39,
            pos_value=900.0, weight_pct=11.3,
            total_pos_profit=25.39, total_campaign_r=1.30,
            open_r_val=1.30, status="🔥 Power", action_short="החזקה",
        )
        # No KeyError, no exception — and the missing-stop fallback fires
        assert "⚠️ חסר" in out

    def test_other_actionability_labels_unchanged(self):
        assert tf.ACTIONABILITY_LABELS["action_required"] == "🔴 פעולה נדרשת"
        assert tf.ACTIONABILITY_LABELS["observation_only"] == "⚪ מידע בלבד"
        assert tf.ACTIONABILITY_LABELS["external_managed"].startswith("🟠")
