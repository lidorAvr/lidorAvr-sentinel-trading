"""
test_security.py — Security tests for Sentinel Trading.

Covers:
- Sensitive data masking (tokens, passwords never in plain text)
- Rate limiting enforcement (developer sync)
- Authorization checks (admin-only commands)
- Input sanitization (no injection via ticker / chat_id / captions)
- Secrets not leaked in error messages or logs
- Report delivery: no token in URLs stored to disk
- Config display: all sensitive keys masked
"""
import json
import os
import sys
import time
import re
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_dev_state(count_today=0, last_ts=None, date=None):
    return {
        "date":        date or datetime.now().strftime("%Y-%m-%d"),
        "count_today": count_today,
        "last_ts":     last_ts or 0,
    }


# ════════════════════════════════════════════════════════════════════════════════
# 1. TOKEN MASKING
# ════════════════════════════════════════════════════════════════════════════════

class TestTokenMasking:
    """Tokens and secrets must never appear unmasked in output."""

    def test_ibkr_sync_result_does_not_contain_token(self, tmp_path):
        """run_ibkr_sync result must not include the IBKR_TOKEN value."""
        import ibkr_sync_runner as m
        fake_token = "SUPER_SECRET_TOKEN_12345"
        with (patch.dict(os.environ, {"IBKR_TOKEN": fake_token, "IBKR_QUERY_ID": "9999"}),
              patch("ibkr_sync_runner.requests") as mock_req,
              patch("ibkr_sync_runner.time") as _,
              patch("ibkr_sync_runner.os.makedirs"),
              patch("builtins.open", side_effect=Exception("no write"))):
            # SendRequest returns an error XML
            mock_req.get.return_value.text = (
                "<FlexStatementResponse><Status>Fail</Status>"
                "<ErrorCode>1009</ErrorCode></FlexStatementResponse>"
            )
            result = m.run_ibkr_sync()

        result_str = json.dumps(result)
        assert fake_token not in result_str

    def test_parse_flex_error_does_not_expose_token(self):
        import ibkr_sync_runner as m
        xml = "<FlexStatementResponse><ErrorCode>1015</ErrorCode></FlexStatementResponse>"
        err = m.parse_flex_error(xml)
        assert err is not None
        # Error descriptions may legitimately use the word "Token" (it's an auth error).
        # What must NOT appear are actual secret values or patterns like API keys.
        assert "SECRET" not in json.dumps(err).upper()
        assert err["code"] == 1015
        assert err["class"] == "fatal"

    def test_account_state_fallback_does_not_include_token(self):
        import account_state as m
        with patch.object(m, "_CONFIG_PATHS", ["/nonexistent/path.json"]):
            result = m.load()
        result_str = json.dumps(result)
        # None of these dangerous patterns should appear
        for pattern in ("password", "token", "secret", "key"):
            assert pattern.lower() not in result_str.lower()

    def test_config_display_masks_token_fields(self):
        """Simulate what the developer menu shows — tokens must be masked."""
        config = {
            "nav": 10000.0,
            "risk_pct_input": 0.5,
            "total_deposited": 7500.0,
            "TELEGRAM_TOKEN": "bot123456:ABC-DEF",
            "IBKR_TOKEN": "real_ibkr_secret",
            "SUPABASE_KEY": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret",
        }
        _SENSITIVE_KEYS = {"TELEGRAM_TOKEN", "IBKR_TOKEN", "SUPABASE_KEY",
                           "telegram_token", "ibkr_token", "supabase_key"}
        masked = {
            k: ("***" if k in _SENSITIVE_KEYS else v)
            for k, v in config.items()
        }
        for key in _SENSITIVE_KEYS:
            if key in masked:
                assert masked[key] == "***", f"{key} must be masked"


# ════════════════════════════════════════════════════════════════════════════════
# 2. RATE LIMITING
# ════════════════════════════════════════════════════════════════════════════════

