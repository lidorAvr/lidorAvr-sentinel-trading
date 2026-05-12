"""
Tests for ibkr_trade_importer.py — XML parsing + new-trade import logic.

No network, no actual Supabase — uses a MagicMock client.
"""
import sys, os, types as py_types
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _mod in ("telebot", "telebot.types", "supabase", "dotenv",
             "adaptive_risk_engine", "engine_core", "telegram_formatters"):
    sys.modules.setdefault(_mod, MagicMock())

import ibkr_trade_importer as imp


# ── Sample XML matching production format ─────────────────────────────────────

_SAMPLE_XML = """\
<FlexQueryResponse queryName="Sentinel_Trades" type="AF">
<FlexStatements count="1">
<FlexStatement accountId="U17457096" fromDate="20260504" toDate="20260508">
<Trades>
<Trade assetCategory="STK" symbol="HOOD" tradeID="9449697599" tradeDate="20260506"
       quantity="4" tradePrice="78.89" ibCommission="-2.5" fifoPnlRealized="0"
       buySell="BUY" orderTime="20260506;153011" />
<Trade assetCategory="STK" symbol="HOOD" tradeID="9459447495" tradeDate="20260507"
       quantity="-4" tradePrice="75.585" ibCommission="-2.5" fifoPnlRealized="-18.22"
       buySell="SELL" orderTime="20260507;153026" />
<Trade assetCategory="STK" symbol="JPM" tradeID="9428022411" tradeDate="20260504"
       quantity="-1" tradePrice="308.47" ibCommission="-2.5" fifoPnlRealized="-9.175"
       buySell="SELL" orderTime="20260504;110022" />
</Trades>
</FlexStatement>
</FlexStatements>
</FlexQueryResponse>
"""


# ── parse_trades_from_xml ─────────────────────────────────────────────────────

class TestParseTradesFromXml:
    def test_parses_all_three_trades(self):
        result = imp.parse_trades_from_xml(_SAMPLE_XML)
        assert len(result) == 3

    def test_trade_id_is_string(self):
        result = imp.parse_trades_from_xml(_SAMPLE_XML)
        assert all(isinstance(t["trade_id"], str) for t in result)
        assert result[0]["trade_id"] == "9449697599"

    def test_buy_side_uppercase(self):
        result = imp.parse_trades_from_xml(_SAMPLE_XML)
        hood_buy = next(t for t in result if t["trade_id"] == "9449697599")
        assert hood_buy["side"] == "BUY"

    def test_sell_side_uppercase(self):
        result = imp.parse_trades_from_xml(_SAMPLE_XML)
        hood_sell = next(t for t in result if t["trade_id"] == "9459447495")
        assert hood_sell["side"] == "SELL"

    def test_quantity_always_positive(self):
        result = imp.parse_trades_from_xml(_SAMPLE_XML)
        sells = [t for t in result if t["side"] == "SELL"]
        assert all(t["quantity"] > 0 for t in sells)

    def test_buy_quantity_value(self):
        result = imp.parse_trades_from_xml(_SAMPLE_XML)
        hood_buy = next(t for t in result if t["trade_id"] == "9449697599")
        assert hood_buy["quantity"] == 4

    def test_sell_quantity_abs(self):
        result = imp.parse_trades_from_xml(_SAMPLE_XML)
        hood_sell = next(t for t in result if t["trade_id"] == "9459447495")
        assert hood_sell["quantity"] == 4  # XML had "-4", we want absolute

    def test_price_is_float(self):
        result = imp.parse_trades_from_xml(_SAMPLE_XML)
        assert result[0]["price"] == 78.89

    def test_date_iso_format(self):
        result = imp.parse_trades_from_xml(_SAMPLE_XML)
        hood_buy = next(t for t in result if t["trade_id"] == "9449697599")
        assert hood_buy["trade_date"] == "2026-05-06"

    def test_pnl_zero_for_buy(self):
        result = imp.parse_trades_from_xml(_SAMPLE_XML)
        hood_buy = next(t for t in result if t["trade_id"] == "9449697599")
        assert hood_buy["pnl_usd"] == 0

    def test_pnl_nonzero_for_sell(self):
        result = imp.parse_trades_from_xml(_SAMPLE_XML)
        hood_sell = next(t for t in result if t["trade_id"] == "9459447495")
        assert hood_sell["pnl_usd"] == -18.22

    def test_symbol_preserved(self):
        result = imp.parse_trades_from_xml(_SAMPLE_XML)
        assert {t["symbol"] for t in result} == {"HOOD", "JPM"}


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestParseEdgeCases:
    def test_empty_string(self):
        assert imp.parse_trades_from_xml("") == []

    def test_malformed_xml(self):
        assert imp.parse_trades_from_xml("<not-valid<xml") == []

    def test_no_trades_element(self):
        xml = "<FlexQueryResponse><FlexStatement /></FlexQueryResponse>"
        assert imp.parse_trades_from_xml(xml) == []

    def test_trade_missing_id_skipped(self):
        xml = """<FlexQueryResponse><Trade symbol="X" buySell="BUY"
                  quantity="1" tradePrice="10" tradeDate="20260506" /></FlexQueryResponse>"""
        result = imp.parse_trades_from_xml(xml)
        assert result == []

    def test_trade_missing_side_skipped(self):
        xml = """<FlexQueryResponse><Trade tradeID="T1" symbol="X"
                  quantity="1" tradePrice="10" tradeDate="20260506" /></FlexQueryResponse>"""
        assert imp.parse_trades_from_xml(xml) == []

    def test_trade_unknown_side_skipped(self):
        xml = """<FlexQueryResponse><Trade tradeID="T1" symbol="X" buySell="HOLD"
                  quantity="1" tradePrice="10" tradeDate="20260506" /></FlexQueryResponse>"""
        assert imp.parse_trades_from_xml(xml) == []

    def test_trade_bad_date_skipped(self):
        xml = """<FlexQueryResponse><Trade tradeID="T1" symbol="X" buySell="BUY"
                  quantity="1" tradePrice="10" tradeDate="2026-05-06" /></FlexQueryResponse>"""
        assert imp.parse_trades_from_xml(xml) == []

    def test_trade_zero_quantity_skipped(self):
        xml = """<FlexQueryResponse><Trade tradeID="T1" symbol="X" buySell="BUY"
                  quantity="0" tradePrice="10" tradeDate="20260506" /></FlexQueryResponse>"""
        assert imp.parse_trades_from_xml(xml) == []

    def test_trade_negative_price_skipped(self):
        xml = """<FlexQueryResponse><Trade tradeID="T1" symbol="X" buySell="BUY"
                  quantity="1" tradePrice="-5" tradeDate="20260506" /></FlexQueryResponse>"""
        assert imp.parse_trades_from_xml(xml) == []

    def test_one_bad_one_good(self):
        xml = """<FlexQueryResponse>
                  <Trade tradeID="" symbol="BAD" buySell="BUY"
                         quantity="1" tradePrice="10" tradeDate="20260506" />
                  <Trade tradeID="GOOD1" symbol="OK" buySell="BUY"
                         quantity="2" tradePrice="20" tradeDate="20260507" />
                  </FlexQueryResponse>"""
        result = imp.parse_trades_from_xml(xml)
        assert len(result) == 1
        assert result[0]["trade_id"] == "GOOD1"


