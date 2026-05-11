"""
test_ibkr_sync_full.py — Comprehensive IBKR Flex Query sync tests.

Covers:
- parse_flex_error: all 17 known error codes + unknown + malformed XML
- get_statement_with_retry: retry count, fatal stops, success path
- run_ibkr_sync: full pipeline mocking (SendRequest + GetStatement + NAV update)
- NAV extraction from XML (ChangeInNAV endingValue)
- Old report cleanup (keeps only _REPORTS_TO_KEEP files)
- Manual result file written on success
- Error return structure always has required keys
"""
import json
import os
import sys
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import ibkr_sync_runner as m


# ── XML helpers ────────────────────────────────────────────────────────────────

def _error_xml(code):
    return f"<FlexStatementResponse><ErrorCode>{code}</ErrorCode></FlexStatementResponse>"

_IBKR_FETCH_URL = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"

def _success_xml(ref="REF123456"):
    return (f"<FlexStatementResponse><Status>Success</Status>"
            f"<ReferenceCode>{ref}</ReferenceCode>"
            f"<Url>{_IBKR_FETCH_URL}</Url></FlexStatementResponse>")

def _success_xml_legacy(ref="REF123456"):
    """Old lowercase <code> format — kept for backward-compat coverage."""
    return f"<FlexStatementResponse><Status>Success</Status><code>{ref}</code></FlexStatementResponse>"

def _statement_xml(nav=12345.67, trade_count=3):
    trades = "".join(f"<Trade id='{i}' />" for i in range(trade_count))
    return (
        f"<FlexQueryResponse>"
        f"<ChangeInNAV endingValue='{nav}' />"
        f"<Trades>{trades}</Trades>"
        f"</FlexQueryResponse>"
    )


# ════════════════════════════════════════════════════════════════════════════════
# PARSE_FLEX_ERROR — ALL ERROR CODES
# ════════════════════════════════════════════════════════════════════════════════

class TestParseFlexErrorCodes:
    """Every code in IBKR_ERROR_CLASSES must be correctly parsed and classified."""

    @pytest.mark.parametrize("code,expected_class", [
        (1001, "temporary"), (1004, "temporary"), (1005, "temporary"),
        (1006, "temporary"), (1007, "temporary"), (1008, "temporary"),
        (1009, "temporary"), (1018, "rate_limit"), (1019, "temporary"),
        (1021, "temporary"), (1012, "fatal"), (1013, "fatal"),
        (1014, "fatal"), (1015, "fatal"), (1016, "fatal"),
        (1017, "fatal"), (1020, "fatal"),
    ])
    def test_known_code_classified_correctly(self, code, expected_class):
        err = m.parse_flex_error(_error_xml(code))
        assert err is not None
        assert err["code"] == code
        assert err["class"] == expected_class

    def test_unknown_code_classified_temporary(self):
        err = m.parse_flex_error(_error_xml(9999))
        assert err["class"] == "temporary"
        assert "9999" in err["description"]

    def test_no_error_code_returns_none(self):
        xml = "<FlexQueryResponse><Trade /></FlexQueryResponse>"
        assert m.parse_flex_error(xml) is None

    def test_empty_xml_returns_error_dict(self):
        err = m.parse_flex_error("")
        assert err is not None
        assert err["code"] == -1

    def test_not_xml_returns_error_dict(self):
        err = m.parse_flex_error("Internal Server Error 500")
        assert err is not None

    def test_all_errors_have_description(self):
        for code in m.IBKR_ERROR_CLASSES:
            err = m.parse_flex_error(_error_xml(code))
            assert err["description"] != ""

    def test_fatal_errors_are_not_temporary(self):
        fatal_codes = [code for code, (cls, _) in m.IBKR_ERROR_CLASSES.items()
                       if cls == "fatal"]
        for code in fatal_codes:
            err = m.parse_flex_error(_error_xml(code))
            assert err["class"] == "fatal"
            assert err["class"] != "temporary"


# ════════════════════════════════════════════════════════════════════════════════
# GET_STATEMENT_WITH_RETRY
# ════════════════════════════════════════════════════════════════════════════════