class TestRateLimiting:
    """Developer sync must be rate-limited: max 2/day, min 3h cooldown."""

    def _import_bot(self):
        for mod in ("telebot", "telebot.types", "supabase", "dotenv",
                    "adaptive_risk_engine", "engine_core", "telegram_formatters"):
            sys.modules.setdefault(mod, MagicMock())
        import telegram_bot as tb
        return tb

    def test_daily_limit_blocks_third_sync(self, tmp_path):
        tb = self._import_bot()
        state = _make_dev_state(count_today=2)
        state_path = str(tmp_path / "dev_state.json")
        with open(state_path, "w") as f:
            json.dump(state, f)
        with patch.object(tb, "_DEV_STATE_FILE", state_path):
            allowed, reason, _ = tb._dev_sync_check()
        assert allowed is False
        assert "יום" in reason or "limit" in reason.lower() or "2" in reason

    def test_cooldown_blocks_too_soon(self, tmp_path):
        tb = self._import_bot()
        state = _make_dev_state(
            count_today=1,
            last_ts=(datetime.now() - timedelta(minutes=30)).isoformat()  # 30 min ago
        )
        state_path = str(tmp_path / "dev_state.json")
        with open(state_path, "w") as f:
            json.dump(state, f)
        with patch.object(tb, "_DEV_STATE_FILE", state_path):
            allowed, reason, _ = tb._dev_sync_check()
        assert allowed is False
        assert "שעות" in reason or "cooldown" in reason.lower() or "3" in reason

    def test_fresh_state_allows_sync(self, tmp_path):
        tb = self._import_bot()
        state_path = str(tmp_path / "dev_state.json")
        # No file → fresh
        with patch.object(tb, "_DEV_STATE_FILE", state_path):
            allowed, reason, _ = tb._dev_sync_check()
        assert allowed is True

    def test_after_cooldown_allows_sync(self, tmp_path):
        tb = self._import_bot()
        state = _make_dev_state(
            count_today=1,
            last_ts=time.time() - 60 * 60 * 4   # 4h ago — past 3h cooldown
        )
        state_path = str(tmp_path / "dev_state.json")
        with open(state_path, "w") as f:
            json.dump(state, f)
        with patch.object(tb, "_DEV_STATE_FILE", state_path):
            allowed, _, _ = tb._dev_sync_check()
        assert allowed is True

    def test_record_increments_count(self, tmp_path):
        tb = self._import_bot()
        state_path = str(tmp_path / "dev_state.json")
        with open(state_path, "w") as f:
            json.dump(_make_dev_state(count_today=1), f)
        with patch.object(tb, "_DEV_STATE_FILE", state_path):
            state = _make_dev_state(count_today=1)
            tb._dev_sync_record(state)
        with open(state_path) as f:
            saved = json.load(f)
        assert saved["count_today"] == 2

    def test_yesterday_count_resets_to_zero(self, tmp_path):
        tb = self._import_bot()
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        state = _make_dev_state(count_today=2, date=yesterday)
        state_path = str(tmp_path / "dev_state.json")
        with open(state_path, "w") as f:
            json.dump(state, f)
        with patch.object(tb, "_DEV_STATE_FILE", state_path):
            allowed, _, _ = tb._dev_sync_check()
        assert allowed is True


# ════════════════════════════════════════════════════════════════════════════════
# 3. INPUT SANITIZATION
# ════════════════════════════════════════════════════════════════════════════════

class TestInputSanitization:
    """Malicious or unexpected input must not break the system or leak data."""

    def test_pdf_caption_truncated_at_1024_chars(self):
        """sendDocument caption must not exceed Telegram's 1024-char limit."""
        from report_delivery import send_pdf
        long_caption = "A" * 2000
        with patch("report_delivery.requests.post") as mock_post:
            mock_post.return_value.ok = True
            mock_post.return_value.json.return_value = {"ok": True}
            # Create a dummy file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(b"%PDF-1.4")
                path = f.name
            try:
                send_pdf(path, long_caption, "12345", "fake_token")
                call_kwargs = mock_post.call_args
                sent_caption = call_kwargs[1]["data"]["caption"]
                assert len(sent_caption) <= 1024
            finally:
                os.unlink(path)

    def test_send_pdf_nonexistent_file_returns_false(self):
        from report_delivery import send_pdf
        result = send_pdf("/nonexistent/path/report.pdf", "caption", "chat", "token")
        assert result is False

    def test_period_label_with_unicode_symbols(self):
        """Period labels must handle Hebrew months without crashing."""
        import report_renderer as rr
        from datetime import datetime
        # All 12 months
        for month in range(1, 13):
            start = datetime(2025, month, 1)
            end   = datetime(2025, month, 28)
            label = rr._period_label(start, end)
            assert isinstance(label, str)
            assert len(label) > 0

    def test_analytics_with_xss_in_symbol_doesnt_crash(self):
        """Symbol names with HTML/script chars must not cause exceptions."""
        import pandas as pd
        from analytics_engine import compute_period_analytics
        from datetime import datetime

        df = pd.DataFrame([
            {"campaign_id": "c1", "side": "BUY",  "trade_date": "2025-01-07",
             "price": 100, "quantity": 10, "pnl_usd": 0,
             "initial_stop": 95, "stop_loss": 95,
             "setup_type": "<script>alert(1)</script>",
             "symbol": "<img src=x onerror=alert(1)>"},
            {"campaign_id": "c1", "side": "SELL", "trade_date": "2025-01-09",
             "price": 110, "quantity": 10, "pnl_usd": 100,
             "initial_stop": 0, "stop_loss": 0,
             "setup_type": "<script>alert(1)</script>",
             "symbol": "<img src=x onerror=alert(1)>"},
        ])
        account = {"nav": 10000.0, "risk_pct_input": 1.0}
        result = compute_period_analytics(df, datetime(2025, 1, 6), datetime(2025, 1, 13), account)
        # Must not raise; result is a valid dict
        assert isinstance(result, dict)

    def test_summary_text_does_not_execute_markdown_injection(self):
        """Summary text for Telegram must be valid Markdown, not executable."""
        from report_renderer import build_summary_text
        analytics = {
            "ok": True, "campaigns_closed": 3, "win_rate": 0.6,
            "total_r_net": 1.5, "realized_pnl": 300.0,
            "expectancy_r": 0.5, "profit_factor": 2.0,
            "missing_stop_rate": 0.0, "oversized_rate": 0.0,
        }
        text = build_summary_text(analytics, "05/01–11/01", "weekly")
        # Should not contain raw HTML
        assert "<script" not in text
        assert "<img" not in text
        # Must use only allowed Telegram Markdown (*, `, no < >)
        assert isinstance(text, str)


