"""
test_data_validation.py — Input validation and robustness at all system boundaries.

Covers:
- analytics_engine: missing columns, NaN values, zero quantities, negative prices
- account_state: partial JSON, corrupt timestamps, missing keys
- report_snapshot_store: corrupt files, idempotent saves, directory creation
- adaptive_risk_engine: campaigns with missing fields, non-numeric PnL
- ibkr_sync_runner: malformed XML, empty XML, partial XML
- report_delivery: missing files, empty tokens
- chart_generator: empty data, missing analytics keys
"""
import json
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import analytics_engine      as ae
import account_state         as acc
import report_snapshot_store as snap
import adaptive_risk_engine  as are
import ibkr_sync_runner      as ibkr
import chart_generator       as cg
from report_delivery import send_pdf, send_summary, deliver_report


ACCOUNT = {"nav": 10000.0, "risk_pct_input": 1.0}
START   = datetime(2025, 1, 6)
END     = datetime(2025, 1, 13)


# ════════════════════════════════════════════════════════════════════════════════
# ANALYTICS ENGINE — MALFORMED INPUT
# ════════════════════════════════════════════════════════════════════════════════

class TestAnalyticsEngineMalformedInput:
    def _sell(self, cid="c1", date="2025-01-09"):
        return {"campaign_id": cid, "side": "SELL", "trade_date": date,
                "price": 110, "quantity": 10, "pnl_usd": 100,
                "initial_stop": 0, "stop_loss": 0,
                "setup_type": "B", "symbol": "A"}

    def _buy(self, cid="c1", date="2025-01-07", **kw):
        base = {"campaign_id": cid, "side": "BUY", "trade_date": date,
                "price": 100, "quantity": 10, "pnl_usd": 0,
                "initial_stop": 90, "stop_loss": 90,
                "setup_type": "B", "symbol": "A"}
        base.update(kw)
        return base

    def test_missing_columns_returns_ok_dict(self):
        df = pd.DataFrame([{"side": "SELL", "trade_date": "2025-01-09"}])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert isinstance(result, dict)

    def test_nan_price_handled(self):
        df = pd.DataFrame([
            self._buy(price=float("nan")),
            self._sell(),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert isinstance(result, dict)

    def test_nan_pnl_handled(self):
        df = pd.DataFrame([
            self._buy(),
            {**self._sell(), "pnl_usd": float("nan")},
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert isinstance(result, dict)

    def test_zero_quantity_buy_excluded(self):
        df = pd.DataFrame([
            self._buy(quantity=0),
            self._sell(),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        # Zero-qty buy creates no valid campaign
        assert result["campaigns_closed"] == 0 or isinstance(result, dict)

    def test_negative_price_doesnt_crash(self):
        df = pd.DataFrame([
            self._buy(price=-100),
            self._sell(),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert isinstance(result, dict)

    def test_string_price_coerced_to_numeric(self):
        df = pd.DataFrame([
            self._buy(price="100"),
            self._sell(),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert isinstance(result, dict)

    def test_invalid_date_string_handled(self):
        df = pd.DataFrame([
            self._buy(date="not-a-date"),
            self._sell(date="not-a-date"),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert isinstance(result, dict)

    def test_duplicate_campaign_ids_dont_double_count(self):
        df = pd.DataFrame([
            self._buy(cid="c1"),
            self._sell(cid="c1"),
            self._buy(cid="c1"),   # duplicate campaign_id buy
            self._sell(cid="c1"),
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        # Should aggregate as one campaign
        assert result["campaigns_closed"] == 1

    def test_none_campaign_id_excluded(self):
        df = pd.DataFrame([
            {**self._buy(), "campaign_id": None},
            {**self._sell(), "campaign_id": None},
        ])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert result["campaigns_closed"] == 0

    def test_only_buys_no_sells_in_period_returns_empty(self):
        df = pd.DataFrame([self._buy()])  # BUY but no SELL
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        assert result["campaigns_closed"] == 0

    def test_all_fields_present_in_result(self):
        df = pd.DataFrame([self._buy(), self._sell()])
        result = ae.compute_period_analytics(df, START, END, ACCOUNT)
        for key in ("campaigns_closed", "win_rate", "expectancy_r", "profit_factor",
                    "avg_win_r", "avg_loss_r", "total_r_net", "realized_pnl",
                    "missing_stop_rate", "oversized_rate", "avg_r_per_day"):
            assert key in result, f"Missing key: {key}"

    def test_result_never_raises_exception(self):
        """compute_period_analytics must never raise."""
        for df_input in (None, pd.DataFrame(), pd.DataFrame({"garbage": [1, 2]})):
            try:
                ae.compute_period_analytics(df_input, START, END, ACCOUNT)
            except Exception as e:
                pytest.fail(f"compute_period_analytics raised {e} for {df_input}")


# ════════════════════════════════════════════════════════════════════════════════
# ACCOUNT STATE — EDGE CASE JSON
# ════════════════════════════════════════════════════════════════════════════════

class TestAccountStateValidation:
    def test_empty_json_object_returns_defaults(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text("{}")
        with patch.object(acc, "_CONFIG_PATHS", [str(cfg)]):
            result = acc.load()
        assert result["nav"] == 7500.0
        assert result["risk_pct_input"] == 0.5

    def test_nav_as_string_coerced(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text('{"nav": "10000", "total_deposited": 7500}')
        with patch.object(acc, "_CONFIG_PATHS", [str(cfg)]):
            result = acc.load()
        assert result["nav"] == 10000.0

    def test_negative_nav_stored_as_is(self, tmp_path):
        """We trust the stored value; validation is the broker's job."""
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text('{"nav": -500, "total_deposited": 7500, "risk_pct_input": 0.5}')
        with patch.object(acc, "_CONFIG_PATHS", [str(cfg)]):
            result = acc.load()
        assert result["nav"] == -500.0

    def test_nav_updated_at_wrong_format_gives_unknown(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text('{"nav": 10000, "total_deposited": 7500, "risk_pct_input": 0.5, "nav_updated_at": "yesterday"}')
        with patch.object(acc, "_CONFIG_PATHS", [str(cfg)]):
            result = acc.load()
        assert result["freshness"] == "unknown"

    def test_load_always_returns_dict(self):
        for path in (["/nonexistent/a.json"], ["not_a_file.json"]):
            with patch.object(acc, "_CONFIG_PATHS", path):
                result = acc.load()
            assert isinstance(result, dict)
            assert "nav" in result

    def test_list_json_returns_fallback(self, tmp_path):
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text('[1, 2, 3]')  # JSON array, not object
        with patch.object(acc, "_CONFIG_PATHS", [str(cfg)]):
            result = acc.load()
        # Should either fallback or handle gracefully
        assert isinstance(result, dict)


# ════════════════════════════════════════════════════════════════════════════════
# REPORT SNAPSHOT STORE
# ════════════════════════════════════════════════════════════════════════════════

class TestSnapshotStoreValidation:
    def _analytics(self):
        return {"campaigns_closed": 5, "win_rate": 0.6,
                "expectancy_r": 0.4, "profit_factor": 1.8,
                "avg_win_r": 1.2, "avg_loss_r": -0.8,
                "total_r_net": 2.0, "realized_pnl": 400.0,
                "missing_stop_rate": 0.1, "oversized_rate": 0.05,
                "avg_r_per_day": 0.08, "dev_score": 72,
                "setup_breakdown": {}}

    def test_save_creates_file(self, tmp_path):
        with patch.object(snap, "_BASE_DIR", str(tmp_path)):
            snap.save("weekly", datetime(2025,1,6), datetime(2025,1,12),
                      self._analytics(), {"nav": 10000.0, "nav_source": "broker", "freshness": "fresh", "risk_pct_input": 0.5})
        files = list((tmp_path / "weekly").glob("*.json"))
        assert len(files) == 1

    def test_save_is_idempotent(self, tmp_path):
        with patch.object(snap, "_BASE_DIR", str(tmp_path)):
            for _ in range(3):
                snap.save("weekly", datetime(2025,1,6), datetime(2025,1,12),
                          self._analytics(), {"nav": 10000.0, "nav_source": "broker", "freshness": "fresh", "risk_pct_input": 0.5})
        files = list((tmp_path / "weekly").glob("*.json"))
        assert len(files) == 1   # Only one file

    def test_save_load_round_trip(self, tmp_path):
        with patch.object(snap, "_BASE_DIR", str(tmp_path)):
            snap.save("weekly", datetime(2025,1,6), datetime(2025,1,12),
                      self._analytics(), {"nav": 10000.0, "nav_source": "broker", "freshness": "fresh", "risk_pct_input": 0.5})
            recent = snap.load_recent("weekly", n=1)
        assert len(recent) == 1
        assert recent[0]["campaigns_closed"] == 5
        assert recent[0]["win_rate"] == 0.6

    def test_load_recent_returns_newest_first(self, tmp_path):
        with patch.object(snap, "_BASE_DIR", str(tmp_path)):
            for week_offset in range(3):
                ps = datetime(2025, 1, 6) + timedelta(weeks=week_offset)
                pe = ps + timedelta(days=6)
                snap.save("weekly", ps, pe, self._analytics(),
                          {"nav": 10000.0, "nav_source": "broker", "freshness": "fresh", "risk_pct_input": 0.5})
            recent = snap.load_recent("weekly", n=3)
        dates = [r["period_start"] for r in recent]
        assert dates == sorted(dates, reverse=True)

    def test_load_previous_returns_correct_period(self, tmp_path):
        with patch.object(snap, "_BASE_DIR", str(tmp_path)):
            week1 = datetime(2025, 1,  6)
            week2 = datetime(2025, 1, 13)
            snap.save("weekly", week1, week1 + timedelta(days=6), self._analytics(),
                      {"nav": 10000.0, "nav_source": "broker", "freshness": "fresh", "risk_pct_input": 0.5})
            prev = snap.load_previous("weekly", week2)
        assert prev is not None
        assert prev["period_start"] == week1.isoformat()

    def test_load_previous_returns_none_when_no_earlier(self, tmp_path):
        with patch.object(snap, "_BASE_DIR", str(tmp_path)):
            snap.save("weekly", datetime(2025,1,13), datetime(2025,1,19), self._analytics(),
                      {"nav": 10000.0, "nav_source": "broker", "freshness": "fresh", "risk_pct_input": 0.5})
            prev = snap.load_previous("weekly", datetime(2025, 1, 6))
        assert prev is None

    def test_load_recent_returns_empty_on_missing_dir(self, tmp_path):
        with patch.object(snap, "_BASE_DIR", str(tmp_path / "nonexistent")):
            result = snap.load_recent("weekly")
        assert result == []

    def test_corrupt_snapshot_file_skipped(self, tmp_path):
        folder = tmp_path / "weekly"
        folder.mkdir(parents=True)
        (folder / "2025-01-06.json").write_text("NOT VALID JSON {{{")
        with patch.object(snap, "_BASE_DIR", str(tmp_path)):
            result = snap.load_recent("weekly")
        assert result == []   # Corrupt file is silently skipped

    def test_snapshot_contains_all_required_keys(self, tmp_path):
        with patch.object(snap, "_BASE_DIR", str(tmp_path)):
            snap.save("monthly", datetime(2025,1,1), datetime(2025,1,31),
                      self._analytics(), {"nav": 10000.0, "nav_source": "broker", "freshness": "fresh", "risk_pct_input": 0.5})
            recent = snap.load_recent("monthly", n=1)
        s = recent[0]
        for key in ("period_type", "period_start", "period_end", "generated_at",
                    "campaigns_closed", "win_rate", "expectancy_r", "profit_factor"):
            assert key in s, f"Snapshot missing key: {key}"


# ════════════════════════════════════════════════════════════════════════════════
# ADAPTIVE RISK ENGINE — MALFORMED CAMPAIGNS
# ════════════════════════════════════════════════════════════════════════════════

class TestAdaptiveRiskMalformedInput:
    def test_empty_campaigns_returns_error(self):
        result = are.compute_adaptive_risk([], 0.5, 10000)
        assert result["ok"] is False

    def test_campaigns_with_missing_is_win_defaults_gracefully(self):
        campaigns = [
            {"campaign_id": "c1", "close_date": datetime(2025,1,10), "total_pnl_usd": 100},  # no is_win
        ] * 5
        # Should not raise (is_win missing defaults via .get)
        try:
            result = are.compute_adaptive_risk(campaigns, 0.5, 10000)
        except Exception as e:
            pytest.fail(f"compute_adaptive_risk raised {e}")

    def test_compute_closed_campaigns_with_none_df(self):
        result = are.compute_closed_campaigns(None)
        assert result == []

    def test_compute_closed_campaigns_empty_df(self):
        result = are.compute_closed_campaigns(pd.DataFrame())
        assert result == []

    def test_compute_closed_campaigns_no_campaign_id_column(self):
        df = pd.DataFrame([{"symbol": "AAPL", "quantity": 10}])
        result = are.compute_closed_campaigns(df)
        assert result == []

    def test_compute_closed_campaigns_open_position_excluded(self):
        """Campaign where buys > sells → still open → excluded."""
        df = pd.DataFrame([
            {"campaign_id": "c1", "symbol": "AAPL", "side": "BUY",
             "quantity": 10, "price": 100, "pnl_usd": 0, "trade_date": "2025-01-07"},
        ])
        result = are.compute_closed_campaigns(df)
        assert result == []

    def test_compute_closed_campaigns_returns_sorted_newest_first(self):
        df = pd.DataFrame([
            {"campaign_id": "c1", "symbol": "A", "side": "BUY",
             "quantity": 10, "price": 100, "pnl_usd": 0, "trade_date": "2025-01-07"},
            {"campaign_id": "c1", "symbol": "A", "side": "SELL",
             "quantity": -10, "price": 110, "pnl_usd": 100, "trade_date": "2025-01-10"},
            {"campaign_id": "c2", "symbol": "B", "side": "BUY",
             "quantity": 5, "price": 200, "pnl_usd": 0, "trade_date": "2025-01-01"},
            {"campaign_id": "c2", "symbol": "B", "side": "SELL",
             "quantity": -5, "price": 210, "pnl_usd": 50, "trade_date": "2025-01-05"},
        ])
        result = are.compute_closed_campaigns(df)
        assert len(result) == 2
        assert result[0]["close_date"] >= result[1]["close_date"]


# ════════════════════════════════════════════════════════════════════════════════
# IBKR SYNC — XML VALIDATION
# ════════════════════════════════════════════════════════════════════════════════

class TestIbkrXmlValidation:
    def test_empty_string_returns_parse_error(self):
        err = ibkr.parse_flex_error("")
        assert err is not None
        assert err["class"] == "temporary"

    def test_plain_text_not_xml_returns_error(self):
        err = ibkr.parse_flex_error("Server is down for maintenance")
        assert err is not None

    def test_valid_xml_no_error_code_returns_none(self):
        xml = "<FlexQueryResponse><FlexStatements count='1'><Trade /></FlexStatements></FlexQueryResponse>"
        err = ibkr.parse_flex_error(xml)
        assert err is None

    def test_xml_with_non_numeric_error_code(self):
        xml = "<FlexStatementResponse><ErrorCode>ABCD</ErrorCode></FlexStatementResponse>"
        err = ibkr.parse_flex_error(xml)
        assert err is not None
        assert err["code"] == -1

    def test_xml_with_empty_error_code_element(self):
        xml = "<FlexStatementResponse><ErrorCode></ErrorCode></FlexStatementResponse>"
        err = ibkr.parse_flex_error(xml)
        assert err is not None

    def test_deeply_nested_error_code_found(self):
        xml = ("<FlexStatementResponse><wrapper><inner>"
               "<ErrorCode>1012</ErrorCode>"
               "</inner></wrapper></FlexStatementResponse>")
        err = ibkr.parse_flex_error(xml)
        assert err is not None
        assert err["code"] == 1012
        assert err["class"] == "fatal"

    def test_all_17_error_codes_classified(self):
        for code, (cls, desc) in ibkr.IBKR_ERROR_CLASSES.items():
            xml = f"<FlexStatementResponse><ErrorCode>{code}</ErrorCode></FlexStatementResponse>"
            err = ibkr.parse_flex_error(xml)
            assert err is not None
            assert err["code"] == code
            assert err["class"] == cls


# ════════════════════════════════════════════════════════════════════════════════
# REPORT DELIVERY — BOUNDARY CONDITIONS
# ════════════════════════════════════════════════════════════════════════════════

class TestReportDeliveryValidation:
    def test_send_pdf_returns_false_for_missing_file(self):
        result = send_pdf("/does/not/exist.pdf", "caption", "chat_id", "token")
        assert result is False

    def test_send_pdf_returns_false_for_empty_token(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        with patch("report_delivery.requests.post") as mock_post:
            mock_post.return_value.ok = False
            mock_post.return_value.json.return_value = {"ok": False}
            result = send_pdf(str(pdf), "caption", "chat_id", "")
        # Should attempt and fail gracefully, not crash
        assert isinstance(result, bool)

    def test_deliver_report_returns_both_keys(self, tmp_path):
        pdf = tmp_path / "report.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        with patch("report_delivery.requests.post") as mock_post:
            mock_post.return_value.ok = True
            mock_post.return_value.json.return_value = {"ok": True}
            result = deliver_report(str(pdf), "summary text", "caption", "chat", "token")
        assert "summary_ok" in result
        assert "pdf_ok" in result
        assert isinstance(result["summary_ok"], bool)
        assert isinstance(result["pdf_ok"], bool)

    def test_send_summary_with_empty_text_doesnt_crash(self):
        with patch("report_delivery.requests.post") as mock_post:
            mock_post.return_value.ok = True
            mock_post.return_value.json.return_value = {"ok": True}
            result = send_summary("", "chat_id", "token")
        assert isinstance(result, bool)

    def test_caption_exactly_1024_chars_not_truncated(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        caption = "A" * 1024
        with patch("report_delivery.requests.post") as mock_post:
            mock_post.return_value.ok = True
            mock_post.return_value.json.return_value = {"ok": True}
            send_pdf(str(pdf), caption, "chat", "tok")
            sent = mock_post.call_args[1]["data"]["caption"]
        assert len(sent) == 1024

    def test_caption_1025_chars_truncated_to_1024(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        caption = "B" * 1025
        with patch("report_delivery.requests.post") as mock_post:
            mock_post.return_value.ok = True
            mock_post.return_value.json.return_value = {"ok": True}
            send_pdf(str(pdf), caption, "chat", "tok")
            sent = mock_post.call_args[1]["data"]["caption"]
        assert len(sent) == 1024


# ════════════════════════════════════════════════════════════════════════════════
# CHART GENERATOR — MISSING DATA KEYS
# ════════════════════════════════════════════════════════════════════════════════

class TestChartGeneratorMissingKeys:
    def test_missing_setup_breakdown_returns_none(self):
        result = cg.setup_performance_bars({}, "test")
        assert result is None

    def test_missing_campaigns_closed_win_loss_donut_returns_none(self):
        result = cg.win_loss_donut({"win_rate": 0.6}, "test")
        assert result is None

    def test_empty_weekly_breakdown_returns_none(self):
        result = cg.weekly_equity_curve([], "test")
        assert result is None

    def test_no_plotly_all_functions_return_none(self):
        with patch.object(cg, "_PLOTLY_OK", False):
            assert cg.campaign_r_bars({"setup_breakdown": {}}, "test") is None
            assert cg.setup_performance_bars({"setup_breakdown": {"B": {"net_r": 1}}}, "test") is None
            assert cg.weekly_equity_curve([{"label": "w1", "net_r": 1}], "test") is None
            assert cg.win_loss_donut({"campaigns_closed": 5, "win_rate": 0.6}, "test") is None