class TestGetStatementWithRetry:
    def _mock_resp(self, text):
        r = MagicMock()
        r.text = text
        return r

    def test_success_on_first_attempt(self):
        with patch("ibkr_sync_runner.requests.get",
                   return_value=self._mock_resp(_statement_xml())):
            with patch("ibkr_sync_runner.time.sleep"):
                xml, err = m.get_statement_with_retry("ref", "tok", max_retries=3, wait_sec=0)
        assert xml is not None
        assert err is None

    def test_fatal_stops_after_first_attempt(self):
        attempts = []
        def fake_get(url, timeout=60):
            attempts.append(1)
            return self._mock_resp(_error_xml(1015))   # fatal
        with patch("ibkr_sync_runner.requests.get", side_effect=fake_get):
            with patch("ibkr_sync_runner.time.sleep"):
                xml, err = m.get_statement_with_retry("ref", "tok", max_retries=5, wait_sec=0)
        assert len(attempts) == 1
        assert err["class"] == "fatal"

    def test_temporary_retries_exact_max(self):
        attempts = []
        def fake_get(url, timeout=60):
            attempts.append(1)
            return self._mock_resp(_error_xml(1001))
        with patch("ibkr_sync_runner.requests.get", side_effect=fake_get):
            with patch("ibkr_sync_runner.time.sleep"):
                m.get_statement_with_retry("ref", "tok", max_retries=3, wait_sec=0)
        assert len(attempts) == 3

    def test_success_after_temporary_errors(self):
        calls = [0]
        def fake_get(url, timeout=60):
            calls[0] += 1
            if calls[0] < 3:
                return self._mock_resp(_error_xml(1001))
            return self._mock_resp(_statement_xml())
        with patch("ibkr_sync_runner.requests.get", side_effect=fake_get):
            with patch("ibkr_sync_runner.time.sleep"):
                xml, err = m.get_statement_with_retry("ref", "tok", max_retries=3, wait_sec=0)
        assert xml is not None
        assert err is None

    def test_network_error_counted_as_attempt(self):
        attempts = []
        def fake_get(url, timeout=60):
            attempts.append(1)
            raise ConnectionError("Network unreachable")
        with patch("ibkr_sync_runner.requests.get", side_effect=fake_get):
            with patch("ibkr_sync_runner.time.sleep"):
                xml, err = m.get_statement_with_retry("ref", "tok", max_retries=2, wait_sec=0)
        assert len(attempts) == 2
        assert xml is None

    def test_sleep_called_between_retries(self):
        sleeps = []
        def fake_sleep(s):
            sleeps.append(s)
        def fake_get(url, timeout=60):
            return self._mock_resp(_error_xml(1001))
        with patch("ibkr_sync_runner.requests.get", side_effect=fake_get):
            with patch("ibkr_sync_runner.time.sleep", side_effect=fake_sleep):
                m.get_statement_with_retry("ref", "tok", max_retries=3, wait_sec=10)
        # Should sleep between attempts (2 sleeps for 3 attempts)
        assert len(sleeps) == 2
        assert all(s == 10 for s in sleeps)


# ════════════════════════════════════════════════════════════════════════════════
# RUN_IBKR_SYNC — FULL PIPELINE
# ════════════════════════════════════════════════════════════════════════════════

