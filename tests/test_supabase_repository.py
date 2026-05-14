"""
Tests for supabase_repository.py — pure data-access layer.

Uses a mock Supabase client. Tests verify that each function:
  1. Calls the right table/method/filter chain.
  2. Returns empty list when .data is None or [].
"""
import sys, os
import pytest
from unittest.mock import MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import supabase_repository as repo


def _sb():
    """Return a MagicMock supabase client with chained methods."""
    sb = MagicMock()
    # Chain: .table().select().execute().data
    sb.table.return_value = sb
    sb.select.return_value = sb
    sb.eq.return_value = sb
    sb.lt.return_value = sb
    sb.or_.return_value = sb
    sb.order.return_value = sb
    sb.limit.return_value = sb
    sb.update.return_value = sb
    sb.execute.return_value.data = [{"trade_id": "T1", "symbol": "MRVL"}]
    return sb


# ── get_all_trades ─────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetAllTrades:
    def test_calls_trades_table(self):
        sb = _sb()
        repo.get_all_trades(sb)
        sb.table.assert_called_with("trades")

    def test_calls_select_star(self):
        sb = _sb()
        repo.get_all_trades(sb)
        sb.select.assert_called_with("*")

    def test_returns_data_list(self):
        sb = _sb()
        result = repo.get_all_trades(sb)
        assert result == [{"trade_id": "T1", "symbol": "MRVL"}]

    def test_returns_empty_list_when_none(self):
        sb = _sb()
        sb.execute.return_value.data = None
        assert repo.get_all_trades(sb) == []


# ── get_trades_by_symbol ───────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetTradesBySymbol:
    def test_filters_by_symbol(self):
        sb = _sb()
        repo.get_trades_by_symbol(sb, "MRVL")
        sb.eq.assert_called_with("symbol", "MRVL")

    def test_returns_empty_list_when_none(self):
        sb = _sb()
        sb.execute.return_value.data = None
        assert repo.get_trades_by_symbol(sb, "QQQ") == []


# ── get_incomplete_trades ──────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetIncompleteTrades:
    def test_calls_or_with_query(self):
        sb = _sb()
        repo.get_incomplete_trades(sb)
        assert sb.or_.called
        args = sb.or_.call_args[0][0]
        assert "setup_type.is.null" in args
        assert "side.eq.BUY" in args

    def test_applies_limit_100_by_default(self):
        sb = _sb()
        repo.get_incomplete_trades(sb)
        sb.limit.assert_called_with(100)

    def test_custom_limit(self):
        sb = _sb()
        repo.get_incomplete_trades(sb, limit=20)
        sb.limit.assert_called_with(20)

    def test_returns_empty_list_when_none(self):
        sb = _sb()
        sb.execute.return_value.data = None
        assert repo.get_incomplete_trades(sb) == []


# ── get_earlier_buys_for_campaign ─────────────────────────────────────────────

@pytest.mark.unit
class TestGetEarlierBuysForCampaign:
    def test_filters_campaign_id(self):
        sb = _sb()
        repo.get_earlier_buys_for_campaign(sb, "C1", "2024-01-01")
        calls = [str(c) for c in sb.eq.call_args_list]
        assert any("C1" in c for c in calls)

    def test_filters_side_buy(self):
        sb = _sb()
        repo.get_earlier_buys_for_campaign(sb, "C1", "2024-01-01")
        calls = [str(c) for c in sb.eq.call_args_list]
        assert any("BUY" in c for c in calls)

    def test_filters_before_date(self):
        sb = _sb()
        repo.get_earlier_buys_for_campaign(sb, "C1", "2024-06-15")
        sb.lt.assert_called_with("trade_date", "2024-06-15")

    def test_returns_empty_list_when_none(self):
        sb = _sb()
        sb.execute.return_value.data = None
        assert repo.get_earlier_buys_for_campaign(sb, "C1", "2024-01-01") == []


# ── get_old_trades ─────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetOldTrades:
    def test_filters_by_date(self):
        sb = _sb()
        repo.get_old_trades(sb, "2024-01-01")
        sb.lt.assert_called_with("trade_date", "2024-01-01")

    def test_returns_empty_list_when_none(self):
        sb = _sb()
        sb.execute.return_value.data = None
        assert repo.get_old_trades(sb, "2024-01-01") == []


# ── get_campaigns_pnl ─────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGetCampaignsPnl:
    def test_selects_correct_columns(self):
        sb = _sb()
        repo.get_campaigns_pnl(sb)
        sb.select.assert_called_with("campaign_id,pnl_usd,trade_date")

    def test_returns_empty_list_when_none(self):
        sb = _sb()
        sb.execute.return_value.data = None
        assert repo.get_campaigns_pnl(sb) == []


# ── update_trade ───────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestUpdateTrade:
    def test_calls_update_with_fields(self):
        sb = _sb()
        repo.update_trade(sb, "T123", {"quality": 8})
        sb.update.assert_called_with({"quality": 8})

    def test_filters_by_trade_id(self):
        sb = _sb()
        repo.update_trade(sb, "T123", {"quality": 8})
        sb.eq.assert_called_with("trade_id", "T123")


# ── update_stop_for_campaign ───────────────────────────────────────────────────