# ── import_new_trades ─────────────────────────────────────────────────────────

class _FakeRepo:
    """Minimal in-memory stand-in for supabase_repository."""
    def __init__(self, existing_ids=None):
        self.existing = set(existing_ids or [])
        self.inserted = []

    def get_existing_trade_ids(self, sb):
        return set(self.existing)

    def insert_trades(self, sb, trades):
        self.inserted.extend(trades)
        return len(trades)


def _patched_repo(existing_ids=None):
    return _FakeRepo(existing_ids)


class TestImportNewTrades:
    def test_inserts_all_when_supabase_empty(self):
        fake = _patched_repo([])
        with patch.object(imp, 'repo', fake):
            result = imp.import_new_trades(MagicMock(), _SAMPLE_XML)
        assert result["new_count"] == 3
        assert len(fake.inserted) == 3
        assert result["ok"] is True

    def test_inserts_only_missing_when_one_exists(self):
        fake = _patched_repo(["9449697599"])  # HOOD BUY already there
        with patch.object(imp, 'repo', fake):
            result = imp.import_new_trades(MagicMock(), _SAMPLE_XML)
        assert result["new_count"] == 2
        assert "9449697599" not in {t["trade_id"] for t in result["new_trades"]}

    def test_inserts_nothing_when_all_exist(self):
        fake = _patched_repo(["9449697599", "9459447495", "9428022411"])
        with patch.object(imp, 'repo', fake):
            result = imp.import_new_trades(MagicMock(), _SAMPLE_XML)
        assert result["new_count"] == 0
        assert fake.inserted == []

    def test_empty_xml_returns_zero(self):
        fake = _patched_repo([])
        with patch.object(imp, 'repo', fake):
            result = imp.import_new_trades(MagicMock(), "")
        assert result["new_count"] == 0
        assert result["ok"] is False  # XML didn't parse

    def test_total_in_xml_tracked(self):
        fake = _patched_repo([])
        with patch.object(imp, 'repo', fake):
            result = imp.import_new_trades(MagicMock(), _SAMPLE_XML)
        assert result["total_in_xml"] == 3

    def test_supabase_error_during_select_treated_as_empty(self):
        broken = MagicMock()
        broken.get_existing_trade_ids.side_effect = Exception("DB down")
        broken.insert_trades.return_value = 3
        with patch.object(imp, 'repo', broken):
            # Should still attempt insert when select fails
            result = imp.import_new_trades(MagicMock(), _SAMPLE_XML)
        assert result["new_count"] == 3  # tried to insert all

    def test_insert_error_returns_ok_false(self):
        broken = MagicMock()
        broken.get_existing_trade_ids.return_value = set()
        broken.insert_trades.side_effect = Exception("constraint violation")
        with patch.object(imp, 'repo', broken):
            result = imp.import_new_trades(MagicMock(), _SAMPLE_XML)
        assert result["ok"] is False
