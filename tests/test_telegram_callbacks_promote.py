"""
Tests for telegram_callbacks.handle_queries — stop-promotion routing.

Verifies the new tap-only callbacks added for UX_TELEGRAM_AUDIT_DAY3 Pain 1:
  * promote_open            → handle_stop_promote_entry
  * promote_pick|<idx>      → handle_stop_promote_pick(idx)
  * promote_algo_noop       → alert, no state change
  * start_trail_flow        → now shows inline keyboard (no "type the number"),
                              and falls back to the lightweight entry when no
                              cached positions exist (no heavy room re-run).

The lazy `import telegram_bot as _tb` inside handle_queries is satisfied by
injecting a stub module into sys.modules before the call.
"""
import sys, os, types as py_types
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for mod in ["telebot", "supabase", "dotenv", "engine_core", "adaptive_risk_engine",
            "telegram_formatters", "supabase_repository", "ibkr_sync_runner"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# CRITICAL: the real bot_core.bot is a telebot.TeleBot whose
# @bot.callback_query_handler decorator REGISTERS the handler and returns
# the ORIGINAL function unchanged. Under a MagicMock bot the decorator
# returns a MagicMock, replacing handle_queries with an un-callable mock.
#
# To get a callable handle_queries WITHOUT mutating the shared
# telegram_callbacks / bot_core modules other tests rely on, we load the
# telegram_callbacks source under a private module name with our own
# identity-decorator bot injected. Fully isolated: nothing in sys.modules
# that sibling tests use is replaced.
import importlib.util


class _IdentityDecoratorBot:
    def callback_query_handler(self, *a, **k):
        return lambda fn: fn  # register-and-return-unchanged

    def __getattr__(self, name):
        return MagicMock()


def _load_isolated_callbacks():
    _bc = py_types.ModuleType("bot_core")
    _bc.bot        = _IdentityDecoratorBot()
    _bc.supabase   = MagicMock()
    _bc.user_state = {}
    _bc.RTL        = "‏"
    _bc.TOKEN      = ""
    _bc.ADMIN_ID   = ""

    saved_bc = sys.modules.get("bot_core")
    saved_tc = sys.modules.get("telegram_callbacks")
    sys.modules["bot_core"] = _bc
    try:
        path = os.path.join(os.path.dirname(__file__), "..", "telegram_callbacks.py")
        spec = importlib.util.spec_from_file_location("_isolated_tc", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        # Restore shared modules so sibling tests are unaffected.
        if saved_bc is not None:
            sys.modules["bot_core"] = saved_bc
        else:
            sys.modules.pop("bot_core", None)
        if saved_tc is not None:
            sys.modules["telegram_callbacks"] = saved_tc


tc = _load_isolated_callbacks()


def _call(data, *, state=None):
    """Invoke handle_queries with a fake call object + stubbed telegram_bot."""
    fake_bot = MagicMock()
    fake_tb = py_types.ModuleType("telegram_bot")
    fake_tb.handle_stop_promote_entry = MagicMock()
    fake_tb.handle_stop_promote_pick = MagicMock()
    fake_tb.build_stop_promote_keyboard = MagicMock(return_value="KB")
    fake_tb.handle_drilldown = MagicMock()
    fake_tb.get_next_missing = MagicMock()
    sys.modules["telegram_bot"] = fake_tb

    call = MagicMock()
    call.data = data
    call.id = "cb1"
    call.message.chat.id = 5001
    call.message.message_id = 99

    st = {} if state is None else state
    with patch.object(tc, 'bot', fake_bot), \
         patch.object(tc, 'user_state', st):
        tc.handle_queries(call)
    return fake_bot, fake_tb, st


class TestPromoteRouting:
    def test_promote_open_calls_entry(self):
        _bot, tb, _ = _call("promote_open")
        tb.handle_stop_promote_entry.assert_called_once_with(5001)

    def test_promote_pick_passes_index(self):
        _bot, tb, _ = _call("promote_pick|3")
        tb.handle_stop_promote_pick.assert_called_once_with(5001, 3)

    def test_promote_pick_bad_index_no_crash(self):
        fake_bot, tb, _ = _call("promote_pick|abc")
        tb.handle_stop_promote_pick.assert_not_called()
        # user gets an error message, no exception
        assert fake_bot.send_message.called

    def test_promote_algo_noop_shows_alert_no_state(self):
        fake_bot, tb, st = _call("promote_algo_noop")
        fake_bot.answer_callback_query.assert_called_once()
        kwargs = fake_bot.answer_callback_query.call_args[1]
        assert kwargs.get("show_alert") is True
        tb.handle_stop_promote_pick.assert_not_called()
        assert st == {}


class TestStartTrailFlowTapOnly:
    def test_with_cached_positions_shows_inline_keyboard(self):
        state = {5001: {"temp_positions": [{"symbol": "CAT"}]}}
        fake_bot, tb, st = _call("start_trail_flow", state=state)
        tb.build_stop_promote_keyboard.assert_called_once()
        # must NOT switch to the legacy 'type the trade number' action
        assert st[5001].get("action") != "select_trade_index"
        kwargs = fake_bot.send_message.call_args[1]
        assert kwargs.get("reply_markup") == "KB"

    def test_without_cached_positions_falls_back_to_lightweight_entry(self):
        fake_bot, tb, _ = _call("start_trail_flow", state={})
        # No heavy 'חדר מצב' re-run prompt — open the lightweight list instead
        tb.handle_stop_promote_entry.assert_called_once_with(5001)


# ── Sprint-12 routing: /clean confirm + price-fallback note ──────────────────

def _call_ext(data, *, state=None):
    """Like _call but the stub telegram_bot also exposes the Sprint-12
    clean-gate handlers (mirrors the real re-export in telegram_bot.py)."""
    fake_bot = MagicMock()
    fake_tb = py_types.ModuleType("telegram_bot")
    fake_tb.handle_stop_promote_entry = MagicMock()
    fake_tb.handle_stop_promote_pick = MagicMock()
    fake_tb.build_stop_promote_keyboard = MagicMock(return_value="KB")
    fake_tb.handle_drilldown = MagicMock()
    fake_tb.get_next_missing = MagicMock()
    fake_tb.finalize_pending_loosen = MagicMock()
    fake_tb.finalize_pending_clean = MagicMock()
    fake_tb.handle_clean_entry = MagicMock()
    sys.modules["telegram_bot"] = fake_tb

    call = MagicMock()
    call.data = data
    call.id = "cb1"
    call.message.chat.id = 5001
    call.message.message_id = 99

    st = {} if state is None else state
    with patch.object(tc, 'bot', fake_bot), \
         patch.object(tc, 'user_state', st):
        tc.handle_queries(call)
    return fake_bot, fake_tb, st


class TestCleanConfirmRouting:
    def test_clean_confirm_yes_routes_finalize_true(self):
        fake_bot, tb, _ = _call_ext("clean_confirm|yes")
        tb.finalize_pending_clean.assert_called_once_with(5001, True)
        fake_bot.answer_callback_query.assert_called_once()

    def test_clean_confirm_no_routes_finalize_false(self):
        fake_bot, tb, _ = _call_ext("clean_confirm|no")
        tb.finalize_pending_clean.assert_called_once_with(5001, False)

    def test_clean_confirm_does_not_touch_loosen(self):
        _fb, tb, _ = _call_ext("clean_confirm|yes")
        tb.finalize_pending_loosen.assert_not_called()


class TestPriceFallbackNoteRouting:
    def test_promote_price_fallback_note_alert_only_no_state(self):
        fake_bot, tb, st = _call_ext("promote_price_fallback_note")
        # telegram_formatters is stubbed as a MagicMock in this harness, so
        # the echoed text is a mock here; the EXACT canonical string is
        # asserted in test_price_fallback_label.py. This test proves the
        # ROUTING is alert-only and never an action / never mutates state.
        fake_bot.answer_callback_query.assert_called_once()
        kwargs = fake_bot.answer_callback_query.call_args[1]
        assert kwargs.get("show_alert") is True
        assert "text" in kwargs  # an echo is provided (the canonical label)
        assert st == {}
        tb.handle_stop_promote_pick.assert_not_called()
