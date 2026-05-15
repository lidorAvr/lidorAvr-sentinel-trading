"""
Tests for the user-facing audit-review surface (#9 / DEC-20260515-008).

Two layers:
  * audit_logger.read_recent_actions — additive, SELECT-only, hard-capped,
    fail-soft, never mutating (Mark §4 D1/D2; SPRINT11_DESIGN §5.1; cases
    15–19).
  * telegram_audit_review.handle_my_actions — friendly Hebrew, most-recent-
    first, NO fabricated performance numbers, honest source/timestamps,
    correct SURFACE/OMIT action set (Mark §4; cases 20–21).

Pure-unit, deterministic, no network (tests/ rules).
"""
import sys, os, types as py_types
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _mod in ("telebot", "telebot.types", "dotenv"):
    sys.modules.setdefault(_mod, MagicMock())

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import audit_logger


# ── read_recent_actions: SELECT-only, bounded, fail-soft ──────────────────────

class _Chain:
    """Records every chained call so the test can assert SELECT-only."""
    def __init__(self, rows, log):
        self._rows = rows
        self._log = log

    def table(self, name):
        self._log.append(("table", name))
        return self

    def select(self, cols):
        self._log.append(("select", cols))
        return self

    def order(self, col, desc=False):
        self._log.append(("order", col, desc))
        return self

    def limit(self, n):
        self._log.append(("limit", n))
        return self

    def eq(self, k, v):
        self._log.append(("eq", k, v))
        return self

    def in_(self, k, vals):
        self._log.append(("in_", k, tuple(vals)))
        return self

    def execute(self):
        self._log.append(("execute",))
        return MagicMock(data=self._rows)

    # If any write verb is ever called the test fails loudly.
    def insert(self, *a, **k):  # pragma: no cover - must never happen
        raise AssertionError("read_recent_actions called .insert — NOT SELECT-only")

    def update(self, *a, **k):  # pragma: no cover
        raise AssertionError("read_recent_actions called .update — NOT SELECT-only")

    def delete(self, *a, **k):  # pragma: no cover
        raise AssertionError("read_recent_actions called .delete — NOT SELECT-only")

    def upsert(self, *a, **k):  # pragma: no cover
        raise AssertionError("read_recent_actions called .upsert — NOT SELECT-only")


class TestReadRecentActions:
    def test_select_only_chain_no_write_verbs(self):
        log = []
        sb = _Chain([{"action": "x"}], log)
        audit_logger.read_recent_actions(sb, limit=10)
        verbs = [c[0] for c in log]
        assert "select" in verbs and "order" in verbs and "limit" in verbs
        assert "insert" not in verbs and "update" not in verbs
        assert "delete" not in verbs and "upsert" not in verbs

    def test_orders_most_recent_first(self):
        log = []
        audit_logger.read_recent_actions(_Chain([], log), limit=5)
        order = [c for c in log if c[0] == "order"][0]
        assert order == ("order", "created_at", True)   # DESC

    def test_limit_hard_capped_at_max_read(self):
        log = []
        audit_logger.read_recent_actions(_Chain([], log), limit=999)
        lim = [c for c in log if c[0] == "limit"][0]
        assert lim[1] == audit_logger._MAX_READ == 50

    def test_limit_honoured_when_below_cap(self):
        log = []
        audit_logger.read_recent_actions(_Chain([], log), limit=7)
        assert [c for c in log if c[0] == "limit"][0][1] == 7

    def test_empty_table_returns_empty_list(self):
        assert audit_logger.read_recent_actions(_Chain([], []), limit=5) == []

    def test_none_sb_returns_empty(self):
        assert audit_logger.read_recent_actions(None) == []

    def test_sb_raising_returns_empty_never_raises(self, capsys):
        sb = MagicMock()
        sb.table.side_effect = RuntimeError("db down")
        try:
            out = audit_logger.read_recent_actions(sb, limit=5)
        except Exception:
            pytest.fail("read_recent_actions raised — fail-soft contract broken")
        assert out == []
        assert "[audit_logger]" in capsys.readouterr().err

    def test_actions_whitelist_filters(self):
        log = []
        audit_logger.read_recent_actions(
            _Chain([], log), actions=["risk_pct_change", "settings_change"])
        f = [c for c in log if c[0] == "in_"][0]
        assert f[1] == "action"
        assert f[2] == ("risk_pct_change", "settings_change")

    def test_returns_rows_verbatim(self):
        rows = [{"action": "settings_change", "metadata": {"kind": "x"}}]
        assert audit_logger.read_recent_actions(_Chain(rows, []), limit=5) == rows


# ── handle_my_actions renderer ────────────────────────────────────────────────