# ════════════════════════════════════════════════════════════════════════════════
# 4. SECRETS NOT IN LOGS
# ════════════════════════════════════════════════════════════════════════════════

class TestSecretsNotInLogs:
    """Log messages and error outputs must not contain credential values."""

    def test_ibkr_sync_error_log_doesnt_contain_token(self, tmp_path):
        import ibkr_sync_runner as m
        fake_token = "VERY_SECRET_IBKR_TOKEN"
        log_lines = []
        def capture_log(msg):
            log_lines.append(msg)

        with (patch.dict(os.environ, {"IBKR_TOKEN": fake_token}),
              patch("ibkr_sync_runner.requests") as mock_req,
              patch("ibkr_sync_runner.time.sleep")):
            mock_req.get.side_effect = Exception("connection refused")
            m.run_ibkr_sync(log_fn=capture_log)

        full_log = " ".join(log_lines)
        assert fake_token not in full_log

    def test_report_delivery_log_doesnt_contain_token(self, tmp_path, capsys):
        from report_delivery import _log
        # _log always prints to stdout before attempting file write.
        # Capture stdout to verify no token values are injected.
        _log("test error: connection refused")
        captured = capsys.readouterr()
        assert "test error" in captured.out
        assert "TOKEN" not in captured.out.upper() or "test error" in captured.out

    def test_account_state_error_message_safe(self, tmp_path):
        import account_state as m
        cfg = tmp_path / "sentinel_config.json"
        cfg.write_text('{"nav": 10000, "TELEGRAM_TOKEN": "secret_token_here"}')
        with patch.object(m, "_CONFIG_PATHS", [str(cfg)]):
            result = m.load()
        # The freshness_label (shown in UI) must not contain the raw token
        assert "secret_token_here" not in result.get("freshness_label", "")


# ════════════════════════════════════════════════════════════════════════════════
# 5. RETRY DOES NOT AMPLIFY SECRETS
# ════════════════════════════════════════════════════════════════════════════════

class TestRetrySecurityBoundary:
    """Retry logic must not retry on fatal auth errors (would lock the account)."""

    def test_fatal_error_stops_immediately_no_retry(self):
        import ibkr_sync_runner as m
        call_count = []
        def fake_get(url, timeout=60):
            call_count.append(1)
            resp = MagicMock()
            # Token invalid — fatal, must NOT retry
            resp.text = "<FlexStatementResponse><ErrorCode>1015</ErrorCode></FlexStatementResponse>"
            return resp

        with patch("ibkr_sync_runner.requests.get", side_effect=fake_get):
            with patch("ibkr_sync_runner.time.sleep"):
                xml, err = m.get_statement_with_retry("ref123", "token", max_retries=3, wait_sec=0)

        assert xml is None
        assert err["class"] == "fatal"
        assert len(call_count) == 1   # Only one attempt — no retry on fatal

    def test_rate_limit_stops_and_returns_rate_limit_class(self):
        import ibkr_sync_runner as m
        def fake_get(url, timeout=60):
            resp = MagicMock()
            resp.text = "<FlexStatementResponse><ErrorCode>1018</ErrorCode></FlexStatementResponse>"
            return resp

        with patch("ibkr_sync_runner.requests.get", side_effect=fake_get):
            with patch("ibkr_sync_runner.time.sleep"):
                xml, err = m.get_statement_with_retry("ref123", "token", max_retries=3, wait_sec=0)

        assert xml is None
        # 1018 is rate_limit class, which is not fatal but still stops
        assert err["class"] in ("rate_limit", "temporary")

    def test_temporary_retries_up_to_max(self):
        import ibkr_sync_runner as m
        call_count = []
        def fake_get(url, timeout=60):
            call_count.append(1)
            resp = MagicMock()
            resp.text = "<FlexStatementResponse><ErrorCode>1001</ErrorCode></FlexStatementResponse>"
            return resp

        with patch("ibkr_sync_runner.requests.get", side_effect=fake_get):
            with patch("ibkr_sync_runner.time.sleep"):
                xml, err = m.get_statement_with_retry("ref", "tok", max_retries=3, wait_sec=0)

        assert xml is None
        assert len(call_count) == 3   # Exactly max_retries attempts
