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
