"""
Tests for telegram_stop_promote.py — lightweight tap-only stop promotion.

Covers UX_TELEGRAM_AUDIT_DAY3 Pain 1 fix:
* keyboard built with one symbol-labelled button per discretionary position
* ALGO positions are NOT promotable (Sentinel does not manage ALGO stops)
* lightweight entry point does NOT call evaluate_position_engine
* picking a position hands off to the existing input_new_sl flow with the
  promote_batch flag set (write path unchanged)

Uses patch.object on the real module (same pattern as
test_telegram_portfolio.py / test_telegram_backlog.py) so it works even
when telegram_stop_promote was pre-imported via telegram_bot.
"""
import sys, os, types as py_types
from unittest.mock import MagicMock, patch
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Stub heavy deps if not yet loaded ─────────────────────────────────────────
for mod in ["telebot", "supabase", "dotenv", "engine_core", "adaptive_risk_engine",
            "telegram_formatters", "ibkr_sync_runner"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# telebot.types structure-exposing fakes. Multiple Telegram test modules
# (test_telegram_menus.py, this one) share the global sys.modules["telebot"].
# Whoever loads last must NOT clobber a structured fake the other relies on.
#
# Strategy: if a structured fake is already installed (has a real
# InlineKeyboardMarkup class, not an auto-MagicMock), reuse it. Otherwise
# install a FULLY structured set — including ReplyKeyboardMarkup/
# KeyboardButton — so test_telegram_menus.py keeps working even if this
# module loaded first. (The previous bug: ReplyKeyboardMarkup=MagicMock
# made menus.get_main_menu().buttons a MagicMock for sibling tests.)
_tb_mod = sys.modules["telebot"]


class _FIMarkup:
    def __init__(self, *a, **k): self.buttons = []
    def add(self, *btns): self.buttons.extend(btns)


class _FIButton:
    def __init__(self, text="", callback_data=None, *a, **k):
        self.text = text
        self.callback_data = callback_data or ""


_existing = getattr(_tb_mod, "types", None)
if _existing is None or not isinstance(
    getattr(_existing, "InlineKeyboardMarkup", None), type
):
    _tbt2 = py_types.ModuleType("telebot.types")
    _tbt2.InlineKeyboardMarkup = _FIMarkup
    _tbt2.InlineKeyboardButton = _FIButton
    _tbt2.ReplyKeyboardMarkup  = _FIMarkup   # structured (NOT MagicMock)
    _tbt2.KeyboardButton       = _FIButton   # structured (NOT MagicMock)
    _tbt2.ReplyKeyboardRemove  = _FIMarkup
    _tb_mod.types = _tbt2
    sys.modules["telebot.types"] = _tbt2

# bot_core is created with safe stub singletons ONLY when absent — matches
# the pattern in test_telegram_backlog.py / test_telegram_portfolio.py.
# bot_helpers / telegram_menus / supabase_repository are pure, network-free
# modules: let the REAL ones load (do not shadow them with partial stubs,
# which would break sibling test modules collected in the same session).
if "bot_core" not in sys.modules:
    _bc = py_types.ModuleType("bot_core")
    _bc.bot        = MagicMock()
    _bc.supabase   = MagicMock()
    _bc.user_state = {}
    _bc.RTL        = "‏"
    _bc.TOKEN      = ""
    _bc.ADMIN_ID   = ""
    sys.modules["bot_core"] = _bc

import telegram_stop_promote as sp  # noqa


# Structured telebot.types stand-in patched directly onto the module under
# test (sp.types). telegram_stop_promote does `from telebot import types`, so
# if it was first imported under a MagicMock telebot, sp.types would be a
# MagicMock with no real .buttons list. Patching sp.types per test makes
# every assertion independent of global sys.modules["telebot"] pollution
# caused by sibling Telegram test modules.
class _StubTypes:
    InlineKeyboardMarkup = _FIMarkup
    InlineKeyboardButton = _FIButton
    ReplyKeyboardMarkup  = _FIMarkup
    KeyboardButton       = _FIButton
    ReplyKeyboardRemove  = _FIMarkup


_fake_bot  = MagicMock()
_fake_sb   = MagicMock()
_repo_mock = MagicMock()
_ec_mock   = MagicMock()


def _setup_send_message():
    msg = MagicMock()
    msg.message_id = 7
    _fake_bot.send_message.return_value = msg


def _pos(**ov):
    base = {
        "symbol": "CAT", "price": 100.0, "quantity": 10, "stop_loss": 95.0,
        "initial_stop": 90.0, "base_price": 100.0, "base_qty": 10,
        "setup_type": "VCP", "campaign_id": "CAT_1",
    }
    base.update(ov)
    return base


# ── build_stop_promote_keyboard ────────────────────────────────────────────────

class TestBuildKeyboard:
    def _build(self, positions, live_price=120.0):
        _ec_mock.reset_mock()
        _ec_mock.get_live_price.return_value = live_price
        with patch.object(sp, 'types', _StubTypes), \
             patch.object(sp, 'ec', _ec_mock), \
             patch.object(sp, 'get_account_settings',
                          lambda: {"total_deposited": 10000.0, "risk_pct_input": 0.5}), \
             patch.object(sp, 'get_nav_and_risk', lambda s=None: (10000.0, 50.0, None)):
            return sp.build_stop_promote_keyboard(positions)

    def test_one_button_per_position_plus_close(self):
        kb = self._build([_pos(symbol="CAT"), _pos(symbol="MSFT", campaign_id="MSFT_1")])
        # 2 picks + 1 close
        assert len(kb.buttons) == 3
        assert any("CAT" in b.text for b in kb.buttons)
        assert any("MSFT" in b.text for b in kb.buttons)

    def test_button_label_has_open_r(self):
        # entry 100, curr 120, qty 10 → open pnl 200
        # original risk = (100-90)*10 = 100 → open_r = +2.00R
        kb = self._build([_pos()], live_price=120.0)
        pick = [b for b in kb.buttons if b.callback_data.startswith("promote_pick|")][0]
        assert "+2.00R" in pick.text
        assert "🎯" in pick.text
        assert "CAT" in pick.text

    def test_callback_data_is_index_based(self):
        kb = self._build([_pos(symbol="A", campaign_id="A_1"),
                          _pos(symbol="B", campaign_id="B_1")])
        picks = [b for b in kb.buttons if b.callback_data.startswith("promote_pick|")]
        assert {b.callback_data for b in picks} == {"promote_pick|0", "promote_pick|1"}

    def test_algo_position_not_promotable(self):
        kb = self._build([_pos(symbol="QQQ", setup_type="ALGO", campaign_id="QQQ_1")])
        algo_btns = [b for b in kb.buttons if "QQQ" in b.text]
        assert algo_btns
        # ALGO button must NOT be a promote_pick — it's a no-op info button
        assert algo_btns[0].callback_data == "promote_algo_noop"
        assert not any(b.callback_data.startswith("promote_pick|") for b in kb.buttons)

    def test_missing_initial_stop_shows_na(self):
        kb = self._build([_pos(initial_stop=0)], live_price=120.0)
        pick = [b for b in kb.buttons if b.callback_data.startswith("promote_pick|")][0]
        assert "N/A" in pick.text


# ── handle_stop_promote_entry — lightweight, no heavy engine ───────────────────

class TestEntry:
    def _run(self, positions_df):
        _fake_bot.reset_mock()
        _setup_send_message()
        _repo_mock.reset_mock()
        _ec_mock.reset_mock()
        _repo_mock.get_all_trades.return_value = [{"x": 1}]
        _ec_mock.get_open_positions_campaign.return_value = {
            "ok": True, "error": None, "data": positions_df
        }
        _ec_mock.get_live_price.return_value = 110.0
        state = {}
        with patch.object(sp, 'types', _StubTypes), \
             patch.object(sp, 'bot', _fake_bot), \
             patch.object(sp, 'supabase', _fake_sb), \
             patch.object(sp, 'user_state', state), \
             patch.object(sp, 'repo', _repo_mock), \
             patch.object(sp, 'ec', _ec_mock), \
             patch.object(sp, 'get_account_settings',
                          lambda: {"total_deposited": 10000.0, "risk_pct_input": 0.5}), \
             patch.object(sp, 'get_nav_and_risk', lambda s=None: (10000.0, 50.0, None)):
            sp.handle_stop_promote_entry(4001)
        return state

    def test_does_not_call_evaluate_position_engine(self):
        self._run(pd.DataFrame([_pos()]))
        assert not _ec_mock.evaluate_position_engine.called

    def test_stores_temp_positions(self):
        state = self._run(pd.DataFrame([_pos(symbol="CAT")]))
        assert 4001 in state
        assert "temp_positions" in state[4001]
        assert state[4001]["temp_positions"][0]["symbol"] == "CAT"

    def test_empty_positions_message(self):
        self._run(pd.DataFrame())
        last = _fake_bot.send_message.call_args_list[-1][0][1]
        assert "אין פוזיציות פתוחות" in last

    def test_sends_keyboard_with_buttons(self):
        self._run(pd.DataFrame([_pos()]))
        kwargs = _fake_bot.send_message.call_args_list[-1][1]
        kb = kwargs.get("reply_markup")
        assert kb is not None and len(kb.buttons) >= 2

    def test_all_algo_warns_no_promotable(self):
        self._run(pd.DataFrame([_pos(setup_type="ALGO")]))
        msgs = "\n".join(c[0][1] for c in _fake_bot.send_message.call_args_list)
        assert "ALGO" in msgs


# ── handle_stop_promote_pick — hands off to existing input_new_sl ─────────────

class TestPick:
    def _run(self, idx, positions, preset_state=None):
        _fake_bot.reset_mock()
        _setup_send_message()
        state = {4002: dict(preset_state or {})}
        if positions is not None:
            state[4002]["temp_positions"] = positions
        with patch.object(sp, 'types', _StubTypes), \
             patch.object(sp, 'bot', _fake_bot), \
             patch.object(sp, 'supabase', _fake_sb), \
             patch.object(sp, 'user_state', state), \
             patch.object(sp, 'repo', _repo_mock), \
             patch.object(sp, 'ec', _ec_mock), \
             patch.object(sp, 'get_account_settings',
                          lambda: {"total_deposited": 10000.0, "risk_pct_input": 0.5}), \
             patch.object(sp, 'get_nav_and_risk', lambda s=None: (10000.0, 50.0, None)):
            sp.handle_stop_promote_pick(4002, idx)
        return state

    def test_sets_input_new_sl_action_and_batch_flag(self):
        state = self._run(0, [_pos(symbol="CAT")])
        assert state[4002]["action"] == "input_new_sl"
        assert state[4002]["promote_batch"] is True
        assert state[4002]["selected_trade"]["symbol"] == "CAT"

    def test_prompts_for_new_stop_price(self):
        self._run(0, [_pos(symbol="CAT")])
        text = _fake_bot.send_message.call_args[0][1]
        assert "סטופ החדש" in text
        assert "CAT" in text

    def test_algo_pick_refused(self):
        state = self._run(0, [_pos(symbol="QQQ", setup_type="ALGO")])
        # must NOT set the write-handoff action for an ALGO campaign
        assert state[4002].get("action") != "input_new_sl"
        text = _fake_bot.send_message.call_args[0][1]
        assert "ALGO" in text or "מנוהל חיצונית" in text

    def test_out_of_range_idx_reopens_list(self):
        # idx 5 with 1 position → invalid → re-entry attempt
        _repo_mock.get_all_trades.return_value = []
        _ec_mock.get_open_positions_campaign.return_value = {
            "ok": True, "error": None, "data": pd.DataFrame()
        }
        state = self._run(5, [_pos()])
        assert state[4002].get("action") != "input_new_sl"

    def test_missing_temp_positions_reopens_entry(self):
        _repo_mock.get_all_trades.return_value = []
        _ec_mock.get_open_positions_campaign.return_value = {
            "ok": True, "error": None, "data": pd.DataFrame()
        }
        state = self._run(0, None)
        # No crash; falls back to entry which finds no positions
        assert state[4002].get("action") != "input_new_sl"