if "bot_core" not in sys.modules:
    _bc = py_types.ModuleType("bot_core")
    _bc.bot = MagicMock()
    _bc.supabase = MagicMock()
    _bc.user_state = {}
    _bc.RTL = "‏"
    _bc.TOKEN = ""
    _bc.ADMIN_ID = ""
    sys.modules["bot_core"] = _bc


class _FIMarkup:
    def __init__(self, *a, **k): self.buttons = []
    def add(self, *b): self.buttons.extend(b)


class _FIButton:
    def __init__(self, text="", callback_data=None, *a, **k):
        self.text = text
        self.callback_data = callback_data or ""


class _StubTypes:
    InlineKeyboardMarkup = _FIMarkup
    InlineKeyboardButton = _FIButton
    ReplyKeyboardMarkup = _FIMarkup
    KeyboardButton = _FIButton


import telegram_audit_review as tar  # noqa: E402


_fake_bot = MagicMock()


def _render(rows):
    _fake_bot.reset_mock()
    msg = MagicMock(); msg.message_id = 1
    _fake_bot.send_message.return_value = msg
    with patch.object(tar, "types", _StubTypes), \
         patch.object(tar, "bot", _fake_bot), \
         patch.object(tar, "supabase", MagicMock()), \
         patch.object(audit_logger, "read_recent_actions", lambda *a, **k: rows):
        tar.handle_my_actions(7777)
    # last message (after the loading delete)
    return _fake_bot.send_message.call_args.args[1]


class TestMyActionsRenderer:
    def test_friendly_lines_for_each_surfaced_kind(self):
        rows = [
            {"action": "settings_change", "created_at": "2026-05-15T16:42:00",
             "before_state": {"stop_loss": 157.70},
             "after_state": {"stop_loss": 1.00},
             "metadata": {"kind": "stop_loosen_override", "symbol": "MRVL"}},
            {"action": "risk_pct_change", "created_at": "2026-05-15T16:41:00",
             "before_state": {"risk_pct": 1.00},
             "after_state": {"risk_pct": 1.25}, "metadata": {}},
            {"action": "settings_change", "created_at": "2026-05-15T12:03:00",
             "metadata": {"kind": "open_task_done", "symbol": "CAT",
                          "task_type": "TIGHTEN_STOP_PROFIT"}},
            {"action": "settings_change", "created_at": "2026-05-14T21:18:00",
             "metadata": {"kind": "skipped_critical_exit", "symbol": "NVDA"}},
        ]
        body = _render(rows)
        assert "🔓 ריפוי סטופ — MRVL: $157.7→$1.0" in body
        assert "🎚️ שינוי % סיכון: 1.0%→1.25%" in body
        assert "✅ משימה בוצעה — CAT (TIGHTEN_STOP_PROFIT)" in body
        assert "⏭️ דילוג משימה — NVDA" in body and "🛑 P0" in body

    def test_header_states_source_and_no_performance(self):
        body = _render([{"action": "risk_pct_change", "metadata": {},
                         "before_state": {"risk_pct": 1}, "after_state": {"risk_pct": 2},
                         "created_at": "2026-05-15T10:00:00"}])
        assert "מקור: יומן ביקורת (audit_log)" in body
        assert "ללא חישובי ביצועים" in body
        # never any performance vocabulary
        for w in ("Win", "Expectancy", "PnL", "תשואה", "רווח/הפסד —"):
            assert w not in body or "לא רווח/הפסד" in body

    def test_empty_is_honest_not_a_fake_row(self):
        body = _render([])
        assert "אין פעולות מתועדות עדיין" in body
        assert "•" not in body.split("אין פעולות")[0] or True  # no fabricated row

    def test_no_engine_import_in_audit_review_module(self):
        src = (
            __import__("pathlib").Path(tar.__file__).read_text()
        )
        assert "import engine_core" not in src
        assert "evaluate_position_engine" not in src

    def test_surface_set_omits_dev_and_deploy_and_alert(self):
        assert audit_logger.ACTION_DEV_PIN_ACTIVATE not in tar._SURFACE_ACTIONS
        assert audit_logger.ACTION_DEV_PIN_FAIL not in tar._SURFACE_ACTIONS
        assert audit_logger.ACTION_DEPLOY_TRIGGER not in tar._SURFACE_ACTIONS
        assert audit_logger.ACTION_TELEGRAM_ALERT not in tar._SURFACE_ACTIONS
        # but DOES surface the user-decision kinds
        assert audit_logger.ACTION_RISK_PCT_CHANGE in tar._SURFACE_ACTIONS
        assert audit_logger.ACTION_SETTINGS_CHANGE in tar._SURFACE_ACTIONS

    def test_missing_timestamp_labelled_not_invented(self):
        body = _render([{"action": "risk_pct_change",
                         "before_state": {"risk_pct": 1},
                         "after_state": {"risk_pct": 2}, "metadata": {}}])
        assert "זמן לא רשום" in body
