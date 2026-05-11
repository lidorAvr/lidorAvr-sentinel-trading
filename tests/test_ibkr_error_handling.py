"""
Tests for IBKR Flex Query error classification and retry logic.
All tests are deterministic and do not make network calls.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ibkr_sync_runner as m


# ── Helpers ────────────────────────────────────────────────────────────────

def make_error_xml(code, message="Test error"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<FlexStatementResponse>
  <Status>Fail</Status>
  <ErrorCode>{code}</ErrorCode>
  <ErrorMessage>{message}</ErrorMessage>
</FlexStatementResponse>"""


def make_success_xml():
    return """<?xml version="1.0" encoding="UTF-8"?>
<FlexStatementResponse>
  <Status>Success</Status>
  <ReferenceCode>9876543210</ReferenceCode>
</FlexStatementResponse>"""


def make_report_xml():
    return """<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse queryName="Test">
  <FlexStatements count="1">
    <FlexStatement accountId="U123">
      <Trades>
        <Trade symbol="AAPL" />
        <Trade symbol="MRVL" />
      </Trades>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>"""


# ── IBKR_ERROR_CLASSES coverage ────────────────────────────────────────────

class TestIbkrErrorClasses:
    def test_all_temporary_codes_classified(self):
        temporary_codes = [1001, 1004, 1005, 1006, 1007, 1008, 1009, 1019, 1021]
        for code in temporary_codes:
            cls, _ = m.IBKR_ERROR_CLASSES[code]
            assert cls == "temporary", f"Code {code} should be temporary, got {cls}"

    def test_all_fatal_codes_classified(self):
        fatal_codes = [1012, 1013, 1014, 1015, 1016, 1017, 1020]
        for code in fatal_codes:
            cls, _ = m.IBKR_ERROR_CLASSES[code]
            assert cls == "fatal", f"Code {code} should be fatal, got {cls}"

    def test_rate_limit_code_classified(self):
        cls, _ = m.IBKR_ERROR_CLASSES[1018]
        assert cls == "rate_limit"

    def test_all_codes_have_hebrew_description(self):
        for code, (cls, desc) in m.IBKR_ERROR_CLASSES.items():
            assert len(desc) > 5, f"Code {code} has too short a description: {desc!r}"

    def test_max_attempts_raised_to_five(self):
        import main as _main
        assert _main.MAX_ATTEMPTS_PER_DAY == 5


# ── parse_flex_error ────────────────────────────────────────────────────────

class TestParseFlexError:
    def test_success_response_returns_none(self):
        assert m.parse_flex_error(make_success_xml()) is None

    def test_report_xml_returns_none(self):
        assert m.parse_flex_error(make_report_xml()) is None

    def test_temporary_code_1019(self):
        result = m.parse_flex_error(make_error_xml(1019))
        assert result is not None
        assert result["code"] == 1019
        assert result["class"] == "temporary"
        assert len(result["description"]) > 0

    def test_temporary_code_1001(self):
        result = m.parse_flex_error(make_error_xml(1001))
        assert result["class"] == "temporary"

    def test_fatal_code_1015(self):
        result = m.parse_flex_error(make_error_xml(1015))
        assert result["code"] == 1015
        assert result["class"] == "fatal"

    def test_fatal_code_1014_bad_query(self):
        result = m.parse_flex_error(make_error_xml(1014))
        assert result["class"] == "fatal"

    def test_rate_limit_code_1018(self):
        result = m.parse_flex_error(make_error_xml(1018))
        assert result["class"] == "rate_limit"

    def test_unknown_code_defaults_to_temporary(self):
        result = m.parse_flex_error(make_error_xml(9999))
        assert result is not None
        assert result["code"] == 9999
        assert result["class"] == "temporary"

    def test_malformed_xml_returns_temporary_not_exception(self):
        result = m.parse_flex_error("this is not xml <<<")
        assert result is not None
        assert result["class"] == "temporary"

    def test_empty_string_returns_temporary_not_exception(self):
        result = m.parse_flex_error("")
        assert result is not None
        assert result["class"] == "temporary"

    def test_result_has_required_keys(self):
        result = m.parse_flex_error(make_error_xml(1019))
        assert "code" in result
        assert "class" in result
        assert "description" in result

    def test_all_known_error_codes_parsed_correctly(self):
        for code, (expected_class, _) in m.IBKR_ERROR_CLASSES.items():
            result = m.parse_flex_error(make_error_xml(code))
            assert result is not None, f"Code {code} returned None"
            assert result["class"] == expected_class, (
                f"Code {code}: expected {expected_class}, got {result['class']}"
            )
