"""
RISK-1c — admin-triggered retroactive at-entry-lock backfill.

Tests pinned in this file:
  A. preview_missing_locks — counts every NULL-locked BUY, splits by
     lockable / anomalous-price, groups by symbol. Read-only; no mutation.
  B. run_backfill — orchestrates per-row locks via the EXISTING
     repo.lock_entry_from_trade_price helper (method='backfill'), captures
     summary counts, writes ONE ACTION_AT_ENTRY_BACKFILL_RUN audit row.
     Idempotent + fail-soft per-row; never raises.
  C. Formatter byte-shape — Hebrew RTL preview / result lines.
  D. Backwards compatibility — lock_entry_from_trade_price's new `method`
     kwarg defaults to 'wizard' so every existing RISK-1b call site is
     byte-identical.
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Pre-stub sandbox-unimportable modules; never overwrite anything the real
# tests rely on.
for mod in ("telebot", "supabase", "dotenv"):
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import audit_logger  # noqa: E402
import risk1c_backfill as r1c  # noqa: E402
import supabase_repository as repo  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# A. preview_missing_locks — read-only triage
# ════════════════════════════════════════════════════════════════════════════

class TestPreviewMissingLocks:
    def test_empty_db_returns_zero_shape(self):
        with patch.object(repo, "get_trades_missing_lock", return_value=[]):
            p = r1c.preview_missing_locks(MagicMock())
        assert p["total"] == 0
        assert p["lockable_count"] == 0
        assert p["anomalous_count"] == 0
        assert p["by_symbol"] == {}
        assert p["anomalous_symbols"] == []
        assert p["fetch_error"] is False

    def test_classifies_lockable_vs_anomalous(self):
        rows = [
            {"trade_id": "T1", "symbol": "AAPL", "price": 150.0},
            {"trade_id": "T2", "symbol": "AAPL", "price": 152.0},
            {"trade_id": "T3", "symbol": "MSFT", "price": 0.0},          # anomalous: zero
            {"trade_id": "T4", "symbol": "TSLA", "price": -5.0},         # anomalous: negative
            {"trade_id": "T5", "symbol": "PLTR", "price": None},         # anomalous: none
            {"trade_id": "T6", "symbol": "NVDA", "price": "abc"},        # anomalous: non-numeric
            {"trade_id": "T7", "symbol": "AAPL", "price": "148.5"},      # lockable: numeric-string
        ]
        with patch.object(repo, "get_trades_missing_lock", return_value=rows):
            p = r1c.preview_missing_locks(MagicMock())
        assert p["total"] == 7
        assert p["lockable_count"] == 3  # AAPL x2 + AAPL numeric-string
        assert p["anomalous_count"] == 4
        assert p["by_symbol"] == {"AAPL": 3}
        assert set(p["anomalous_symbols"]) == {"MSFT", "TSLA", "PLTR", "NVDA"}
        assert p["fetch_error"] is False

    def test_fetch_error_returns_honest_zero_shape(self):
        # When Supabase is unreachable, the preview reports the failure honestly
        # rather than crashing the operator's button click.
        def _raise(*_a, **_kw):
            raise RuntimeError("supabase unreachable")
        with patch.object(repo, "get_trades_missing_lock", side_effect=_raise):
            p = r1c.preview_missing_locks(MagicMock())
        assert p["fetch_error"] is True
        assert p["total"] == 0
        assert p["lockable_count"] == 0

    def test_missing_symbol_falls_back_to_question_mark(self):
        rows = [{"trade_id": "T1", "symbol": None, "price": 100.0}]
        with patch.object(repo, "get_trades_missing_lock", return_value=rows):
            p = r1c.preview_missing_locks(MagicMock())
        assert p["by_symbol"] == {"?": 1}


# ════════════════════════════════════════════════════════════════════════════
# B. run_backfill — orchestration
# ════════════════════════════════════════════════════════════════════════════

class TestRunBackfillHappyPath:
    def test_locks_every_lockable_row(self):
        rows = [
            {"trade_id": "T1", "symbol": "AAPL", "price": 150.0},
            {"trade_id": "T2", "symbol": "AAPL", "price": 152.0},
            {"trade_id": "T3", "symbol": "MSFT", "price": 300.0},
        ]
        sb = MagicMock()
        with patch.object(repo, "get_trades_missing_lock", return_value=rows), \
             patch.object(repo, "lock_entry_from_trade_price",
                          return_value=True) as mock_lock, \
             patch.object(audit_logger, "log_action", return_value=True) as mock_audit:
            result = r1c.run_backfill(sb, chat_id=12345)

        assert result["locked"] == 3
        assert result["skipped_anomaly"] == 0
        assert result["skipped_other"] == 0
        assert result["total_processed"] == 3
        assert result["by_symbol"] == {"AAPL": 2, "MSFT": 1}
        assert result["fetch_error"] is False
        # Every per-row lock got method='backfill' (NOT 'wizard'); the chat_id
        # is propagated so the per-row audit rows tie back to the operator.
        for call in mock_lock.call_args_list:
            assert call.kwargs.get("method") == "backfill"
            assert call.kwargs.get("chat_id") == 12345
        # Exactly ONE batch-level audit row (per-row audits are inside the
        # repo helper, NOT counted here).
        batch_calls = [c for c in mock_audit.call_args_list
                       if c.args[1] == audit_logger.ACTION_AT_ENTRY_BACKFILL_RUN]
        assert len(batch_calls) == 1
        metadata = batch_calls[0].kwargs["metadata"]
        assert metadata["locked"] == 3
        assert metadata["total_processed"] == 3
        assert metadata["outcome"] == "success"


class TestRunBackfillFailSoft:
    def test_anomalous_price_row_counts_as_anomaly_skip(self):
        rows = [
            {"trade_id": "T1", "symbol": "AAPL", "price": 150.0},   # lockable
            {"trade_id": "T2", "symbol": "MSFT", "price": 0.0},     # anomaly
        ]
        # The repo helper returns False for the anomalous row; we classify
        # that as skipped_anomaly via the pre-check in run_backfill.
        def _lock_side_effect(_sb, trade_id, **_kw):
            return trade_id == "T1"
        with patch.object(repo, "get_trades_missing_lock", return_value=rows), \
             patch.object(repo, "lock_entry_from_trade_price",
                          side_effect=_lock_side_effect), \
             patch.object(audit_logger, "log_action", return_value=True):
            result = r1c.run_backfill(MagicMock())

        assert result["locked"] == 1
        assert result["skipped_anomaly"] == 1
        assert result["skipped_other"] == 0
        assert result["by_symbol"] == {"AAPL": 1}

    def test_already_locked_returns_false_counts_as_other_skip(self):
        # When the helper returns False but the row's price IS valid (e.g.
        # a concurrent wizard already locked it), it's counted as "other".
        rows = [{"trade_id": "T1", "symbol": "AAPL", "price": 150.0}]
        with patch.object(repo, "get_trades_missing_lock", return_value=rows), \
             patch.object(repo, "lock_entry_from_trade_price",
                          return_value=False), \
             patch.object(audit_logger, "log_action", return_value=True):
            result = r1c.run_backfill(MagicMock())

        assert result["locked"] == 0
        assert result["skipped_anomaly"] == 0
        assert result["skipped_other"] == 1

    def test_missing_trade_id_skipped_as_other(self):
        rows = [{"trade_id": None, "symbol": "X", "price": 100.0}]
        with patch.object(repo, "get_trades_missing_lock", return_value=rows), \
             patch.object(repo, "lock_entry_from_trade_price",
                          return_value=True) as mock_lock, \
             patch.object(audit_logger, "log_action", return_value=True):
            result = r1c.run_backfill(MagicMock())
        # The helper must NOT be called when trade_id is missing.
        mock_lock.assert_not_called()
        assert result["locked"] == 0
        assert result["skipped_other"] == 1

    def test_fetch_error_returns_zero_shape_and_audits_attempt(self):
        # When Supabase is unreachable on the fetch, we still audit that the
        # operator pressed "confirm" — the record matters for compliance.
        with patch.object(repo, "get_trades_missing_lock",
                          side_effect=RuntimeError("unreachable")), \
             patch.object(audit_logger, "log_action", return_value=True) as mock_audit:
            result = r1c.run_backfill(MagicMock(), chat_id=7777)

        assert result["fetch_error"] is True
        assert result["locked"] == 0
        assert result["total_processed"] == 0
        # The batch audit row IS written with outcome=fetch_error.
        batch_calls = [c for c in mock_audit.call_args_list
                       if c.args[1] == audit_logger.ACTION_AT_ENTRY_BACKFILL_RUN]
        assert len(batch_calls) == 1
        assert batch_calls[0].kwargs["chat_id"] == 7777
        assert batch_calls[0].kwargs["metadata"]["outcome"] == "fetch_error"


class TestRunBackfillIdempotent:
    def test_re_running_after_full_success_is_a_no_op(self):
        # Second run: get_trades_missing_lock returns [] (everything is
        # already locked) ⇒ zero locks, zero skips, no per-row helper call.
        with patch.object(repo, "get_trades_missing_lock", return_value=[]), \
             patch.object(repo, "lock_entry_from_trade_price",
                          return_value=False) as mock_lock, \
             patch.object(audit_logger, "log_action", return_value=True):
            result = r1c.run_backfill(MagicMock())
        mock_lock.assert_not_called()
        assert result["locked"] == 0
        assert result["total_processed"] == 0


# ════════════════════════════════════════════════════════════════════════════
# C. Formatters — Hebrew RTL operator-facing screens
# ════════════════════════════════════════════════════════════════════════════

class TestFormatPreview:
    def test_fetch_error_message_disclosed(self):
        s = r1c.format_preview({"fetch_error": True})
        assert "שגיאה" in s
        assert "Supabase" in s

    def test_zero_total_shows_all_clean(self):
        s = r1c.format_preview({
            "total": 0, "lockable_count": 0, "anomalous_count": 0,
            "by_symbol": {}, "anomalous_symbols": [], "fetch_error": False,
        })
        assert "כבר נעול" in s

    def test_real_preview_shows_counts_and_per_symbol(self):
        s = r1c.format_preview({
            "total": 152, "lockable_count": 150, "anomalous_count": 2,
            "by_symbol": {"AAPL": 30, "MSFT": 25, "TSLA": 20},
            "anomalous_symbols": ["BADA", "BADB"],
            "fetch_error": False,
        })
        assert "152" in s
        assert "150" in s
        assert "AAPL" in s
        assert "MSFT" in s
        assert "TSLA" in s
        # Anomaly disclosure
        assert "2" in s
        assert "BADA" in s
        # Irreversibility caveat present
        assert "בלתי-הפיכה" in s

    def test_caps_per_symbol_at_12(self):
        # 15 symbols → first 12 shown, then a "+3 more" summary.
        by_sym = {f"SYM{i:02d}": 1 for i in range(15)}
        s = r1c.format_preview({
            "total": 15, "lockable_count": 15, "anomalous_count": 0,
            "by_symbol": by_sym, "anomalous_symbols": [], "fetch_error": False,
        })
        # 15-12 = 3 more symbols, 3 more rows.
        assert "+3" in s or "3 סימולים" in s


class TestFormatResult:
    def test_success_with_skips_disclosed(self):
        s = r1c.format_result({
            "locked": 150, "skipped_anomaly": 2, "skipped_other": 0,
            "by_symbol": {"AAPL": 30, "MSFT": 25},
            "total_processed": 152, "fetch_error": False,
        })
        assert "150" in s
        assert "ננעלו" in s or "נעלו" in s
        assert "2" in s  # anomaly count
        assert "AAPL" in s
        # Forward-looking note — what changes for the founder.
        assert "/portfolio" in s

    def test_fetch_error_result_message(self):
        s = r1c.format_result({"fetch_error": True})
        assert "שגיאה" in s
        assert "אין שינוי" in s


# ════════════════════════════════════════════════════════════════════════════
# D. Backwards compatibility — lock_entry_from_trade_price `method` kwarg
# ════════════════════════════════════════════════════════════════════════════

class TestLockEntryMethodKwarg:
    """The `method` kwarg added in RISK-1c must default to 'wizard' so every
    existing RISK-1b call site is byte-identical (no caller change required)."""

    def test_method_kwarg_default_is_wizard(self):
        import inspect
        sig = inspect.signature(repo.lock_entry_from_trade_price)
        assert "method" in sig.parameters
        assert sig.parameters["method"].default == "wizard"

    def test_method_propagates_to_set_locked_entry_and_audit(self):
        sb = MagicMock()
        # Mock the chained .table().select().eq().limit().execute() chain to
        # return a real row dict.
        execute_result = MagicMock()
        execute_result.data = [{
            "price": 150.0, "locked_entry_price": None, "symbol": "AAPL",
        }]
        sb.table.return_value.select.return_value.eq.return_value \
            .limit.return_value.execute.return_value = execute_result

        with patch.object(repo, "set_locked_entry") as mock_set, \
             patch.object(audit_logger, "log_action",
                          return_value=True) as mock_audit:
            ok = repo.lock_entry_from_trade_price(
                sb, "T1", chat_id=99, method="backfill")

        assert ok is True
        # set_locked_entry receives method='backfill' (not the default wizard).
        assert mock_set.call_args.kwargs["method"] == "backfill"
        # The ACTION_AT_ENTRY_LOCK audit row records method='backfill' in `after`.
        lock_calls = [c for c in mock_audit.call_args_list
                      if c.args[1] == audit_logger.ACTION_AT_ENTRY_LOCK]
        assert len(lock_calls) == 1
        assert lock_calls[0].kwargs["after"]["lock_method"] == "backfill"

    def test_default_method_is_wizard_byte_identical(self):
        # No `method=` kwarg ⇒ everything still routes as 'wizard' (RISK-1b
        # byte-identity guard — the original RISK-1b call site never passes
        # method=).
        sb = MagicMock()
        execute_result = MagicMock()
        execute_result.data = [{
            "price": 100.0, "locked_entry_price": None, "symbol": "X",
        }]
        sb.table.return_value.select.return_value.eq.return_value \
            .limit.return_value.execute.return_value = execute_result

        with patch.object(repo, "set_locked_entry") as mock_set, \
             patch.object(audit_logger, "log_action", return_value=True):
            repo.lock_entry_from_trade_price(sb, "T1", chat_id=42)

        assert mock_set.call_args.kwargs["method"] == "wizard"
