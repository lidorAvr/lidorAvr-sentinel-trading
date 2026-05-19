"""
Phase JOURNAL-1 (T-J1) acceptance tests — telegram_backlog.get_next_missing().

Covers the additive SELL-leg inheritance branch: Setup/Quality are entry-time,
campaign-level properties answered at open; a SELL (close) row must inherit
them from the campaign's first BUY (symmetric to the existing BUY add-on
inheritance) so the close journal does not re-ask an already-answered question.

Harness mirrors tests/test_telegram_backlog.py exactly: same module stubs,
same patch.object-on-`tb` approach, same _run() shape / dependency mocks.
"""
import sys, os, types as py_types
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Stub telebot / supabase / dotenv if not yet loaded (mirror existing) ──────
for mod in ["telebot", "supabase", "dotenv", "engine_core", "adaptive_risk_engine",
            "telegram_formatters", "ibkr_sync_runner"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

if "telebot" in sys.modules:
    _tb_mod = sys.modules["telebot"]
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

if "bot_core" not in sys.modules:
    _bc = py_types.ModuleType("bot_core")
    _bc.bot        = MagicMock()
    _bc.supabase   = MagicMock()
    _bc.user_state = {}
    _bc.RTL        = "‏"
    _bc.TOKEN      = ""
    _bc.ADMIN_ID   = ""
    sys.modules["bot_core"] = _bc

if "supabase_repository" not in sys.modules:
    sys.modules["supabase_repository"] = MagicMock()

import telegram_backlog as tb  # noqa

# Module-level fakes — used with patch.object so they work even when
# telegram_backlog was pre-imported (e.g. by test_developer_menu.py).
_fake_bot   = MagicMock()
_fake_sb    = MagicMock()
_user_state = {}

_repo_mock = MagicMock()
_repo_mock.get_incomplete_trades.return_value = []
_repo_mock.get_earlier_buys_for_campaign.return_value = []

_ec_mock = MagicMock()
_ec_mock.get_minervini_analysis.return_value = {"ok": True, "data": ["VCP analysis report"]}

_menus_mock = MagicMock()
_menus_mock.get_main_menu.return_value      = "MAIN_MENU"
_menus_mock.get_setup_keyboard.side_effect  = lambda t_id: f"SETUP_KB_{t_id}"
_menus_mock.get_rating_keyboard.side_effect = lambda t_id, field: f"RATING_KB_{t_id}_{field}"


def _run(chat_id, trade_rows=None, earlier_buys=None):
    """Run get_next_missing with all dependencies patched (mirrors
    tests/test_telegram_backlog.py::_run; adds earlier_buys control)."""
    if trade_rows is not None:
        _repo_mock.get_incomplete_trades.return_value = trade_rows
    _repo_mock.get_earlier_buys_for_campaign.return_value = earlier_buys or []
    _user_state.clear()
    _fake_bot.reset_mock()
    _repo_mock.update_trade.reset_mock()
    _repo_mock.get_earlier_buys_for_campaign.reset_mock()
    _ec_mock.reset_mock()
    _ec_mock.get_minervini_analysis.return_value = {"ok": True, "data": ["VCP analysis report"]}

    with patch.object(tb, 'bot', _fake_bot), \
         patch.object(tb, 'supabase', _fake_sb), \
         patch.object(tb, 'user_state', _user_state), \
         patch.object(tb, 'repo', _repo_mock), \
         patch.object(tb, 'ec', _ec_mock), \
         patch.object(tb, 'get_main_menu', _menus_mock.get_main_menu), \
         patch.object(tb, 'get_setup_keyboard', _menus_mock.get_setup_keyboard), \
         patch.object(tb, 'get_rating_keyboard', _menus_mock.get_rating_keyboard):
        tb.get_next_missing(chat_id)


def _sell_row(setup=None, quality=None, cid="CMP-1"):
    return {"trade_id": "S1", "symbol": "PWR", "side": "SELL",
            "trade_date": "2026-05-10", "setup_type": setup,
            "quality": quality, "score": None, "image_url": None,
            "management_notes": None, "initial_stop": 90.0,
            "campaign_id": cid}


def _all_send_texts():
    return [c[0][1] for c in _fake_bot.send_message.call_args_list]


# ── 1. SELL + campaign first BUY has BOTH setup_type and quality ───────────────

class TestSellInheritsBothFromCampaignBuy:
    def _buy(self):
        return {"trade_id": "B0", "side": "BUY", "campaign_id": "CMP-1",
                "setup_type": "VCP", "quality": 8,
                "initial_stop": 100.0, "stop_loss": 95.0}

    def test_update_trade_called_with_both_inherited(self):
        _run(2001, [_sell_row()], earlier_buys=[self._buy()])
        _repo_mock.update_trade.assert_called_once()
        args = _repo_mock.update_trade.call_args[0]
        assert args[1] == "S1"
        assert args[2] == {"setup_type": "VCP", "quality": 8}

    def test_setup_and_quality_prompts_not_sent(self):
        _run(2001, [_sell_row()], earlier_buys=[self._buy()])
        texts = " ".join(_all_send_texts())
        assert "אנא סווג את האסטרטגיה" not in texts
        assert "מהי איכות הסטאפ" not in texts

    def test_flow_proceeds_to_close_specific_exit_score_prompt(self):
        # After inheritance the SELL has no setup_type/quality re-asked; the
        # incomplete row is consumed (continue), so with only this row the
        # journal reports complete — i.e. no Setup/Quality prompt fired.
        _run(2001, [_sell_row()], earlier_buys=[self._buy()])
        texts = " ".join(_all_send_texts())
        assert "אנא סווג את האסטרטגיה" not in texts
        # The legitimate close-specific item is the exit-score prompt — verify
        # it is reached on a re-scan where the SELL now carries inherited
        # setup/quality (still missing only its own score).
        _run(2002, [_sell_row(setup="VCP", quality=8)], earlier_buys=[self._buy()])
        assert "כיצד היית מדרג את סגירת העסקה" in " ".join(_all_send_texts())


# ── 2. SELL + BUY has setup_type but NOT quality ──────────────────────────────

class TestSellPartialInheritOnlySetup:
    def _buy(self):
        return {"trade_id": "B0", "side": "BUY", "campaign_id": "CMP-1",
                "setup_type": "SWING", "quality": None,
                "initial_stop": 100.0, "stop_loss": 95.0}

    def test_update_trade_called_with_only_setup_type(self):
        _run(2003, [_sell_row()], earlier_buys=[self._buy()])
        _repo_mock.update_trade.assert_called_once()
        assert _repo_mock.update_trade.call_args[0][2] == {"setup_type": "SWING"}

    def test_quality_still_asked_after_setup_inherited(self):
        # SELL re-scanned with inherited setup but still missing quality.
        _run(2004, [_sell_row(setup="SWING")], earlier_buys=[self._buy()])
        assert "מהי איכות הסטאפ" in " ".join(_all_send_texts())


# ── 3. SELL with no campaign_id ⇒ no inheritance, Setup ask still fires ────────

class TestSellNoCampaignNoInheritance:
    def test_no_inheritance_update_trade_not_called(self):
        _run(2005, [_sell_row(cid=None)], earlier_buys=[
            {"trade_id": "B0", "side": "BUY", "setup_type": "VCP", "quality": 8}])
        _repo_mock.update_trade.assert_not_called()

    def test_existing_setup_ask_still_fires(self):
        _run(2005, [_sell_row(cid=None)])
        assert "אנא סווג את האסטרטגיה" in " ".join(_all_send_texts())

    def test_get_earlier_buys_not_consulted_without_campaign(self):
        _run(2005, [_sell_row(cid=None)])
        _repo_mock.get_earlier_buys_for_campaign.assert_not_called()


# ── 4. SELL, campaign BUY itself has no setup_type/quality ⇒ no false recovery ─

class TestSellCampaignBuyUnclassifiedNoFalseRecovery:
    def _buy(self):
        return {"trade_id": "B0", "side": "BUY", "campaign_id": "CMP-1",
                "setup_type": None, "quality": None,
                "initial_stop": None, "stop_loss": None}

    def test_no_inheritance_update_trade_not_called(self):
        _run(2006, [_sell_row()], earlier_buys=[self._buy()])
        _repo_mock.update_trade.assert_not_called()

    def test_existing_setup_ask_fires(self):
        _run(2006, [_sell_row()], earlier_buys=[self._buy()])
        assert "אנא סווג את האסטרטגיה" in " ".join(_all_send_texts())


# ── 5. SELL already has setup_type ⇒ never overwritten ────────────────────────

class TestSellExistingSetupNeverOverwritten:
    def _buy(self):
        return {"trade_id": "B0", "side": "BUY", "campaign_id": "CMP-1",
                "setup_type": "VCP", "quality": 9,
                "initial_stop": 100.0, "stop_loss": 95.0}

    def test_existing_setup_not_overwritten_only_quality_inherited(self):
        # SELL already has its own setup_type='SWING'; only quality missing.
        _run(2007, [_sell_row(setup="SWING", quality=None)],
             earlier_buys=[self._buy()])
        _repo_mock.update_trade.assert_called_once()
        upd = _repo_mock.update_trade.call_args[0][2]
        assert "setup_type" not in upd
        assert upd == {"quality": 9}

    def test_no_spurious_update_when_both_already_set(self):
        _run(2008, [_sell_row(setup="SWING", quality=6)],
             earlier_buys=[self._buy()])
        _repo_mock.update_trade.assert_not_called()


# ── 6. BUY add-on regression: unchanged inheritance behaviour ─────────────────

class TestBuyAddOnInheritanceRegression:
    def _buy_addon(self):
        return {"trade_id": "B2", "symbol": "PWR", "side": "BUY",
                "trade_date": "2026-05-12", "setup_type": None,
                "quality": None, "initial_stop": None,
                "campaign_id": "CMP-1"}

    def _first_buy(self):
        return {"trade_id": "B0", "side": "BUY", "campaign_id": "CMP-1",
                "setup_type": "VCP", "quality": 8,
                "initial_stop": 100.0, "stop_loss": 95.0}

    def test_buy_addon_inherits_setup_quality_and_stops_unchanged(self):
        _run(2009, [self._buy_addon()], earlier_buys=[self._first_buy()])
        _repo_mock.update_trade.assert_called_once()
        args = _repo_mock.update_trade.call_args[0]
        assert args[1] == "B2"
        assert args[2] == {
            "setup_type": "VCP",
            "quality": 8,
            "initial_stop": 100.0,
            "stop_loss": 95.0,
        }
