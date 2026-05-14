"""test_c1_ux_shortcuts.py — UX shortcuts + flattened main menu.

Covers C1 from the 2026-05-14 session feedback ("יותר מדי לחיצות").

Two layers:
  1. _SLASH_SHORTCUTS dict — single-letter aliases /p /m /j /h /d /r /home
     mapped to the canonical button text the existing dispatcher handles.
  2. get_main_menu() — flattened: the 2 most-frequent screens (portfolio,
     market) and stats are direct buttons; analysis stays nested.
"""
import os
import sys
import types as py_types
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# NOTE: do NOT stub telegram_formatters / engine_core / adaptive_risk_engine
# here — those are real modules and stubbing them leaks across the pytest
# session (sys.modules is global), breaking later tests that need real
# behavior. Only stub the truly external deps that aren't installed in the
# sandbox (telebot, supabase, dotenv).
for _mod in ("telebot", "telebot.types", "supabase", "dotenv"):
    sys.modules.setdefault(_mod, MagicMock())
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")


# ════════════════════════════════════════════════════════════════════════════════
# Layer 1: _SLASH_SHORTCUTS mapping
# ════════════════════════════════════════════════════════════════════════════════

class TestSlashShortcutsMapping:
    """Each shortcut must map to a button text the dispatcher already
    handles. If a mapping changes, this test catches it before the user
    types `/p` and gets nothing back."""

    def _shortcuts(self):
        import telegram_bot as tb
        return tb._SLASH_SHORTCUTS

    def test_p_maps_to_portfolio_button(self):
        assert self._shortcuts()["/p"] == "📊 חדר מצב (פוזיציות)"

    def test_m_maps_to_market_button(self):
        assert self._shortcuts()["/m"] == "🌡️ משטר שוק וסיכונים"

    def test_j_maps_to_next_command(self):
        # /j → /next (journal handler already handles /next)
        assert self._shortcuts()["/j"] == "/next"

    def test_h_maps_to_help_button(self):
        assert self._shortcuts()["/h"] == "❓ עזרה"

    def test_d_maps_to_developer_menu(self):
        assert self._shortcuts()["/d"] == "🛠️ מפתח"

    def test_r_maps_to_risk_stats(self):
        # /r → /stats (handler already handles /stats)
        assert self._shortcuts()["/r"] == "/stats"

    def test_home_maps_to_back_button(self):
        assert self._shortcuts()["/home"] == "⬅️ חזרה לתפריט ראשי"

    def test_all_targets_are_strings(self):
        """Defensive: every value must be a non-empty string (otherwise
        the dispatcher would fall through to default-handler)."""
        for src, target in self._shortcuts().items():
            assert isinstance(target, str) and target.strip(), \
                f"Shortcut {src} has invalid target {target!r}"

    def test_no_recursive_shortcut(self):
        """A shortcut MUST NOT map to another shortcut — that would loop
        through dispatch twice in the bot before reaching the handler."""
        shortcuts = self._shortcuts()
        for src, target in shortcuts.items():
            assert target not in shortcuts, (
                f"Shortcut {src} → {target} is itself a shortcut key — "
                f"would cause double-dispatch."
            )


# ════════════════════════════════════════════════════════════════════════════════
# Layer 2: Main menu has the direct buttons
# ════════════════════════════════════════════════════════════════════════════════

class TestFlatMainMenu:
    """The flattened main menu (C1) puts the most-frequent screens as
    direct buttons, not nested under sub-menus.

    `telebot` is stubbed in this test env (no real KeyboardButton), so we
    introspect the source of `get_main_menu` directly. This is more
    robust to stub-shape changes than trying to fake the markup tree."""

    def _main_menu_buttons(self):
        import inspect
        import telegram_menus as menus
        return inspect.getsource(menus.get_main_menu)

    def test_portfolio_is_direct_button(self):
        """Was buried under 📊 מצב תיק → 📊 חדר מצב. Now top-level."""
        src = self._main_menu_buttons()
        assert "📊 חדר מצב (פוזיציות)" in src

    def test_market_regime_is_direct_button(self):
        src = self._main_menu_buttons()
        assert "🌡️ משטר שוק וסיכונים" in src

    def test_stats_is_direct_button(self):
        """B3 makes stats more useful (gate explanations etc.) — promote it."""
        src = self._main_menu_buttons()
        assert "📊 סטטיסטיקת ציות" in src

    def test_journal_still_there(self):
        src = self._main_menu_buttons()
        assert "📚 יומן" in src

    def test_developer_still_there(self):
        src = self._main_menu_buttons()
        assert "🛠️ מפתח" in src

    def test_help_still_there(self):
        src = self._main_menu_buttons()
        assert "❓ עזרה" in src

    def test_analysis_still_there(self):
        src = self._main_menu_buttons()
        assert "🔬 ניתוח" in src


# ════════════════════════════════════════════════════════════════════════════════
# Help text mentions the new shortcuts
# ════════════════════════════════════════════════════════════════════════════════

class TestHelpMentionsShortcuts:
    def test_help_text_has_shortcuts_section(self):
        """The /help and ❓ עזרה output must surface the new shortcuts so
        users discover them."""
        # Read the help text directly from the source (the bot itself is
        # not easily exercisable without a full mock harness)
        with open(os.path.join(os.path.dirname(__file__), "..",
                                "telegram_bot.py"), encoding="utf-8") as f:
            src = f.read()
        # Verify each shortcut appears in the help block
        for short in ("/p", "/m", "/r", "/j", "/d", "/h"):
            assert f"`{short}`" in src, (
                f"Shortcut {short} not mentioned in telegram_bot.py "
                f"(expected in /help text)"
            )
