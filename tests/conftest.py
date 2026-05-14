"""
Shared pytest fixtures for Sentinel Trading test suite.

Provides reusable mocks for external dependencies (Supabase, yfinance)
and sample data structures used across multiple test modules.

# Network isolation (Sprint 7, post-Meeting-7 incident)

`pytest-socket` blocks all socket calls by default. Any test that
silently relied on a real yfinance/Supabase/Telegram fetch will now
fail loudly with `SocketBlockedError` instead of returning whatever
the network happened to send back.

The Sprint 6 CI incident traced to exactly this gap:
test_returns_none_when_history_empty passed an empty DataFrame and
expected None, but the production code fell through to a real
yfinance fetch — invisible in sandboxed local runs, fatal in CI.

If a test legitimately needs the loopback interface, decorate with
`@pytest.mark.enable_socket` (provided by pytest-socket). No test
should ever talk to a public host.

# Marker auto-tagging (Sprint 8 #4)

`pytest.ini` declares three markers (unit / integration / slow) but they
were never applied to the existing 1258 tests — `pytest -m unit` returned
zero results. Chris (QA) flagged this in Meeting 8.

Rather than touching every one of the 42 test files, the
`pytest_collection_modifyitems` hook below tags every collected test by
filename. Files explicitly marked already keep their marker; everything
else falls through to a sensible default.

Run the slices:
    pytest -m unit             # pure math, fastest
    pytest -m integration      # cross-module flows with mocks
    pytest -m slow             # heavy I/O or chart generation
    pytest -m "not slow"       # CI-default — excludes the slow tier
"""
import sys
import types
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch
from pytest_socket import disable_socket


def pytest_runtest_setup():
    """Disable network sockets before every test (pytest-socket hook).

    Tests that need a local socket (e.g. an in-process HTTP server)
    can opt in with `@pytest.mark.enable_socket`. No exemptions for
    public hosts — that's the whole point.
    """
    disable_socket()


# ── Marker auto-tagging by filename (Sprint 8 #4) ─────────────────────────────

# Files that exercise cross-module flows or patch heavy deps (supabase mocks,
# bot fixtures, multi-module wiring). These need the integration tier.
_INTEGRATION_FILES = frozenset({
    "test_e2e_risk_monitor.py",
    "test_integration.py",
    "test_bot_health.py",
    "test_developer_menu.py",
    "test_healthcheck.py",
    "test_secure_runner.py",
    "test_telegram_portfolio.py",
    "test_telegram_backlog.py",
    "test_supabase_repository.py",
    "test_audit_logger.py",
    "test_phase3_state_alerts.py",
    "test_phase4_algo_oversight.py",
    "test_phase5_anti_spam.py",
    "test_phase6_context_export.py",
    "test_dev_pin_persistence.py",
})

# Files that take noticeable time or do heavy I/O — chart generation,
# IBKR sync end-to-end. Excluded from CI default with `-m "not slow"`.
_SLOW_FILES = frozenset({
    "test_ibkr_sync_full.py",
    "test_ibkr_trade_importer.py",
    "test_ibkr_error_handling.py",
    "test_chart_generator.py",
    "test_report_scheduler.py",
})


def pytest_collection_modifyitems(config, items):
    """Auto-apply marker to every collected test based on its filename.

    Tests with an explicit marker on the function/class keep it — this hook
    only fills in the gap for files that never declared one.
    """
    for item in items:
        # Respect any explicit marker the test/class already declares
        existing = {m.name for m in item.iter_markers()}
        if {"unit", "integration", "slow"} & existing:
            continue
        fname = item.fspath.basename
        if fname in _INTEGRATION_FILES:
            item.add_marker(pytest.mark.integration)
        elif fname in _SLOW_FILES:
            item.add_marker(pytest.mark.slow)
        else:
            item.add_marker(pytest.mark.unit)


@pytest.fixture
def mock_supabase():
    """Supabase client mock — table().select().execute() returns empty data by default."""
    sb = MagicMock()
    sb.table.return_value.select.return_value.execute.return_value.data = []
    return sb


@pytest.fixture
def mock_yfinance():
    """yfinance Ticker mock returning a minimal one-bar OHLCV DataFrame."""
    with patch("yfinance.Ticker") as mock_ticker:
        df = pd.DataFrame(
            {
                "Open":   [100.0],
                "High":   [101.0],
                "Low":    [99.0],
                "Close":  [100.5],
                "Volume": [1_000_000],
            },
            index=pd.bdate_range("2026-01-02", periods=1),
        )
        mock_ticker.return_value.history.return_value = df
        yield mock_ticker


@pytest.fixture
def sample_open_positions():
    """One manual LONG position with all required fields populated."""
    return [
        {
            "symbol":          "AAPL",
            "side":            "LONG",
            "entry_price":     150.0,
            "initial_stop":    142.0,
            "quantity":        100,
            "current_price":   158.0,
            "management_mode": "MANUAL",
            "campaign_id":     "test-campaign-001",
        },
    ]


@pytest.fixture
def sample_closed_campaigns():
    """One winning and one losing closed campaign."""
    return [
        {
            "symbol":      "MSFT",
            "is_win":      True,
            "total_pnl_usd": 500.0,
            "r_multiple":  2.5,
            "close_date":  "2026-04-01",
        },
        {
            "symbol":      "TSLA",
            "is_win":      False,
            "total_pnl_usd": -200.0,
            "r_multiple":  -1.0,
            "close_date":  "2026-04-10",
        },
    ]


@pytest.fixture
def mock_telegram_bot(monkeypatch):
    """
    Capture all messages sent via risk_monitor.send_telegram / send_telegram_with_keyboard.

    Yields a list that accumulates message strings as the test runs.

    Usage:
        def test_foo(mock_telegram_bot):
            trigger_something()
            assert "expected phrase" in mock_telegram_bot[0]
    """
    # Ensure heavy deps are stubbed before risk_monitor is referenced
    for _mod in ("telebot", "supabase", "dotenv"):
        if _mod not in sys.modules:
            sys.modules[_mod] = types.ModuleType(_mod)
    if not getattr(sys.modules["supabase"], "create_client", None):
        sys.modules["supabase"].create_client = lambda *a, **k: None
    if not getattr(sys.modules["dotenv"], "load_dotenv", None):
        sys.modules["dotenv"].load_dotenv = lambda *a, **k: None
    if not getattr(sys.modules["telebot"], "TeleBot", None):
        sys.modules["telebot"].TeleBot = type("TeleBot", (), {"__init__": lambda *a, **k: None})

    import risk_monitor as rm

    sent: list = []
    monkeypatch.setattr(rm, "send_telegram", lambda msg: sent.append(msg))
    monkeypatch.setattr(rm, "send_telegram_with_keyboard", lambda msg, kb: sent.append(msg))
    return sent