class TestRunIbkrSync:
    def _make_send_resp(self, text):
        r = MagicMock()
        r.text = text
        return r

    def test_success_returns_correct_structure(self, tmp_path):
        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok", "IBKR_QUERY_ID": "123"}),
              patch("ibkr_sync_runner.requests.get") as mock_get,
              patch("ibkr_sync_runner.time.sleep"),
              patch("ibkr_sync_runner._REPORTS_DIR", str(tmp_path)),
              patch("ibkr_sync_runner._CONFIG_PATH", str(tmp_path / "cfg.json"))):

            mock_get.side_effect = [
                self._make_send_resp(_success_xml("REF_ABC")),
                self._make_send_resp(_statement_xml(nav=15000.0, trade_count=5)),
            ]
            result = m.run_ibkr_sync()

        assert result["status"] == "success"
        assert result["nav"] == pytest.approx(15000.0)
        assert "5" in result["message"]

    def test_send_request_error_returns_error_status(self, tmp_path):
        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok"}),
              patch("ibkr_sync_runner.requests.get",
                    return_value=self._make_send_resp(_error_xml(1018))),
              patch("ibkr_sync_runner.time.sleep")):
            result = m.run_ibkr_sync()
        assert result["status"] == "rate_limit"
        assert result["nav"] is None

    def test_missing_ref_code_returns_temporary(self, tmp_path):
        send_xml = "<FlexStatementResponse><Status>Success</Status></FlexStatementResponse>"
        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok"}),
              patch("ibkr_sync_runner.requests.get",
                    return_value=self._make_send_resp(send_xml)),
              patch("ibkr_sync_runner.time.sleep")):
            result = m.run_ibkr_sync()
        assert result["status"] == "temporary"

    def test_legacy_lowercase_code_element_accepted(self, tmp_path):
        """<code> (old lowercase format) must still be accepted as fallback."""
        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok"}),
              patch("ibkr_sync_runner.requests.get") as mock_get,
              patch("ibkr_sync_runner.time.sleep"),
              patch("ibkr_sync_runner._REPORTS_DIR", str(tmp_path))):
            mock_get.side_effect = [
                self._make_send_resp(_success_xml_legacy("LEGACYREF")),
                self._make_send_resp(_statement_xml(nav=9000.0)),
            ]
            result = m.run_ibkr_sync()
        assert result["status"] == "success"

    def test_nav_updated_in_config_on_success(self, tmp_path):
        cfg_path = str(tmp_path / "sentinel_config.json")
        with open(cfg_path, "w") as f:
            json.dump({"total_deposited": 7500.0, "risk_pct_input": 0.5}, f)

        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok", "IBKR_QUERY_ID": "123"}),
              patch("ibkr_sync_runner.requests.get") as mock_get,
              patch("ibkr_sync_runner.time.sleep"),
              patch("ibkr_sync_runner._REPORTS_DIR", str(tmp_path)),
              patch("ibkr_sync_runner._CONFIG_PATH", cfg_path)):

            mock_get.side_effect = [
                self._make_send_resp(_success_xml()),
                self._make_send_resp(_statement_xml(nav=20000.0)),
            ]
            m.run_ibkr_sync()

        with open(cfg_path) as f:
            cfg = json.load(f)
        assert cfg["nav"] == pytest.approx(20000.0)
        assert "nav_updated_at" in cfg

    def test_xml_saved_to_reports_dir(self, tmp_path):
        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok", "IBKR_QUERY_ID": "123"}),
              patch("ibkr_sync_runner.requests.get") as mock_get,
              patch("ibkr_sync_runner.time.sleep"),
              patch("ibkr_sync_runner._REPORTS_DIR", str(tmp_path)),
              patch("ibkr_sync_runner._CONFIG_PATH", str(tmp_path / "cfg.json"))):

            mock_get.side_effect = [
                self._make_send_resp(_success_xml()),
                self._make_send_resp(_statement_xml()),
            ]
            m.run_ibkr_sync()

        xml_files = list(tmp_path.glob("ibkr_*.xml"))
        assert len(xml_files) == 1

    def test_old_reports_cleaned_up(self, tmp_path):
        # Pre-create 5 old reports (more than _REPORTS_TO_KEEP=3)
        for i in range(5):
            (tmp_path / f"ibkr_2025-01-0{i+1}_00-00.xml").write_text("<old/>")

        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok", "IBKR_QUERY_ID": "123"}),
              patch("ibkr_sync_runner.requests.get") as mock_get,
              patch("ibkr_sync_runner.time.sleep"),
              patch("ibkr_sync_runner._REPORTS_DIR", str(tmp_path)),
              patch("ibkr_sync_runner._CONFIG_PATH", str(tmp_path / "cfg.json"))):

            mock_get.side_effect = [
                self._make_send_resp(_success_xml()),
                self._make_send_resp(_statement_xml()),
            ]
            m.run_ibkr_sync()

        xml_files = list(tmp_path.glob("ibkr_*.xml"))
        assert len(xml_files) <= m._REPORTS_TO_KEEP

    def test_result_always_has_required_keys(self, tmp_path):
        required = {"status", "code", "message", "nav"}
        # Test multiple failure scenarios
        for xml_resp in [_error_xml(1015), _error_xml(1001), "<bad xml"]:
            with (patch.dict(os.environ, {"IBKR_TOKEN": "tok"}),
                  patch("ibkr_sync_runner.requests.get",
                        return_value=self._make_send_resp(xml_resp)),
                  patch("ibkr_sync_runner.time.sleep")):
                result = m.run_ibkr_sync()
            assert required.issubset(result.keys()), f"Missing keys for xml: {xml_resp}"

    def test_network_exception_returns_temporary(self):
        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok"}),
              patch("ibkr_sync_runner.requests.get", side_effect=ConnectionError("down")),
              patch("ibkr_sync_runner.time.sleep")):
            result = m.run_ibkr_sync()
        assert result["status"] == "temporary"
        assert result["nav"] is None

    def test_log_fn_called_with_sync_messages(self):
        log_calls = []
        with (patch.dict(os.environ, {"IBKR_TOKEN": "tok", "IBKR_QUERY_ID": "123"}),
              patch("ibkr_sync_runner.requests.get") as mock_get,
              patch("ibkr_sync_runner.time.sleep"),
              patch("ibkr_sync_runner._REPORTS_DIR", "/tmp/test_reports"),
              patch("ibkr_sync_runner._CONFIG_PATH", "/tmp/test_cfg.json"),
              patch("ibkr_sync_runner.os.makedirs"),
              patch("builtins.open", side_effect=Exception("no disk"))):

            mock_get.side_effect = [
                self._make_send_resp(_success_xml()),
                self._make_send_resp(_statement_xml()),
            ]
            m.run_ibkr_sync(log_fn=log_calls.append)

        assert len(log_calls) > 0
        assert any("Sync" in msg or "IBKR" in msg for msg in log_calls)
