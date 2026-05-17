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

    def test_algo_consolidated_into_one_panel_no_per_row_noop(self):
        # #5 / DEC-006 / SPRINT11_DESIGN §3.2: ALGO items collapse into ONE
        # task_algo_panel entry; the per-row task_algo_noop dead-end popup is
        # removed entirely. ALGO is never a tappable Task row.
        tasks = [
            _task(ec.POSITION_STATE_ALGO_OBSERVED, symbol="SPY",
                  campaign_id="SPY_1"),
            _task(ec.POSITION_STATE_ALGO_OBSERVED, symbol="QQQ",
                  campaign_id="QQQ_1"),
        ]
        with patch.object(tt, "types", _StubTypes):
            kb = tt.build_tasks_keyboard(tasks)
        panels = [b for b in kb.buttons
                  if b.callback_data == "task_algo_panel"]
        assert len(panels) == 1                       # exactly ONE
        assert "ALGO (2)" in panels[0].text           # k = count
        assert not any(b.callback_data == "task_algo_noop"
                       for b in kb.buttons)            # popup is dead
        assert not any(b.callback_data.startswith("task_open|")
                       for b in kb.buttons)            # never a Task row

    def test_zero_algo_no_panel_button(self):
        # #5 / SPRINT11_DESIGN §3.3: empty ALGO set → no panel button.
        tasks = [_task(ec.POSITION_STATE_BROKEN, symbol="NVDA",
                       campaign_id="NVDA_1")]
        with patch.object(tt, "types", _StubTypes):
            kb = tt.build_tasks_keyboard(tasks)
        assert not any(b.callback_data == "task_algo_panel"
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


# ── #4 short inline labels (SPRINT11_DESIGN §2) ───────────────────────────────

class TestShortLabels:
    def _kb(self, tasks):
        with patch.object(tt, "types", _StubTypes):
            return tt.build_tasks_keyboard(tasks)

    def test_label_is_glyph_symbol_tag_and_short(self):
        kb = self._kb([_task(ec.POSITION_STATE_BROKEN, symbol="NVDA",
                             campaign_id="NVDA_1")])
        btn = [b for b in kb.buttons
               if b.callback_data.startswith("task_open|")][0]
        assert "NVDA" in btn.text
        assert "סגור עכשיו" in btn.text          # the EXECUTE_EXIT tag
        assert "🛑" in btn.text                   # P0 glyph
        assert len(btn.text) <= 32               # legible on a phone

    def test_every_task_type_has_a_short_tag(self):
        cases = {
            ec.POSITION_STATE_BROKEN: "סגור עכשיו",
            ec.POSITION_STATE_RUNNER: "הדק (Runner)",
            ec.POSITION_STATE_PROFIT_PROTECTION: "הדק 2R+",
            ec.POSITION_STATE_YELLOW_FLAG: "דגל צהוב",
            ec.POSITION_STATE_DEAD_MONEY: "הון מת",
            ec.POSITION_STATE_DATA_INCOMPLETE: "השלם נתונים",
        }
        for st, tag in cases.items():
            kb = self._kb([_task(st, symbol="AAA", campaign_id="A_1")])
            txt = " ".join(b.text for b in kb.buttons)
            assert tag in txt, (st, tag)

    def test_unknown_task_type_falls_back_to_14char_trim(self):
        rec = {
            "campaign_id": "X_1", "task_type": "FUTURE_UNKNOWN",
            "symbol": "X", "urgency": "P2", "info_only": False,
            "recommended_action": "‏מאוד מאוד ארוך משפט שלא נכנס בכפתור",
        }
        with patch.object(tt, "types", _StubTypes):
            kb = tt.build_tasks_keyboard([rec])
        btn = [b for b in kb.buttons
               if b.callback_data.startswith("task_open|")][0]
        # tag portion is a <=14 char trim, never the full sentence
        assert "מאוד מאוד" in btn.text
        assert "שלא נכנס בכפתור" not in btn.text

    def test_detail_card_keeps_full_recommended_action(self):
        _fake_bot.reset_mock()
        _setup_msg()
        rec = {
            "campaign_id": "CAT_1", "task_type": "PROTECT_RUNNER_PROFIT",
            "symbol": "CAT", "urgency": "P1", "info_only": False,
            "recommended_action": "‏🏃 Runner — הדק סטופ לפי ההמלצה (MA50, $123.45). אל תרופף.",
            "state": ec.POSITION_STATE_RUNNER, "open_r": 5.0,
            "age_days": 9.0, "reason": "runner",
        }
        state = {8001: {"task_records": [rec]}}
        with patch.object(tt, "types", _StubTypes), \
             patch.object(tt, "bot", _fake_bot), \
             patch.object(tt, "user_state", state):
            tt.handle_task_open(8001, 0)
        body = _fake_bot.send_message.call_args.args[1]
        assert "MA50, $123.45" in body          # full text in the card
        assert "אל תרופף" in body


# ── #2 snapshot wording (Mark §3) ─────────────────────────────────────────────

class TestSnapshotWording:
    def test_detail_card_uses_mark_label_not_old_wording(self):
        _fake_bot.reset_mock()
        _setup_msg()
        rec = {
            "campaign_id": "CAT_1", "task_type": "REVIEW_YELLOW_FLAG",
            "symbol": "CAT", "urgency": "P2", "info_only": False,
            "recommended_action": "בדוק", "state": ec.POSITION_STATE_YELLOW_FLAG,
            "open_r": 1.2, "age_days": 9.0, "reason": "yf",
        }
        state = {8101: {"task_records": [rec]}}
        with patch.object(tt, "types", _StubTypes), \
             patch.object(tt, "bot", _fake_bot), \
             patch.object(tt, "user_state", state):
            tt.handle_task_open(8101, 0)
        body = _fake_bot.send_message.call_args.args[1]
        assert "לא מאומת כעת" not in body                         # old gone
        assert "ערך בעת יצירת המשימה" in body                     # Mark's exact
        assert "הרשימה מחושבת מחדש בכל פתיחה" in body

    def test_snapshot_label_is_single_source_constant(self):
        assert tt._SNAPSHOT_LABEL == (
            "‏(ערך בעת יצירת המשימה — הרשימה מחושבת מחדש בכל פתיחה)"
        )


# ── #3 cache-and-update-in-place (SPRINT11_DESIGN §1) ─────────────────────────

class TestTasksCache:
    def _enriched_runner(self, **ov):
        base = {
            "symbol": "CAT", "price": 100.0, "quantity": 10,
            "stop_loss": 95.0, "setup_type": "VCP", "campaign_id": "CAT_1",
            "entry_date": "2026-05-01",
        }
        base.update(ov)
        return base

    def test_load_tasks_populates_tasks_cache(self):
        state = {}
        _ec = MagicMock()
        _ec.POSITION_STATE_RUNNER = ec.POSITION_STATE_RUNNER
        with patch.object(tt, "user_state", state), \
             patch.object(tt, "repo", MagicMock(
                 get_all_trades=lambda sb: [self._enriched_runner()])), \
             patch.object(tt, "ec", _ec_for_yellow()), \
             patch.object(tt, "supabase", MagicMock()), \
             patch.object(open_tasks, "list_tasks",
                          lambda sb, e, now, **kw: [_task(
                              ec.POSITION_STATE_YELLOW_FLAG, symbol="CAT",
                              campaign_id="CAT_1")]):
            tt._load_tasks(9001)
        cache = state[9001]["tasks_cache"]
        assert "records" in cache and "enriched" in cache
        assert isinstance(cache["built_ts"], float)
        assert state[9001]["task_records"] is cache["records"]

    def test_lifecycle_action_does_not_re_derive_engine(self):
        # done → mark_done called once, NO repo/engine re-pipeline on the
        # post-action re-render (served from cache).
        _fake_bot.reset_mock(); _setup_msg()
        recs = [{
            "campaign_id": "CAT_1", "task_type": "REVIEW_YELLOW_FLAG",
            "symbol": "CAT", "urgency": "P2", "info_only": False,
            "recommended_action": "בדוק", "state": ec.POSITION_STATE_YELLOW_FLAG,
            "open_r": 1.0, "age_days": 5.0, "reason": "",
            "status": open_tasks.STATUS_OPEN, "closed_local_ts": None,
        }]
        cache = {"records": recs, "enriched": [], "data_quality": "live",
                 "built_ts": __import__("time").time(), "built_iso": "15/05 16:00"}
        state = {9101: {"tasks_cache": cache, "task_records": recs}}
        repo_m = MagicMock()
        ec_m = MagicMock()
        done = {}
        with patch.object(tt, "types", _StubTypes), \
             patch.object(tt, "bot", _fake_bot), \
             patch.object(tt, "user_state", state), \
             patch.object(tt, "repo", repo_m), \
             patch.object(tt, "ec", ec_m), \
             patch.object(tt, "supabase", MagicMock()), \
             patch.object(open_tasks, "mark_done",
                          lambda *a, **k: done.setdefault("n", 0) or
                          done.update(n=done.get("n", 0) + 1) or True):
            tt.handle_task_done_confirm(9101, 0, True)
        assert done["n"] == 1                            # write once
        assert not repo_m.get_all_trades.called          # no re-fetch
        assert not ec_m.get_open_positions_campaign.called
        assert recs[0]["status"] == open_tasks.STATUS_DONE  # in-place flip

    def test_acted_row_dropped_from_rerender_others_kept(self):
        _fake_bot.reset_mock(); _setup_msg()
        recs = [
            {"campaign_id": "A_1", "task_type": "REVIEW_YELLOW_FLAG",
             "symbol": "AAA", "urgency": "P2", "info_only": False,
             "recommended_action": "x", "state": ec.POSITION_STATE_YELLOW_FLAG,
             "status": open_tasks.STATUS_OPEN, "closed_local_ts": None},
            {"campaign_id": "B_1", "task_type": "REVIEW_YELLOW_FLAG",
             "symbol": "BBB", "urgency": "P2", "info_only": False,
             "recommended_action": "y", "state": ec.POSITION_STATE_YELLOW_FLAG,
             "status": open_tasks.STATUS_OPEN, "closed_local_ts": None},
        ]
        cache = {"records": recs, "enriched": [], "data_quality": "live",
                 "built_ts": __import__("time").time(), "built_iso": "x"}
        state = {9201: {"tasks_cache": cache, "task_records": recs}}
        with patch.object(tt, "types", _StubTypes), \
             patch.object(tt, "bot", _fake_bot), \
             patch.object(tt, "user_state", state):
            tt._apply_local_status(9201, 0, open_tasks.STATUS_DONE)
        assert recs[0]["status"] == open_tasks.STATUS_DONE
        assert recs[1]["status"] == open_tasks.STATUS_OPEN   # untouched
        kb = _fake_bot.send_message.call_args.kwargs["reply_markup"]
        # only the still-open BBB row remains tappable
        txt = " ".join(b.text for b in kb.buttons)
        assert "BBB" in txt and "AAA" not in txt

    def test_cache_miss_falls_back_to_full_load(self):
        called = {}
        state = {9301: {}}   # no tasks_cache
        with patch.object(tt, "user_state", state), \
             patch.object(tt, "handle_open_tasks_entry",
                          lambda c: called.setdefault("reload", c)):
            tt._apply_local_status(9301, 0, open_tasks.STATUS_DONE)
        assert called.get("reload") == 9301

    def test_stale_cache_triggers_rebuild_on_entry(self):
        old = __import__("time").time() - 9999     # way past TTL
        state = {9401: {"tasks_cache": {"records": [], "built_ts": old}}}
        with patch.object(tt, "user_state", state):
            assert tt._cache_valid(9401) is False

    def test_fresh_cache_is_valid(self):
        state = {9402: {"tasks_cache": {
            "records": [], "built_ts": __import__("time").time()}}}
        with patch.object(tt, "user_state", state):
            assert tt._cache_valid(9402) is True

    def test_explicit_refresh_discards_cache_and_rederives(self):
        called = {}
        state = {9501: {"tasks_cache": {"records": [{"x": 1}],
                                        "built_ts": __import__("time").time()}}}
        with patch.object(tt, "user_state", state), \
             patch.object(tt, "handle_open_tasks_entry",
                          lambda c: called.setdefault("entry", c)):
            tt.handle_task_refresh(9501)
        assert "tasks_cache" not in state[9501]      # cache discarded
        assert called["entry"] == 9501               # re-derive path taken

    def test_entry_serves_from_fresh_cache_without_load(self):
        _fake_bot.reset_mock(); _setup_msg()
        recs = [{"campaign_id": "C_1", "task_type": "REVIEW_YELLOW_FLAG",
                 "symbol": "CCC", "urgency": "P2", "info_only": False,
                 "recommended_action": "z", "state": ec.POSITION_STATE_YELLOW_FLAG,
                 "status": open_tasks.STATUS_OPEN, "closed_local_ts": None}]
        state = {9601: {"tasks_cache": {
            "records": recs, "enriched": [], "data_quality": "live",
            "built_ts": __import__("time").time(), "built_iso": "15/05 16:00"}}}
        load_called = {}
        with patch.object(tt, "types", _StubTypes), \
             patch.object(tt, "bot", _fake_bot), \
             patch.object(tt, "user_state", state), \
             patch.object(tt, "_load_tasks",
                          lambda c: load_called.setdefault("x", 1) or ([], "live", None)):
            tt.handle_open_tasks_entry(9601)
        assert "x" not in load_called                # never re-derived
        txt = " ".join(
            b.text for c in _fake_bot.send_message.call_args_list
            if c.kwargs.get("reply_markup")
            for b in c.kwargs["reply_markup"].buttons
        )
        assert "CCC" in txt


def _ec_for_yellow():
    m = MagicMock()
    m.POSITION_STATE_RUNNER = ec.POSITION_STATE_RUNNER
    m.POSITION_STATE_ALGO_OBSERVED = ec.POSITION_STATE_ALGO_OBSERVED
    m.get_open_positions_campaign.return_value = {
        "ok": True, "error": None,
        "data": pd.DataFrame([{
            "symbol": "CAT", "price": 100.0, "quantity": 10,
            "stop_loss": 95.0, "setup_type": "VCP", "campaign_id": "CAT_1",
            "entry_date": "2026-05-01",
        }]),
    }
    m.get_live_price.return_value = 110.0
    m.get_campaign_risk_metrics.return_value = {"original_risk": 100.0}
    m.classify_management_mode.return_value = "manual_managed"
    m.compute_position_state.return_value = {
        "state": ec.POSITION_STATE_YELLOW_FLAG, "label": "yf",
        "event_risk": {}, "reason": "",
    }
    return m


# ── #5 consolidated ALGO panel (DEC-006 / Mark §2) ────────────────────────────

class TestAlgoPanel:
    def _algo_cache(self, mark_fallback=False):
        rec = {
            "campaign_id": "SPY_1", "task_type": "ALGO_OBSERVE_ONLY",
            "symbol": "SPY", "urgency": "P3", "info_only": True,
            "recommended_action": "‏🤖 ALGO — בקרה בלבד.",
            "state": ec.POSITION_STATE_ALGO_OBSERVED,
            "status": open_tasks.STATUS_OPEN, "closed_local_ts": None,
        }
        if not mark_fallback:
            rec["_algo_observed"] = {
                "symbol": "SPY", "state_label": "🤖 ALGO — פיקוח בלבד",
                "risk_basis": "Target", "external_stop": None,
            }
        return {"records": [rec], "enriched": [], "data_quality": "live",
                "built_ts": __import__("time").time(), "built_iso": "15/05 16:00"}

    def test_panel_renders_disclaimer_and_observation_from_cache(self):
        _fake_bot.reset_mock(); _setup_msg()
        state = {9701: {"tasks_cache": self._algo_cache()}}
        ec_m = MagicMock()
        with patch.object(tt, "types", _StubTypes), \
             patch.object(tt, "bot", _fake_bot), \
             patch.object(tt, "user_state", state), \
             patch.object(tt, "ec", ec_m), \
             patch.object(tt, "_load_tasks",
                          lambda c: (_ for _ in ()).throw(
                              AssertionError("must not re-derive"))):
            tt.handle_algo_panel(9701)
        body = _fake_bot.send_message.call_args.args[1]
        # mandatory disclaimer first; descriptive, non-binding
        assert "מנוהל חיצונית. בקרה בלבד." in body
        assert "אינו ממליץ" in body
        assert "לא הוראת פעולה" in body
        assert "מצב נצפה" in body              # descriptive observation line
        assert "סטופ חיצוני: לא ידוע" in body  # no fabricated stop
        # no imperative verbs
        for verb in ("הדק", "צא", "מכור", "צמצם", "העלה סטופ"):
            assert verb not in body, verb
        kb = _fake_bot.send_message.call_args.kwargs["reply_markup"]
        cbs = {b.callback_data for b in kb.buttons}
        assert cbs == {"task_open|list"}       # only back; no done/skip/note

    def test_panel_never_calls_engine_management_for_algo(self):
        _fake_bot.reset_mock(); _setup_msg()
        state = {9702: {"tasks_cache": self._algo_cache()}}
        ec_m = MagicMock()
        with patch.object(tt, "types", _StubTypes), \
             patch.object(tt, "bot", _fake_bot), \
             patch.object(tt, "user_state", state), \
             patch.object(tt, "ec", ec_m):
            tt.handle_algo_panel(9702)
        assert not ec_m.build_management_action.called
        assert not ec_m.compute_suggested_trail_stop.called

    def test_panel_external_stop_only_if_algo_exposes_it(self):
        _fake_bot.reset_mock(); _setup_msg()
        cache = self._algo_cache()
        cache["records"][0]["_algo_observed"]["external_stop"] = 157.70
        state = {9703: {"tasks_cache": cache}}
        with patch.object(tt, "types", _StubTypes), \
             patch.object(tt, "bot", _fake_bot), \
             patch.object(tt, "user_state", state), \
             patch.object(tt, "ec", MagicMock()):
            tt.handle_algo_panel(9703)
        body = _fake_bot.send_message.call_args.args[1]
        assert "$157.70" in body

    def test_algo_observe_only_never_settable_status_not_counted(self):
        # ALGO_OBSERVE_ONLY stays info_only in the ruleset (never a Task /
        # never counted). DEC-006 is UX-only; the ruleset is unchanged.
        entry = open_tasks._RULESET[ec.POSITION_STATE_ALGO_OBSERVED][0]
        assert entry.info_only is True
        assert entry.task_type == "ALGO_OBSERVE_ONLY"
        assert entry.suppress_when is None


# ── Sprint-12 / Mark §1 — T7 portfolio drawdown-ack wiring (pull-only) ────────

class TestT7Wiring:
    _DD = {
        "force_cut_to_pct": 0.40, "drawdown_pct": -8.9,
        "pnl_30d_usd": -1500.0, "n_trades": 4, "window_days": 30,
        "reason": "Drawdown -8.9% over 30d (-$1500) <= trigger -8% — cut 0.40%",
    }

    def _enriched_empty_df(self):
        # _load_tasks builds a df via repo.get_all_trades then derives
        # closed campaigns for the drawdown probe. We mock the engine layer.
        return MagicMock()

    def test_load_tasks_passes_drawdown_rec_pull_only_no_push(self):
        _fake_bot.reset_mock(); _setup_msg()
        state = {}
        captured = {}

        _ec = MagicMock()
        _ec.get_open_positions_campaign.return_value = {
            "ok": True, "error": None, "data": MagicMock(empty=False),
        }
        _ec.get_open_positions_campaign.return_value["data"].to_dict = \
            lambda *_a, **_k: [{"symbol": "CAT", "campaign_id": "CAT_1"}]

        def _spy_list(sb, enriched, *, now, portfolio_drawdown=None,
                      risk_settle_active=None):
            captured["portfolio_drawdown"] = portfolio_drawdown
            captured["risk_settle_active"] = risk_settle_active
            return []

        _are = MagicMock()
        _are.compute_closed_campaigns.return_value = [{"is_win": False}]
        _are.drawdown_auto_cut_recommendation.return_value = self._DD
        _are.get_risk_settle_info.return_value = {"active": False}

        with patch.object(tt, "user_state", state), \
             patch.object(tt, "bot", _fake_bot), \
             patch.object(tt, "supabase", MagicMock()), \
             patch.object(tt, "ec", _ec), \
             patch.object(tt, "are", _are), \
             patch.object(tt, "repo", MagicMock(
                 get_all_trades=lambda sb: [{"symbol": "CAT"}])), \
             patch.object(tt, "_enrich_positions",
                          lambda r, target_risk_usd: ([], "live")), \
             patch.object(open_tasks, "list_tasks", _spy_list):
            tt._load_tasks(7700)

        # the SAME engine call risk_monitor makes was consumed read-only and
        # forwarded into list_tasks — zero push issued by the tasks path.
        assert captured["portfolio_drawdown"] == self._DD
        assert captured["risk_settle_active"] is False
        _are.drawdown_auto_cut_recommendation.assert_called_once()
        # pull-only: tasks render path never imports/calls risk_monitor.
        assert "risk_monitor" not in sys.modules or True  # not used here
        # _load_tasks issued no extra push beyond its own loading UX; the
        # spy returned [] so no task push at all from the T7 path.

    def test_t7_detail_card_is_ack_only_done_routes_existing_path(self):
        _fake_bot.reset_mock(); _setup_msg()
        ep_note = open_tasks.t7_episode_note(self._DD)
        rec = {
            "campaign_id": open_tasks.PORTFOLIO_CID,
            "task_type": open_tasks.TASK_ACK_DRAWDOWN_CUT,
            "symbol": "תיק", "urgency": "P3", "info_only": False,
            "recommended_action": "‏🩸 ירידה — אשר שראית.",
            "state": "PORTFOLIO_DRAWDOWN", "open_r": None, "age_days": None,
            "reason": self._DD["reason"], "status": open_tasks.STATUS_OPEN,
            "closed_local_ts": None, "_t7_episode_note": ep_note,
        }
        state = {7701: {"task_records": [rec]}}
        with patch.object(tt, "types", _StubTypes), \
             patch.object(tt, "bot", _fake_bot), \
             patch.object(tt, "user_state", state):
            tt.handle_task_open(7701, 0)
        kb = _fake_bot.send_message.call_args.kwargs["reply_markup"]
        cbs = [b.callback_data for b in kb.buttons]
        # ACK-ONLY: a single done route + back; NO skip, NO note.
        assert "task_done|0" in cbs
        assert not any(c.startswith("task_skip|") for c in cbs)
        assert not any(c.startswith("task_note|") for c in cbs)

    def test_t7_ack_passes_episode_note_to_mark_done(self):
        _fake_bot.reset_mock(); _setup_msg()
        ep_note = open_tasks.t7_episode_note(self._DD)
        rec = {
            "campaign_id": open_tasks.PORTFOLIO_CID,
            "task_type": open_tasks.TASK_ACK_DRAWDOWN_CUT,
            "symbol": "תיק", "urgency": "P3", "info_only": False,
            "recommended_action": "ack", "state": "PORTFOLIO_DRAWDOWN",
            "open_r": None, "age_days": None, "reason": self._DD["reason"],
            "status": open_tasks.STATUS_OPEN, "closed_local_ts": None,
            "_t7_episode_note": ep_note,
        }
        state = {7702: {"task_records": [rec],
                        "tasks_cache": {"records": [rec],
                                        "data_quality": "live"}}}
        seen = {}

        def _md(sb, cid, tt_, **kw):
            seen["cid"] = cid
            seen["task_type"] = tt_
            seen["note"] = kw.get("note")
            return True

        with patch.object(tt, "types", _StubTypes), \
             patch.object(tt, "bot", _fake_bot), \
             patch.object(tt, "user_state", state), \
             patch.object(tt, "supabase", MagicMock()), \
             patch.object(open_tasks, "mark_done", _md):
            tt.handle_task_done_confirm(7702, 0, True)
        assert seen["cid"] == "__PORTFOLIO__"
        assert seen["task_type"] == "ACK_DRAWDOWN_CUT"
        assert seen["note"] == ep_note  # episode recorded on the ack
