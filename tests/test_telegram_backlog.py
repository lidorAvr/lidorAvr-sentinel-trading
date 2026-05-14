"""
Tests for telegram_backlog.py — get_next_missing() journal flow.

Uses patch.object to patch module-level names in telegram_backlog directly
(sys.modules replacement would arrive too late if telegram_backlog was already
imported by test_developer_menu.py via telegram_bot).
"""
import sys, os, types as py_types
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Stub telebot / supabase / dotenv if not yet loaded ────────────────────────
for mod in ["telebot", "supabase", "dotenv", "engine_core", "adaptive_risk_engine",
            "telegram_formatters", "ibkr_sync_runner"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

if "telebot" in sys.modules:
    _tb_mod = sys.modules["telebot"]
    # Ensure telebot.types has the needed fake classes (add only if missing)
    _tbt = getattr(_tb_mod, "types", None)
    if _tbt is None or not hasattr(_tbt, "InlineKeyboardMarkup"):
        import types as _py_types

        class _FIMarkup:
            def __init__(self, *a, **k): self.buttons = []
            def add(self, *btns): self.buttons.extend(btns)

        class _FIButton:
            def __init__(self, text="", callback_data="", **k):
                self.text = text
                self.callback_data = callback_data

        _tbt2 = _py_types.ModuleType("telebot.types")
        _tbt2.InlineKeyboardMarkup = _FIMarkup
        _tbt2.InlineKeyboardButton = _FIButton
        _tbt2.ReplyKeyboardMarkup  = MagicMock
        _tbt2.KeyboardButton       = MagicMock
        _tbt2.ReplyKeyboardRemove  = MagicMock
        _tb_mod.types = _tbt2
        sys.modules["telebot.types"] = _tbt2

# ── Stub bot_core if not yet loaded ───────────────────────────────────────────
if "bot_core" not in sys.modules:
    _bc = py_types.ModuleType("bot_core")
    _bc.bot        = MagicMock()
    _bc.supabase   = MagicMock()
    _bc.user_state = {}
    _bc.RTL        = "‏"
    _bc.TOKEN      = ""
    _bc.ADMIN_ID   = ""
    sys.modules["bot_core"] = _bc

# ── Stub supabase_repository if not yet loaded ────────────────────────────────
if "supabase_repository" not in sys.modules:
    sys.modules["supabase_repository"] = MagicMock()

import telegram_backlog as tb  # noqa

# Module-level fakes — used with patch.object so that they work even when
# telegram_backlog was pre-imported (e.g. by test_developer_menu.py).
_fake_bot    = MagicMock()
_fake_sb     = MagicMock()
_user_state  = {}

_repo_mock = MagicMock()
_repo_mock.get_incomplete_trades.return_value = []
_repo_mock.get_earlier_buys_for_campaign.return_value = []

_ec_mock = MagicMock()
_ec_mock.get_minervini_analysis.return_value = {"ok": True, "data": ["VCP analysis report"]}
# Sprint 11 P4 — the VCP backlog flow now calls compute_trend_template_full
# (8-criterion) and feeds tt_result into tf.fmt_minervini_trend_template.
# Return a realistically-shaped dict so the formatter doesn't blow up.
_ec_mock.compute_trend_template_full.return_value = {
    "ok": True, "error": None,
    "data": {
        "close": 100.0, "ma50": 95.0, "ma150": 90.0, "ma200": 88.0,
        "low_52w": 70.0, "high_52w": 110.0,
        "criteria": {
            "c1_price_above_ma150_ma200": True, "c2_ma150_above_ma200": True,
            "c3_ma200_uptrend_1m": True, "c4_ma50_above_ma150_ma200": True,
            "c5_price_above_ma50": True, "c6_above_30pct_52w_low": True,
            "c7_below_25pct_52w_high": True, "c8_rs_above_spy_12m": True,
        },
        "passed": 8, "score_10": 10.0,
    },
}

_menus_mock = MagicMock()
_menus_mock.get_main_menu.return_value      = "MAIN_MENU"
_menus_mock.get_setup_keyboard.side_effect  = lambda t_id: f"SETUP_KB_{t_id}"
_menus_mock.get_rating_keyboard.side_effect = lambda t_id, field: f"RATING_KB_{t_id}_{field}"


def _run(chat_id, trade_rows=None):
    """Run get_next_missing with all dependencies patched."""
    if trade_rows is not None:
        _repo_mock.get_incomplete_trades.return_value = trade_rows
    _user_state.clear()
    _fake_bot.reset_mock()
    _repo_mock.update_trade.reset_mock()
    _ec_mock.reset_mock()
    _ec_mock.get_minervini_analysis.return_value = {"ok": True, "data": ["VCP analysis report"]}
    _ec_mock.compute_trend_template_full.return_value = {
        "ok": True, "error": None,
        "data": {
            "close": 100.0, "ma50": 95.0, "ma150": 90.0, "ma200": 88.0,
            "low_52w": 70.0, "high_52w": 110.0,
            "criteria": {
                "c1_price_above_ma150_ma200": True, "c2_ma150_above_ma200": True,
                "c3_ma200_uptrend_1m": True, "c4_ma50_above_ma150_ma200": True,
                "c5_price_above_ma50": True, "c6_above_30pct_52w_low": True,
                "c7_below_25pct_52w_high": True, "c8_rs_above_spy_12m": True,
            },
            "passed": 8, "score_10": 10.0,
        },
    }

    with patch.object(tb, 'bot', _fake_bot), \
         patch.object(tb, 'supabase', _fake_sb), \
         patch.object(tb, 'user_state', _user_state), \
         patch.object(tb, 'repo', _repo_mock), \
         patch.object(tb, 'ec', _ec_mock), \
         patch.object(tb, 'get_main_menu', _menus_mock.get_main_menu), \
         patch.object(tb, 'get_setup_keyboard', _menus_mock.get_setup_keyboard), \
         patch.object(tb, 'get_rating_keyboard', _menus_mock.get_rating_keyboard):
        tb.get_next_missing(chat_id)


# ── No incomplete trades ───────────────────────────────────────────────────────

class TestNoMissingTrades:
    def test_sends_complete_message(self):
        _run(1001, [])
        text = _fake_bot.send_message.call_args[0][1]
        assert "מעודכן לחלוטין" in text

    def test_sends_to_correct_chat(self):
        _run(9999, [])
        assert _fake_bot.send_message.call_args[0][0] == 9999


# ── Legacy trades skipped ──────────────────────────────────────────────────────

class TestLegacySkipped:
    def test_legacy_trade_skipped_sends_complete(self):
        _run(1001, [
            {"trade_id": "T1", "symbol": "AAA", "side": "BUY",
             "trade_date": "2025-01-01", "setup_type": "Legacy",
             "quality": None, "initial_stop": None, "campaign_id": None}
        ])
        text = _fake_bot.send_message.call_args[0][1]
        assert "מעודכן לחלוטין" in text


# ── setup_type missing ─────────────────────────────────────────────────────────

class TestSetupTypeMissing:
    def _trade(self):
        return {"trade_id": "T2", "symbol": "BBB", "side": "BUY",
                "trade_date": "2025-02-01", "setup_type": None,
                "quality": None, "initial_stop": None, "campaign_id": None}

    def test_prompts_setup_keyboard(self):
        _run(1002, [self._trade()])
        text = _fake_bot.send_message.call_args[0][1]
        assert "סווג" in text or "Setup" in text

    def test_sends_setup_keyboard(self):
        _run(1002, [self._trade()])
        kwargs = _fake_bot.send_message.call_args[1]
        assert kwargs.get("reply_markup") == "SETUP_KB_T2"


# ── quality missing ────────────────────────────────────────────────────────────

class TestQualityMissing:
    def _trade(self, setup="SWING"):
        return {"trade_id": "T3", "symbol": "CCC", "side": "BUY",
                "trade_date": "2025-03-01", "setup_type": setup,
                "quality": None, "initial_stop": 100.0, "campaign_id": None}

    def test_non_vcp_prompts_quality_rating(self):
        _run(1003, [self._trade("SWING")])
        text = _fake_bot.send_message.call_args[0][1]
        assert "איכות" in text or "quality" in text.lower()

    def test_vcp_triggers_minervini_analysis(self):
        _run(1003, [self._trade("VCP")])
        # Sprint 11 P4 — migrated to the full 8-criterion compute_trend_template_full
        _ec_mock.compute_trend_template_full.assert_called_once_with("CCC")

    def test_vcp_sends_rating_keyboard(self):
        _run(1003, [self._trade("VCP")])
        kwargs = _fake_bot.send_message.call_args[1]
        assert "RATING_KB_T3_quality" in str(kwargs.get("reply_markup", ""))


# ── initial_stop missing (BUY) ─────────────────────────────────────────────────

class TestInitialStopMissing:
    def _trade(self):
        return {"trade_id": "T4", "symbol": "DDD", "side": "BUY",
                "trade_date": "2025-04-01", "setup_type": "SWING",
                "quality": 7, "initial_stop": None, "campaign_id": None}

    def test_prompts_initial_stop(self):
        _run(1004, [self._trade()])
        text = _fake_bot.send_message.call_args[0][1]
        assert "סטופ" in text or "Stop" in text

    def test_sets_user_state(self):
        _run(1004, [self._trade()])
        assert _user_state.get(1004, {}).get("action") == "initial_stop"
        assert _user_state[1004]["t_id"] == "T4"


# ── SELL: score missing ────────────────────────────────────────────────────────

class TestSellScoreMissing:
    def _trade(self):
        return {"trade_id": "T5", "symbol": "EEE", "side": "SELL",
                "trade_date": "2025-05-01", "setup_type": "VCP",
                "quality": 8, "score": None, "image_url": None,
                "management_notes": None, "initial_stop": 90.0, "campaign_id": None}

    def test_prompts_score_rating(self):
        _run(1005, [self._trade()])
        text = _fake_bot.send_message.call_args[0][1]
        assert "דרג" in text or "score" in text.lower() or "סגירת" in text


# ── SELL: image_url missing ────────────────────────────────────────────────────

class TestSellImageMissing:
    def _trade(self):
        return {"trade_id": "T6", "symbol": "FFF", "side": "SELL",
                "trade_date": "2025-06-01", "setup_type": "VCP",
                "quality": 8, "score": 7, "image_url": None,
                "management_notes": None, "initial_stop": 80.0, "campaign_id": None}

    def test_prompts_image_url(self):
        _run(1006, [self._trade()])
        text = _fake_bot.send_message.call_args[0][1]
        assert "קישור" in text or "תמונה" in text or "TradingView" in text

    def test_sets_user_state_image(self):
        _run(1006, [self._trade()])
        assert _user_state.get(1006, {}).get("action") == "image"


# ── SELL: management_notes missing ────────────────────────────────────────────

class TestSellManagementNotesMissing:
    def _trade(self):
        return {"trade_id": "T7", "symbol": "GGG", "side": "SELL",
                "trade_date": "2025-07-01", "setup_type": "VCP",
                "quality": 8, "score": 7, "image_url": "http://img.url",
                "management_notes": None, "initial_stop": 70.0, "campaign_id": None}

    def test_prompts_management_notes(self):
        _run(1007, [self._trade()])
        text = _fake_bot.send_message.call_args[0][1]
        assert "ניהול" in text or "תובנות" in text

    def test_sets_user_state_management_notes(self):
        _run(1007, [self._trade()])
        assert _user_state.get(1007, {}).get("action") == "management_notes"


# ── ALGO auto-fill initial_stop ────────────────────────────────────────────────

class TestAlgoAutoFill:
    def test_algo_buy_with_no_stop_gets_auto_filled_and_skipped(self):
        _run(1008, [
            {"trade_id": "T8", "symbol": "HHH", "side": "BUY",
             "trade_date": "2025-08-01", "setup_type": "ALGO",
             "quality": None, "initial_stop": None, "campaign_id": None}
        ])
        _repo_mock.update_trade.assert_called_once()
        args = _repo_mock.update_trade.call_args[0]
        assert args[2] == {"initial_stop": -1, "stop_loss": -1}
