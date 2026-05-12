"""
Tests for telegram_menus.py — menu and keyboard builder functions.

Uses the same fake telebot stubs as test_phase3_state_alerts.py.
Tests verify return values and callback_data content, not mock call history.
"""
import sys, os, types as py_types
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Stub telebot with fake classes that expose structure ───────────────────────
if "telebot" not in sys.modules:
    sys.modules["telebot"] = MagicMock()

_tb_mod = sys.modules["telebot"]

class _FakeReplyMarkup:
    def __init__(self, *a, **k): self.buttons = []
    def add(self, *btns): self.buttons.extend(btns)

class _FakeInlineMarkup:
    def __init__(self, *a, **k): self.buttons = []
    def add(self, *btns): self.buttons.extend(btns)

class _FakeKeyboardButton:
    def __init__(self, text, *a, **k): self.text = text

class _FakeInlineButton:
    def __init__(self, text, callback_data=None, *a, **k):
        self.text = text
        self.callback_data = callback_data or ""

_tb_types = py_types.ModuleType("telebot.types")
_tb_types.ReplyKeyboardMarkup  = _FakeReplyMarkup
_tb_types.InlineKeyboardMarkup = _FakeInlineMarkup
_tb_types.KeyboardButton       = _FakeKeyboardButton
_tb_types.InlineKeyboardButton = _FakeInlineButton
_tb_mod.types = _tb_types
sys.modules["telebot.types"] = _tb_types

import telegram_menus as menus


# ── Reply menus ────────────────────────────────────────────────────────────────

class TestGetMainMenu:
    def test_returns_markup(self):
        assert menus.get_main_menu() is not None

    def test_has_buttons(self):
        m = menus.get_main_menu()
        assert len(m.buttons) >= 3


class TestGetDeveloperMenu:
    def test_returns_markup(self):
        assert menus.get_developer_menu() is not None

    def test_has_ibkr_sync_button(self):
        m = menus.get_developer_menu()
        texts = [b.text for b in m.buttons]
        assert any("IBKR" in t for t in texts)


class TestGetPortfolioMenu:
    def test_returns_markup(self):
        assert menus.get_portfolio_menu() is not None

    def test_has_back_button(self):
        m = menus.get_portfolio_menu()
        texts = [b.text for b in m.buttons]
        assert any("חזרה" in t for t in texts)


class TestGetAnalysisMenu:
    def test_returns_markup(self):
        assert menus.get_analysis_menu() is not None


class TestGetJournalMenu:
    def test_returns_markup(self):
        assert menus.get_journal_menu() is not None

    def test_has_backlog_button(self):
        m = menus.get_journal_menu()
        texts = [b.text for b in m.buttons]
        assert any("יומן" in t or "Backlog" in t for t in texts)


# ── Inline keyboards ───────────────────────────────────────────────────────────

class TestGetRatingKeyboard:
    def test_returns_markup(self):
        assert menus.get_rating_keyboard("T1", "quality") is not None

    def test_has_ten_rating_buttons(self):
        m = menus.get_rating_keyboard("T1", "quality")
        numeric = [b for b in m.buttons if b.text.isdigit()]
        assert len(numeric) == 10

    def test_callback_data_contains_trade_id(self):
        m = menus.get_rating_keyboard("T42", "score")
        assert all("T42" in b.callback_data for b in m.buttons if b.text.isdigit())

    def test_callback_data_contains_field(self):
        m = menus.get_rating_keyboard("T1", "quality")
        assert all("quality" in b.callback_data for b in m.buttons if b.text.isdigit())

    def test_has_skip_button(self):
        m = menus.get_rating_keyboard("T1", "quality")
        assert any("דילוג" in b.text for b in m.buttons)


class TestGetSetupKeyboard:
    def test_returns_markup(self):
        assert menus.get_setup_keyboard("T1") is not None

    def test_vcp_button_present(self):
        m = menus.get_setup_keyboard("T1")
        assert any(b.text == "VCP" for b in m.buttons)

    def test_algo_button_present(self):
        m = menus.get_setup_keyboard("T1")
        assert any(b.text == "ALGO" for b in m.buttons)

    def test_skip_button_present(self):
        m = menus.get_setup_keyboard("T1")
        assert any("דילוג" in b.text for b in m.buttons)

    def test_callback_data_has_setup_type(self):
        m = menus.get_setup_keyboard("T99")
        non_skip = [b for b in m.buttons if "דילוג" not in b.text]
        assert all("setup_type" in b.callback_data for b in non_skip)

    def test_callback_data_has_trade_id(self):
        m = menus.get_setup_keyboard("T99")
        assert all("T99" in b.callback_data for b in m.buttons)
