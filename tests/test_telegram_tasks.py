"""
Tests for telegram_tasks.py — the Open Tasks (Action-Items) Telegram UX.

Covers OPEN_TASKS_UX_DESIGN: keyboard build, grouping/sort order, done/skip/
note callbacks, the P0-skip-requires-typed-reason gate, ALGO/info-only
non-tappable rows, and edge states (empty / infra error).

Uses the same patch.object-on-the-real-module pattern as
test_telegram_stop_promote.py so it works even when telegram_tasks was
pre-imported via telegram_bot.
"""
import sys, os, types as py_types
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for mod in ["telebot", "supabase", "dotenv", "ibkr_sync_runner"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

_tb_mod = sys.modules["telebot"]


class _FIMarkup:
    def __init__(self, *a, **k): self.buttons = []
    def add(self, *btns): self.buttons.extend(btns)


class _FIButton:
    def __init__(self, text="", callback_data=None, *a, **k):
        self.text = text
        self.callback_data = callback_data or ""


_existing = getattr(_tb_mod, "types", None)
if _existing is None or not isinstance(
    getattr(_existing, "InlineKeyboardMarkup", None), type
):
    _tbt2 = py_types.ModuleType("telebot.types")
    _tbt2.InlineKeyboardMarkup = _FIMarkup
    _tbt2.InlineKeyboardButton = _FIButton
    _tbt2.ReplyKeyboardMarkup = _FIMarkup
    _tbt2.KeyboardButton = _FIButton
    _tbt2.ReplyKeyboardRemove = _FIMarkup
    _tb_mod.types = _tbt2
    sys.modules["telebot.types"] = _tbt2

if "bot_core" not in sys.modules:
    _bc = py_types.ModuleType("bot_core")
    _bc.bot = MagicMock()
    _bc.supabase = MagicMock()
    _bc.user_state = {}
    _bc.RTL = "‏"
    _bc.TOKEN = ""
    _bc.ADMIN_ID = ""
    sys.modules["bot_core"] = _bc

import engine_core as ec
import open_tasks
import telegram_tasks as tt  # noqa


class _StubTypes:
    InlineKeyboardMarkup = _FIMarkup
    InlineKeyboardButton = _FIButton
    ReplyKeyboardMarkup = _FIMarkup
    KeyboardButton = _FIButton
    ReplyKeyboardRemove = _FIMarkup


_NOW = datetime(2026, 5, 15, 16, 42, tzinfo=timezone.utc)


def _task(state, *, symbol, campaign_id, idx_ts="2026-05-15T16:42:00+00:00"):
    entry = open_tasks._RULESET[state][0]
    return open_tasks.Task(
        task_type=entry.task_type,
        campaign_id=campaign_id,
        symbol=symbol,
        urgency=entry.urgency,
        trigger_snapshot=open_tasks.TriggerSnapshot(
            state=state, open_r=1.5, age_days=9.0, reason="r"),
        recommended_action=entry.action_he,
        status=open_tasks.STATUS_OPEN,
        info_only=entry.info_only,
        notes=[],
        created_ts=idx_ts,
    )


_fake_bot = MagicMock()


def _setup_msg():
    msg = MagicMock()
    msg.message_id = 7
    _fake_bot.send_message.return_value = msg


# ── build_tasks_keyboard / grouping ───────────────────────────────────────────

class TestKeyboard:
    def test_one_tappable_row_per_actionable_plus_controls(self):
        tasks = [
            _task(ec.POSITION_STATE_BROKEN, symbol="NVDA", campaign_id="NVDA_1"),
            _task(ec.POSITION_STATE_YELLOW_FLAG, symbol="MSFT",
                  campaign_id="MSFT_1"),
        ]
        with patch.object(tt, "types", _StubTypes):
            kb = tt.build_tasks_keyboard(tasks)
        picks = [b for b in kb.buttons if b.callback_data.startswith("task_open|")]
        assert len(picks) == 2
        # + refresh + close
        assert any(b.callback_data == "task_refresh" for b in kb.buttons)
        assert any(b.callback_data == "cancel_action" for b in kb.buttons)

    def test_algo_info_only_is_non_tappable_noop(self):
        tasks = [_task(ec.POSITION_STATE_ALGO_OBSERVED, symbol="SPY",
                       campaign_id="SPY_1")]
        with patch.object(tt, "types", _StubTypes):
            kb = tt.build_tasks_keyboard(tasks)
        algo = [b for b in kb.buttons if "SPY" in b.text][0]
        assert algo.callback_data == "task_algo_noop"
        assert not any(b.callback_data.startswith("task_open|")
                       for b in kb.buttons)

    def test_grouped_sorted_p0_first_then_symbol(self):
        tasks = [
            _task(ec.POSITION_STATE_YELLOW_FLAG, symbol="ZZZ",
                  campaign_id="Z_1"),                       # P2
            _task(ec.POSITION_STATE_BROKEN, symbol="MMM",
                  campaign_id="M_1"),                       # P0
            _task(ec.POSITION_STATE_YELLOW_FLAG, symbol="AAA",
                  campaign_id="A_1"),                       # P2
        ]
        ordered = tt._grouped_sorted(tasks)
        assert ordered[0].urgency == "P0"                   # P0 first
        # then P2 alphabetical by symbol
        assert [t.symbol for t in ordered[1:]] == ["AAA", "ZZZ"]

    def test_sort_oldest_first_within_symbol(self):
        new = _task(ec.POSITION_STATE_YELLOW_FLAG, symbol="CAT",
                    campaign_id="C_2", idx_ts="2026-05-15T18:00:00+00:00")
        old = _task(ec.POSITION_STATE_YELLOW_FLAG, symbol="CAT",
                    campaign_id="C_1", idx_ts="2026-05-15T09:00:00+00:00")
        ordered = tt._grouped_sorted([new, old])
        assert ordered[0].campaign_id == "C_1"  # oldest unattended first


# ── entry / edge states ───────────────────────────────────────────────────────

class TestEntry:
    def _run(self, load_return):
        _fake_bot.reset_mock()
        _setup_msg()
        state = {}
        with patch.object(tt, "types", _StubTypes), \
             patch.object(tt, "bot", _fake_bot), \
             patch.object(tt, "user_state", state), \
             patch.object(tt, "_load_tasks", lambda cid: load_return):
            tt.handle_open_tasks_entry(5001)
        return [c.args[1] for c in _fake_bot.send_message.call_args_list]

    def test_empty_state(self):
        msgs = self._run(([], "live", None))
        assert any("אין משימות פתוחות" in m for m in msgs)

    def test_infra_error_says_absence_is_not_no_tasks(self):
        msgs = self._run(([], "live", "RuntimeError: boom"))
        joined = "\n".join(msgs)
        assert "אומר שאין" in joined  # "זה *לא* אומר שאין" (markdown emphasis)
        assert "boom" in joined

    def test_list_header_has_count_and_data_label(self):
        tasks = [_task(ec.POSITION_STATE_BROKEN, symbol="NVDA",
                       campaign_id="NVDA_1")]
        msgs = self._run((tasks, "live", None))
        assert any("משימות פתוחות" in m and "חי 🟢" in m for m in msgs)

    def test_stale_data_warns(self):
        tasks = [_task(ec.POSITION_STATE_BROKEN, symbol="NVDA",
                       campaign_id="NVDA_1")]
        msgs = self._run((tasks, "stale", None))
        assert any("אמת מול IBKR" in m for m in msgs)

    def test_algo_only_renders_info_screen(self):
        tasks = [_task(ec.POSITION_STATE_ALGO_OBSERVED, symbol="SPY",
                       campaign_id="SPY_1")]
        msgs = self._run((tasks, "live", None))
        assert any("מעקב בלבד" in m for m in msgs)


# ── done / skip / note callbacks ──────────────────────────────────────────────

def _rec(urgency="P2", state=ec.POSITION_STATE_YELLOW_FLAG):
    return {
        "campaign_id": "CAT_1", "task_type": "REVIEW_YELLOW_FLAG",
        "symbol": "CAT", "urgency": urgency, "info_only": False,
        "recommended_action": "בדוק חריגה", "state": state,
        "open_r": 1.2, "age_days": 9.0, "reason": "yf",
    }


class TestActions:
    def _ctx(self, records, **patches):
        _fake_bot.reset_mock()
        _setup_msg()
        state = {6001: {"task_records": records}}
        base = dict(bot=_fake_bot, user_state=state, types=_StubTypes,
                    supabase=MagicMock())
        base.update(patches)
        cms = [patch.object(tt, k, v) for k, v in base.items()]
        for c in cms:
            c.start()
        return state, cms

    def _stop(self, cms):
        for c in cms:
            c.stop()

    def test_done_shows_default_safe_confirm(self):
        state, cms = self._ctx([_rec()])
        try:
            tt.handle_task_done(6001, 0)
        finally:
            self._stop(cms)
        kb = _fake_bot.send_message.call_args.kwargs["reply_markup"]
        cbs = {b.callback_data for b in kb.buttons}
        assert "task_done_confirm|0|yes" in cbs
        assert "task_done_confirm|0|no" in cbs

    def test_done_confirm_yes_calls_mark_done(self):
        called = {}
        state, cms = self._ctx([_rec()])
        try:
            with patch.object(open_tasks, "mark_done",
                              lambda *a, **k: called.setdefault("done", (a, k)) or True):
                tt.handle_task_done_confirm(6001, 0, True)
        finally:
            self._stop(cms)
        assert "done" in called
        assert called["done"][0][1:3] == ("CAT_1", "REVIEW_YELLOW_FLAG")

    def test_done_confirm_no_does_not_mark(self):
        called = {}
        state, cms = self._ctx([_rec()])
        try:
            with patch.object(open_tasks, "mark_done",
                              lambda *a, **k: called.setdefault("x", 1)):
                tt.handle_task_done_confirm(6001, 0, False)
        finally:
            self._stop(cms)
        assert "x" not in called

    def test_p1_p3_skip_is_single_confirm(self):
        state, cms = self._ctx([_rec(urgency="P2")])
        try:
            tt.handle_task_skip(6001, 0)
        finally:
            self._stop(cms)
        kb = _fake_bot.send_message.call_args.kwargs["reply_markup"]
        cbs = {b.callback_data for b in kb.buttons}
        assert "task_skip_confirm|0|yes" in cbs
        # P2 must NOT enter the typed-reason state machine
        assert state[6001].get("action") != "task_skip_reason"

    def test_p0_skip_requires_typed_reason_gate(self):
        rec = _rec(urgency="P0", state=ec.POSITION_STATE_BROKEN)
        rec["task_type"] = "EXECUTE_EXIT"
        state, cms = self._ctx([rec])
        try:
            tt.handle_task_skip(6001, 0)
        finally:
            self._stop(cms)
        # Sets the free-text capture state — NOT a one-tap confirm.
        assert state[6001]["action"] == "task_skip_reason"
        assert state[6001]["task_idx"] == 0
        txt = _fake_bot.send_message.call_args.args[1]
        assert "דורש סיבה מפורשת" in txt

    def test_p0_skip_empty_reason_reprompts_does_not_skip(self):
        rec = _rec(urgency="P0", state=ec.POSITION_STATE_BROKEN)
        rec["task_type"] = "EXECUTE_EXIT"
        state, cms = self._ctx(
            [rec],
        )
        state[6001]["action"] = "task_skip_reason"
        state[6001]["task_idx"] = 0
        skipped = {}
        try:
            with patch.object(open_tasks, "skip_task",
                              lambda *a, **k: skipped.setdefault("s", 1)):
                tt.handle_task_skip_reason(6001, "   ")
        finally:
            self._stop(cms)
        assert "s" not in skipped  # never skipped on blank reason
        txt = _fake_bot.send_message.call_args.args[1]
        assert "ריקה אינה מתקבלת" in txt

    def test_p0_skip_with_reason_records_skipped_critical_exit(self):
        rec = _rec(urgency="P0", state=ec.POSITION_STATE_BROKEN)
        rec["task_type"] = "EXECUTE_EXIT"
        state, cms = self._ctx([rec])
        state[6001]["action"] = "task_skip_reason"
        state[6001]["task_idx"] = 0
        captured = {}
        try:
            with patch.object(
                open_tasks, "skip_task",
                lambda *a, **k: captured.update(a=a, k=k) or True
            ), patch.object(tt, "handle_open_tasks_entry", lambda c: None):
                tt.handle_task_skip_reason(6001, "exited manually at IBKR")
        finally:
            self._stop(cms)
        assert captured["k"]["urgency"] == "P0"
        assert captured["k"]["note"] == "exited manually at IBKR"
        assert 6001 not in state or state[6001].get("action") != "task_skip_reason"

    def test_add_note_sets_free_text_capture(self):
        state, cms = self._ctx([_rec()])
        try:
            tt.handle_task_note(6001, 0)
        finally:
            self._stop(cms)
        assert state[6001]["action"] == "task_add_note"
        assert state[6001]["task_idx"] == 0

    def test_add_note_text_appends_via_engine_api(self):
        state, cms = self._ctx([_rec()])
        state[6001]["action"] = "task_add_note"
        state[6001]["task_idx"] = 0
        captured = {}
        try:
            with patch.object(
                open_tasks, "add_note",
                lambda *a, **k: captured.update(a=a) or True
            ), patch.object(tt, "handle_task_open", lambda c, i: None):
                tt.handle_task_add_note(6001, "watching for MA50 reclaim")
        finally:
            self._stop(cms)
        assert captured["a"][1:4] == ("CAT_1", "REVIEW_YELLOW_FLAG",
                                      "watching for MA50 reclaim")

    def test_expired_record_reopens_list(self):
        state, cms = self._ctx([])  # no records
        try:
            with patch.object(tt, "handle_open_tasks_entry",
                              lambda c: _fake_bot.send_message(c, "REOPEN")):
                tt.handle_task_open(6001, "0")
        finally:
            self._stop(cms)
        assert any("REOPEN" in str(c.args)
                   for c in _fake_bot.send_message.call_args_list)


# ── info-only detail card never shows an action verb ──────────────────────────

class TestInfoOnlyDetail:
    def test_algo_detail_has_no_action_buttons(self):
        _fake_bot.reset_mock()
        _setup_msg()
        rec = {
            "campaign_id": "SPY_1", "task_type": "ALGO_OBSERVE_ONLY",
            "symbol": "SPY", "urgency": "P3", "info_only": True,
            "recommended_action": "‏🤖 ALGO — בקרה בלבד.",
            "state": ec.POSITION_STATE_ALGO_OBSERVED,
            "open_r": None, "age_days": 3.0, "reason": "algo",
        }
        state = {7001: {"task_records": [rec]}}
        with patch.object(tt, "types", _StubTypes), \
             patch.object(tt, "bot", _fake_bot), \
             patch.object(tt, "user_state", state):
            tt.handle_task_open(7001, 0)
        kb = _fake_bot.send_message.call_args.kwargs["reply_markup"]
        cbs = {b.callback_data for b in kb.buttons}
        assert not any(c.startswith("task_done|") for c in cbs)
        assert not any(c.startswith("task_skip|") for c in cbs)
        assert "task_open|list" in cbs
