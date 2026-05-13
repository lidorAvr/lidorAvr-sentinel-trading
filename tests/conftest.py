"""
Shared pytest fixtures for Sentinel Trading test suite.

Provides reusable mocks for external dependencies (Supabase, yfinance)
and sample data structures used across multiple test modules.
"""
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch


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
