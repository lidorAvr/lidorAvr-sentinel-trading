"""
Tests for telegram_portfolio.py — handle_drilldown() symbol X-ray flow.

Uses patch.object to patch module-level names in telegram_portfolio directly,
avoiding sys.modules isolation issues.
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

if "bot_core" not in sys.modules:
    _bc = py_types.ModuleType("bot_core")
    _bc.bot        = MagicMock()
    _bc.supabase   = MagicMock()
    _bc.user_state = {}
    _bc.RTL        = "‏"
    _bc.TOKEN      = ""
    _bc.ADMIN_ID   = ""
    sys.modules["bot_core"] = _bc

if "bot_helpers" not in sys.modules:
    _bh = py_types.ModuleType("bot_helpers")
    _bh.get_account_settings = lambda: {"total_deposited": 10000.0, "risk_pct_input": 0.5}
    _bh.get_nav_and_risk = lambda s=None: (10000.0, 50.0, None)
    _bh._bot_log = lambda *a, **k: None
    _bh._read_last_log_lines = lambda *a, **k: ""
    _bh._write_runner_decision = lambda *a, **k: None
    _bh._DEV_LOG_FILES = {}
    _bh._BOT_LOG_FILE = ""
    _bh._BOT_LOG_MAX_LINES = 2000
    _bh._RM_STATE_FILE = "risk_monitor_state.json"
    sys.modules["bot_helpers"] = _bh

if "supabase_repository" not in sys.modules:
    sys.modules["supabase_repository"] = MagicMock()

import telegram_portfolio as tp  # noqa


# ── Shared mocks (used via patch.object so they bind to the real module) ──────
_fake_bot = MagicMock()
_fake_sb  = MagicMock()
_repo_mock = MagicMock()
_ec_mock = MagicMock()


def _setup_send_message():
    """Configure bot.send_message to return an object with .message_id."""
    msg = MagicMock()
    msg.message_id = 42
    _fake_bot.send_message.return_value = msg


def _make_position(**overrides):
    """Build a default open position dict."""
    base = {
        'price': 100.0, 'quantity': 10, 'stop_loss': 95.0,
        'initial_stop': 90.0, 'setup_type': 'VCP',
        'management_state': 'full_position', 'entry_date': '2025-01-01',
        'base_price': 100.0, 'base_qty': 10,
    }
    base.update(overrides)
    return base


def _run(chat_id, symbol, *, positions_df=None, engine_data=None,
         live_price=105.0, engine_ok=True):
    """Run handle_drilldown with all deps patched."""
    _fake_bot.reset_mock()
    _setup_send_message()
    _repo_mock.reset_mock()
    _ec_mock.reset_mock()

    # repo.get_trades_by_symbol returns list of dicts → DataFrame
    _repo_mock.get_trades_by_symbol.return_value = [{"trade_id": "T1", "symbol": symbol}]

    # ec.get_open_positions_campaign returns df with a single position
    if positions_df is None:
        positions_df = pd.DataFrame([_make_position()])
    _ec_mock.get_open_positions_campaign.return_value = {
        "ok": True, "data": positions_df
    }
    _ec_mock.get_live_price.return_value = live_price
    _ec_mock.get_cached_history.return_value = pd.DataFrame()
    _ec_mock.get_sector_bundle.return_value = {"sector_etf": "XLK"}

    if engine_data is None:
        engine_data = {
            "status": "✅ פעיל",
            "sizing_status": "✅ תקין",
            "issues": [],
            "features": {
                "dist_12d": 2, "accum_10d": 5,
                "good_closes_10": 7, "bad_closes_10": 3,
                "rs20_market": 0.05, "rs20_stock_sector": 0.02,
                "atr_regime": 1.0, "stretch_ma20_atr": 1.5,
            },
        }
    _ec_mock.evaluate_position_engine.return_value = {
        "ok": engine_ok,
        "data": engine_data,
        "error": "test-error" if not engine_ok else "",
    }

    with patch.object(tp, 'bot', _fake_bot), \
         patch.object(tp, 'supabase', _fake_sb), \
         patch.object(tp, 'repo', _repo_mock), \
         patch.object(tp, 'ec', _ec_mock), \
         patch.object(tp, 'get_account_settings',
                       lambda: {"total_deposited": 10000.0, "risk_pct_input": 0.5}), \
         patch.object(tp, 'get_nav_and_risk',
                       lambda s=None: (10000.0, 50.0, None)):
        tp.handle_drilldown(chat_id, symbol)


# ── Basic execution ────────────────────────────────────────────────────────────

class TestHandleDrilldownExecution:
    def test_sends_loading_message_first(self):
        _run(1001, "AAPL")
        first_call = _fake_bot.send_message.call_args_list[0][0]
        assert first_call[0] == 1001
        assert "Drill-down" in first_call[1] or "רנטגן" in first_call[1]

    def test_calls_get_trades_by_symbol(self):
        _run(1001, "AAPL")
        _repo_mock.get_trades_by_symbol.assert_called_once()
        assert _repo_mock.get_trades_by_symbol.call_args[0][1] == "AAPL"

    def test_edits_message_with_report(self):
        _run(1001, "AAPL")
        _fake_bot.edit_message_text.assert_called_once()
        text = _fake_bot.edit_message_text.call_args[0][0]
        assert "AAPL" in text
        assert "Drill-down" in text or "מודיעין" in text


# ── No positions ───────────────────────────────────────────────────────────────

class TestNoOpenPositions:
    def test_empty_data_shows_error(self):
        empty_df = pd.DataFrame()
        _fake_bot.reset_mock()
        _setup_send_message()
        _repo_mock.get_trades_by_symbol.return_value = []
        _ec_mock.get_open_positions_campaign.return_value = {
            "ok": True, "data": empty_df
        }
        with patch.object(tp, 'bot', _fake_bot), \
             patch.object(tp, 'supabase', _fake_sb), \
             patch.object(tp, 'repo', _repo_mock), \
             patch.object(tp, 'ec', _ec_mock):
            tp.handle_drilldown(1001, "ZZZ")
        text = _fake_bot.edit_message_text.call_args[0][0]
        assert "לא נמצאו" in text or "ZZZ" in text

    def test_engine_returns_not_ok(self):
        _fake_bot.reset_mock()
        _setup_send_message()
        _repo_mock.get_trades_by_symbol.return_value = []
        _ec_mock.get_open_positions_campaign.return_value = {
            "ok": False, "data": pd.DataFrame(), "error": "fail"
        }
        with patch.object(tp, 'bot', _fake_bot), \
             patch.object(tp, 'supabase', _fake_sb), \
             patch.object(tp, 'repo', _repo_mock), \
             patch.object(tp, 'ec', _ec_mock):
            tp.handle_drilldown(1001, "ZZZ")
        text = _fake_bot.edit_message_text.call_args[0][0]
        assert "לא נמצאו" in text


# ── Engine error ───────────────────────────────────────────────────────────────

class TestEngineError:
    def test_engine_error_returns_error_message(self):
        _run(1001, "ERR", engine_ok=False, engine_data={})
        text = _fake_bot.edit_message_text.call_args[0][0]
        assert "שגיאה" in text or "ERR" in text


# ── Report content checks ──────────────────────────────────────────────────────

class TestReportContent:
    def test_report_contains_symbol(self):
        _run(1001, "TSLA")
        text = _fake_bot.edit_message_text.call_args[0][0]
        assert "TSLA" in text

    def test_report_contains_technical_profile(self):
        _run(1001, "AAPL")
        text = _fake_bot.edit_message_text.call_args[0][0]
        assert "פרופיל טכני" in text

    def test_report_contains_rs_section(self):
        _run(1001, "AAPL")
        text = _fake_bot.edit_message_text.call_args[0][0]
        assert "כוח יחסי" in text or "Relative Strength" in text

    def test_report_contains_volatility_regime(self):
        _run(1001, "AAPL")
        text = _fake_bot.edit_message_text.call_args[0][0]
        assert "תנודתיות" in text or "Volatility" in text

    def test_algo_skips_sizing_warning(self):
        positions_df = pd.DataFrame([_make_position(setup_type='ALGO')])
        _run(1001, "ALGO_SYM", positions_df=positions_df, engine_data={
            "status": "✅ פעיל", "sizing_status": "⚠️ חריגה",
            "issues": [], "features": {},
        })
        text = _fake_bot.edit_message_text.call_args[0][0]
        # ALGO position should not show campaign risk warning
        assert "סטטוס סיכון" not in text


# ── Sector bundle integration ──────────────────────────────────────────────────

class TestSectorIntegration:
    def test_sector_etf_appears_in_report_when_present(self):
        _run(1001, "AAPL", engine_data={
            "status": "✅",
            "sizing_status": "✅ תקין",
            "issues": [],
            "features": {"rs20_stock_sector": 0.03, "rs20_market": 0.01},
        })
        text = _fake_bot.edit_message_text.call_args[0][0]
        # XLK is the mocked sector_etf
        assert "XLK" in text


# ── Live price fallback ────────────────────────────────────────────────────────

class TestLivePriceFallback:
    def test_no_live_price_falls_back_to_entry(self):
        # When ec.get_live_price returns None, function should use entry price
        # and still complete without raising
        _run(1001, "AAPL", live_price=None)
        _fake_bot.edit_message_text.assert_called()


# ── handle_market_regime ───────────────────────────────────────────────────────

_tf_mock  = MagicMock()
_are_mock = MagicMock()


def _run_regime(chat_id, *, open_positions=None, regime=None, nav_stale=None,
                trades=None):
    """Run handle_market_regime with all deps patched."""
    _fake_bot.reset_mock()
    _setup_send_message()
    _repo_mock.reset_mock()
    _ec_mock.reset_mock()
    _tf_mock.reset_mock()
    _are_mock.reset_mock()

    _repo_mock.get_all_trades.return_value = trades or []
    if open_positions is None:
        open_positions = pd.DataFrame()
    _ec_mock.get_open_positions_campaign.return_value = {
        "ok": True, "data": open_positions
    }
    _ec_mock.compute_market_regime.return_value = regime or {"ok": True, "data": {"status": "neutral"}}
    _ec_mock.get_cached_history.return_value = pd.DataFrame()
    _ec_mock.get_live_price.return_value = 100.0
    _tf_mock.fmt_regime_report.return_value = "REGIME_REPORT"
    _tf_mock.fmt_adaptive_risk_block.return_value = ""
    _are_mock.compute_closed_campaigns.return_value = []
    _are_mock.compute_adaptive_risk.return_value = {"action": "hold"}

    with patch.object(tp, 'bot', _fake_bot), \
         patch.object(tp, 'supabase', _fake_sb), \
         patch.object(tp, 'repo', _repo_mock), \
         patch.object(tp, 'ec', _ec_mock), \
         patch.object(tp, 'tf', _tf_mock), \
         patch.object(tp, 'are', _are_mock), \
         patch.object(tp, 'get_account_settings',
                       lambda: {"total_deposited": 10000.0, "risk_pct_input": 0.5}), \
         patch.object(tp, 'get_nav_and_risk',
                       lambda s=None: (10000.0, 50.0, nav_stale)):
        tp.handle_market_regime(chat_id)


class TestHandleMarketRegime:
    def test_sends_loading_message(self):
        _run_regime(2001)
        first_call = _fake_bot.send_message.call_args_list[0][0]
        assert "דופק שוק" in first_call[1]

    def test_calls_compute_market_regime(self):
        _run_regime(2001)
        _ec_mock.compute_market_regime.assert_called()

    def test_edits_message_with_regime_report(self):
        _run_regime(2001)
        _fake_bot.edit_message_text.assert_called_once()
        text = _fake_bot.edit_message_text.call_args[0][0]
        assert "REGIME_REPORT" in text

    def test_nav_stale_label_appended(self):
        _run_regime(2001, nav_stale="⚠️ NAV ישן")
        text = _fake_bot.edit_message_text.call_args[0][0]
        assert "NAV ישן" in text

    def test_exposure_breakdown_passes_to_formatter(self):
        # _ec_mock.get_live_price returns 100.0 → curr=100 for both rows
        positions = pd.DataFrame([
            {"symbol": "AAA", "setup_type": "VCP", "price": 100, "quantity": 10},
            {"symbol": "BBB", "setup_type": "ALGO", "price": 50, "quantity": 20},
        ])
        _run_regime(2001, open_positions=positions)
        # fmt_regime_report receives (regime, total_pct, algo, vcp, ep, acc_size)
        args = _tf_mock.fmt_regime_report.call_args[0]
        assert args[2] == 100 * 20  # ALGO exposure (curr=100, qty=20)
        assert args[3] == 100 * 10  # VCP exposure (curr=100, qty=10)


# ── handle_portfolio_room ──────────────────────────────────────────────────────

def _run_room(chat_id, *, open_positions=None, repo_error=False):
    """Run handle_portfolio_room with all deps patched."""
    _fake_bot.reset_mock()
    _setup_send_message()
    _repo_mock.reset_mock()
    _ec_mock.reset_mock()
    _tf_mock.reset_mock()
    _are_mock.reset_mock()

    _repo_mock.get_all_trades.return_value = []
    _repo_mock.get_campaigns_pnl.return_value = []

    if repo_error:
        _ec_mock.get_open_positions_campaign.return_value = {
            "ok": False, "data": pd.DataFrame(), "error": "infra-fail"
        }
    else:
        if open_positions is None:
            open_positions = pd.DataFrame()
        _ec_mock.get_open_positions_campaign.return_value = {
            "ok": True, "data": open_positions
        }

    _ec_mock.get_cached_history.return_value = pd.DataFrame()
    _ec_mock.get_live_price.return_value = 105.0
    _ec_mock.compute_market_regime.return_value = {"ok": True, "data": {"status": "neutral"}}
    _ec_mock.evaluate_position_engine.return_value = {
        "ok": True, "data": {
            "status": "✅", "action": "hold", "trigger": "",
            "sizing_status": "✅ תקין", "issues": [],
            "score": 80, "stage": "stage2", "suggested_stop": 95.0,
            "features": {},
        }
    }
    _ec_mock.generate_minervini_coaching.return_value = []
    _tf_mock.fmt_position_card.return_value = "POSITION_CARD"
    _tf_mock.fmt_adaptive_risk_block.return_value = ""
    _are_mock.compute_closed_campaigns.return_value = []
    _are_mock.compute_adaptive_risk.return_value = {"action": "hold"}

    fake_state = {}
    with patch.object(tp, 'bot', _fake_bot), \
         patch.object(tp, 'supabase', _fake_sb), \
         patch.object(tp, 'user_state', fake_state), \
         patch.object(tp, 'repo', _repo_mock), \
         patch.object(tp, 'ec', _ec_mock), \
         patch.object(tp, 'tf', _tf_mock), \
         patch.object(tp, 'are', _are_mock), \
         patch.object(tp, 'get_account_settings',
                       lambda: {"total_deposited": 10000.0, "risk_pct_input": 0.5}), \
         patch.object(tp, 'get_nav_and_risk',
                       lambda s=None: (10000.0, 50.0, None)):
        tp.handle_portfolio_room(chat_id)
    return fake_state


class TestHandlePortfolioRoom:
    def test_sends_loading_message(self):
        _run_room(3001)
        first_call = _fake_bot.send_message.call_args_list[0][0]
        assert "שואב" in first_call[1] or "מרכיב" in first_call[1]

    def test_empty_positions_shows_message(self):
        _run_room(3001, open_positions=pd.DataFrame())
        last_call = _fake_bot.send_message.call_args_list[-1][0]
        assert "אין פוזיציות" in last_call[1]

    def test_repo_error_shows_infrastructure_error(self):
        _run_room(3001, repo_error=True)
        last_call = _fake_bot.send_message.call_args_list[-1][0]
        assert "תשתית" in last_call[1] or "שגיאת" in last_call[1]

    def test_stores_positions_in_user_state(self):
        positions = pd.DataFrame([{
            "symbol": "AAA", "setup_type": "VCP", "price": 100, "quantity": 10,
            "stop_loss": 95, "initial_stop": 90, "entry_date": "2025-01-01",
            "management_state": "full_position",
        }])
        state = _run_room(3001, open_positions=positions)
        assert 3001 in state
        assert "temp_positions" in state[3001]
        assert len(state[3001]["temp_positions"]) == 1

    def test_algo_position_uses_oversight_language(self):
        positions = pd.DataFrame([{
            "symbol": "ALG", "setup_type": "ALGO", "price": 50, "quantity": 20,
            "stop_loss": 45, "initial_stop": 40, "entry_date": "2025-01-01",
            "management_state": "full_position",
        }])
        _run_room(3001, open_positions=positions)
        # Find the long-message send call (last send_message that's not the loading one)
        all_sends = [c[0][1] for c in _fake_bot.send_message.call_args_list]
        full_msg = "\n".join(all_sends)
        assert "מנוהל חיצונית" in full_msg or "Sentinel אינה מנהלת יציאות" in full_msg
