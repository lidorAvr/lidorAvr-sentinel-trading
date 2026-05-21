"""
F8 (Meeting 21/05/2026 Wave 2) — risk-monitor Telegram-send deadletter.

Before F8 a failed send_telegram (network blip / rate limit / bot down)
only printed to stderr. The CEO couldn't tell which state/digest alerts
had silently dropped — and the system itself had no record. F8 adds
ONE audit_log row per failed send (action="telegram_send_failed")
with: helper name (send_telegram vs send_telegram_with_keyboard),
error type, error message (truncated to 200 chars), text preview
(first 80 chars only — defense in depth against leaking full message
content into the audit trail).

Tests pinned in this file:
  A. The audit constant exists with the documented name.
  B. _audit_telegram_send_failure writes the right shape (helper +
     error_type + error_message + text_preview, all bounded in length).
  C. Helper is fail-open: even when audit_logger raises, the wrapper
     never raises (must NEVER block the next risk-monitor cycle).
  D. send_telegram / send_telegram_with_keyboard's catch paths call
     the deadletter helper (source-scan — verifies the wiring).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(rel_path):
    with open(os.path.join(ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


# ════════════════════════════════════════════════════════════════════════════
# A. Audit constant
# ════════════════════════════════════════════════════════════════════════════

class TestAuditConstant:
    def test_constant_name(self):
        import audit_logger
        assert hasattr(audit_logger, "ACTION_TELEGRAM_SEND_FAILED")
        assert audit_logger.ACTION_TELEGRAM_SEND_FAILED == "telegram_send_failed"


# ════════════════════════════════════════════════════════════════════════════
# B. _audit_telegram_send_failure writes the right shape
# ════════════════════════════════════════════════════════════════════════════
# Risk-monitor is not directly importable (requires TELEGRAM_TOKEN at import).
# Source-scan the helper's behaviour instead — every behavioural assertion
# below maps to a specific line of the helper.

class TestDeadletterHelperShape:
    def test_helper_defined_in_risk_monitor(self):
        src = _read("risk_monitor.py")
        assert "def _audit_telegram_send_failure(" in src

    def test_helper_truncates_error_message_to_200_chars(self):
        # Defense against unbounded error_message in the audit row.
        src = _read("risk_monitor.py")
        assert "str(exc)[:200]" in src, (
            "Deadletter helper must truncate the error message to "
            "≤200 chars before writing the audit row (audit_log shouldn't "
            "grow unboundedly on a flapping send)."
        )

    def test_helper_truncates_text_preview_to_80_chars(self):
        # The full message could contain symbol/PnL data the audit log
        # doesn't need a permanent copy of. Preview only.
        src = _read("risk_monitor.py")
        assert '[:80]' in src or ":80]" in src, (
            "Deadletter helper must truncate the failed text to ≤80 chars "
            "preview (defense in depth against accidental sensitive data "
            "leak into the audit log)."
        )

    def test_helper_records_helper_name_for_grouping(self):
        # The audit row carries the helper name so a future query can
        # distinguish "the state-alert keyboard send failed" from
        # "the digest plain-text send failed".
        src = _read("risk_monitor.py")
        assert '"helper"' in src or "'helper'" in src

    def test_helper_records_error_type(self):
        # error_type lets the CEO group failures by class (TimeoutError,
        # ApiTelegramException, etc) — useful for "is this rate limiting
        # or true network outages?" diagnostics.
        src = _read("risk_monitor.py")
        assert "error_type" in src
        assert "type(exc).__name__" in src

    def test_helper_uses_action_telegram_send_failed_constant(self):
        src = _read("risk_monitor.py")
        assert "ACTION_TELEGRAM_SEND_FAILED" in src


# ════════════════════════════════════════════════════════════════════════════
# C. Helper is fail-open
# ════════════════════════════════════════════════════════════════════════════

class TestFailOpenContract:
    def test_helper_wraps_in_try_except(self):
        # The outer try/except keeps the deadletter wrapper resilient
        # even if audit_logger itself errors (defense in depth — though
        # audit_logger.log_action is itself fail-open already).
        src = _read("risk_monitor.py")
        helper_start = src.find("def _audit_telegram_send_failure(")
        helper_end = src.find("\n\n\ndef send_telegram(", helper_start)
        helper_body = src[helper_start:helper_end]
        assert "try:" in helper_body, "deadletter helper must wrap audit call in try/"
        assert "except Exception:" in helper_body, "must catch any audit exception"

    def test_send_helpers_continue_to_print_to_stderr(self):
        # Keep the existing stderr print on failure — docker logs catch
        # it, so investigators can correlate the audit row with the live
        # log line. F8 is ADDITIVE, never removes the legacy print.
        src = _read("risk_monitor.py")
        assert 'print(f"Telegram send failed:' in src
        assert 'print(f"Telegram send_keyboard failed:' in src


# ════════════════════════════════════════════════════════════════════════════
# D. Surface wiring — send_telegram + send_telegram_with_keyboard route through helper
# ════════════════════════════════════════════════════════════════════════════

class TestSendHelpersCallDeadletter:
    def test_send_telegram_catch_calls_deadletter(self):
        src = _read("risk_monitor.py")
        # Find the send_telegram function block.
        idx = src.find("def send_telegram(text):")
        end = src.find("\n\ndef ", idx)
        body = src[idx:end]
        assert "_audit_telegram_send_failure(" in body, (
            "send_telegram's except branch must call the deadletter helper. "
            "Otherwise the audit trail misses non-keyboard alert failures."
        )
        # Helper called with "send_telegram" as the source name.
        assert '"send_telegram"' in body

    def test_send_telegram_with_keyboard_catch_calls_deadletter(self):
        src = _read("risk_monitor.py")
        idx = src.find("def send_telegram_with_keyboard(text, markup):")
        end = src.find("\n\n", idx + 1)
        body = src[idx:end]
        assert "_audit_telegram_send_failure(" in body, (
            "send_telegram_with_keyboard's except branch must call the "
            "deadletter helper. State-alert keyboards (RUNNER decision) "
            "would silently drop without this wiring."
        )
        assert '"send_telegram_with_keyboard"' in body