@pytest.mark.unit
class TestUpdateStopForCampaign:
    def test_updates_stop_loss(self):
        sb = _sb()
        repo.update_stop_for_campaign(sb, "C1", 150.5)
        sb.update.assert_called_with({"stop_loss": 150.5})

    def test_filters_campaign_and_side(self):
        sb = _sb()
        repo.update_stop_for_campaign(sb, "C1", 150.5)
        calls = [str(c) for c in sb.eq.call_args_list]
        assert any("C1" in c for c in calls)
        assert any("BUY" in c for c in calls)


# ── update_management_notes ───────────────────────────────────────────────────

@pytest.mark.unit
class TestUpdateManagementNotes:
    def test_updates_management_notes(self):
        sb = _sb()
        repo.update_management_notes(sb, "C1", "Runner: להחזיק")
        sb.update.assert_called_with({"management_notes": "Runner: להחזיק"})

    def test_filters_campaign_and_side(self):
        sb = _sb()
        repo.update_management_notes(sb, "C1", "note")
        calls = [str(c) for c in sb.eq.call_args_list]
        assert any("C1" in c for c in calls)
        assert any("BUY" in c for c in calls)


# ── get_open_campaign_for_symbol ───────────────────────────────────────────────

@pytest.mark.unit
class TestGetOpenCampaignForSymbol:
    """
    Sprint 6: closed-campaign filter.

    Convention (matches adaptive_risk_engine.compute_closed_campaigns):
      BUY  → quantity > 0
      SELL → quantity < 0
    Campaign is OPEN when net SUM(quantity) > 0.
    """

    def test_returns_open_campaign_when_net_qty_positive(self):
        sb = _sb()
        sb.execute.return_value.data = [
            {"campaign_id": "CID-OPEN", "quantity": 100, "trade_date": "2026-05-10"},
            {"campaign_id": "CID-OPEN", "quantity": -50, "trade_date": "2026-05-11"},
        ]
        assert repo.get_open_campaign_for_symbol(sb, "NVDA") == "CID-OPEN"

    def test_excludes_fully_closed_campaign(self):
        sb = _sb()
        sb.execute.return_value.data = [
            {"campaign_id": "CID-CLOSED", "quantity": 100, "trade_date": "2026-05-10"},
            {"campaign_id": "CID-CLOSED", "quantity": -100, "trade_date": "2026-05-12"},
        ]
        assert repo.get_open_campaign_for_symbol(sb, "NVDA") is None

    def test_returns_open_when_open_and_closed_coexist(self):
        sb = _sb()
        sb.execute.return_value.data = [
            # Closed campaign (older)
            {"campaign_id": "CID-OLD", "quantity": 50, "trade_date": "2026-04-01"},
            {"campaign_id": "CID-OLD", "quantity": -50, "trade_date": "2026-04-15"},
            # Open campaign (newer)
            {"campaign_id": "CID-NEW", "quantity": 80, "trade_date": "2026-05-01"},
        ]
        assert repo.get_open_campaign_for_symbol(sb, "NVDA") == "CID-NEW"

    def test_picks_most_recent_open_campaign(self):
        sb = _sb()
        sb.execute.return_value.data = [
            {"campaign_id": "CID-A", "quantity": 100, "trade_date": "2026-05-01"},
            {"campaign_id": "CID-B", "quantity": 100, "trade_date": "2026-05-08"},
        ]
        assert repo.get_open_campaign_for_symbol(sb, "NVDA") == "CID-B"

    def test_returns_none_when_no_data(self):
        sb = _sb()
        sb.execute.return_value.data = []
        assert repo.get_open_campaign_for_symbol(sb, "NVDA") is None

    def test_returns_none_when_data_is_none(self):
        sb = _sb()
        sb.execute.return_value.data = None
        assert repo.get_open_campaign_for_symbol(sb, "NVDA") is None

    def test_filters_by_symbol(self):
        sb = _sb()
        sb.execute.return_value.data = [
            {"campaign_id": "CID-X", "quantity": 50, "trade_date": "2026-05-01"},
        ]
        repo.get_open_campaign_for_symbol(sb, "MRVL")
        eq_calls = [str(c) for c in sb.eq.call_args_list]
        assert any("MRVL" in c for c in eq_calls)

    def test_ignores_rows_without_campaign_id(self):
        sb = _sb()
        sb.execute.return_value.data = [
            {"campaign_id": None, "quantity": 100, "trade_date": "2026-05-01"},
            {"campaign_id": "CID-VALID", "quantity": 50, "trade_date": "2026-05-02"},
        ]
        assert repo.get_open_campaign_for_symbol(sb, "NVDA") == "CID-VALID"

    def test_excludes_campaign_with_negative_net_qty(self):
        # Edge case: bookkeeping anomaly — more sold than bought (overshoot).
        # Should not be returned as "open".
        sb = _sb()
        sb.execute.return_value.data = [
            {"campaign_id": "CID-OVER", "quantity": 100, "trade_date": "2026-05-01"},
            {"campaign_id": "CID-OVER", "quantity": -120, "trade_date": "2026-05-05"},
        ]
        assert repo.get_open_campaign_for_symbol(sb, "NVDA") is None
