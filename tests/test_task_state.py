"""test_task_state.py — Persistence layer for Task Review acks + snoozes."""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import task_state as ts


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def state_path(tmp_path):
    return str(tmp_path / "task_state.json")


# ════════════════════════════════════════════════════════════════════════════════
# load_state / save_state
# ════════════════════════════════════════════════════════════════════════════════

class TestPersistence:
    def test_load_returns_empty_when_missing(self, state_path):
        state = ts.load_state(state_path)
        assert state == {"snoozed": {}, "last_action": {}}

    def test_save_then_load_roundtrip(self, state_path):
        ts.save_state({"snoozed": {"k|x": 12345}, "last_action": {}}, state_path)
        loaded = ts.load_state(state_path)
        assert loaded["snoozed"]["k|x"] == 12345

    def test_load_returns_empty_on_corrupt_json(self, state_path):
        with open(state_path, "w") as f:
            f.write("{not valid json")
        state = ts.load_state(state_path)
        assert state == {"snoozed": {}, "last_action": {}}

    def test_save_is_atomic_no_tmp_left_behind(self, state_path):
        ts.save_state({"snoozed": {}, "last_action": {}}, state_path)
        assert os.path.exists(state_path)
        assert not os.path.exists(state_path + ".tmp")

    def test_load_fills_missing_keys(self, state_path):
        with open(state_path, "w") as f:
            json.dump({"snoozed": {"k|x": 100}}, f)
        state = ts.load_state(state_path)
        assert "last_action" in state
        assert state["snoozed"]["k|x"] == 100

    def test_load_returns_empty_for_non_dict_root(self, state_path):
        with open(state_path, "w") as f:
            json.dump([1, 2, 3], f)
        state = ts.load_state(state_path)
        assert state == {"snoozed": {}, "last_action": {}}


# ════════════════════════════════════════════════════════════════════════════════
# get_snoozes
# ════════════════════════════════════════════════════════════════════════════════

class TestGetSnoozes:
    def test_returns_only_active_snoozes(self, state_path):
        now = time.time()
        ts.save_state({
            "snoozed": {
                "a|x": now + 100,    # active
                "b|y": now - 100,    # expired
            },
            "last_action": {},
        }, state_path)
        active = ts.get_snoozes(state_path, now_ts=now)
        assert "a|x" in active
        assert "b|y" not in active

    def test_returns_empty_dict_when_state_missing(self, state_path):
        # State file doesn't exist
        assert ts.get_snoozes(state_path) == {}


# ════════════════════════════════════════════════════════════════════════════════
# snooze_task
# ════════════════════════════════════════════════════════════════════════════════

class TestSnoozeTask:
    def test_short_snooze_records_expiry_24h(self, state_path):
        now = 1_000_000.0
        ts.snooze_task("k|x", ts.SNOOZE_SHORT, state_path, now_ts=now)
        state = ts.load_state(state_path)
        assert state["snoozed"]["k|x"] == pytest.approx(now + ts.SNOOZE_SHORT)

    def test_long_snooze_records_expiry_30d(self, state_path):
        now = 1_000_000.0
        ts.dismiss_task("k|x", state_path, now_ts=now)
        state = ts.load_state(state_path)
        assert state["snoozed"]["k|x"] == pytest.approx(now + ts.SNOOZE_LONG)

    def test_records_last_action(self, state_path):
        now = 1_000_000.0
        ts.snooze_task("k|x", ts.SNOOZE_SHORT, state_path, now_ts=now)
        state = ts.load_state(state_path)
        assert state["last_action"]["k|x"]["action"] == "snooze"
        assert state["last_action"]["k|x"]["ts"] == now

    def test_second_snooze_overwrites_first(self, state_path):
        now = 1_000_000.0
        ts.snooze_task("k|x", 100, state_path, now_ts=now)
        ts.snooze_task("k|x", 200, state_path, now_ts=now + 1)
        state = ts.load_state(state_path)
        # Second wins
        assert state["snoozed"]["k|x"] == pytest.approx(now + 1 + 200)


# ════════════════════════════════════════════════════════════════════════════════
# approve_task
# ════════════════════════════════════════════════════════════════════════════════

class TestApproveTask:
    def test_records_before_and_after(self, state_path):
        now = 1_000_000.0
        ts.approve_task("CAT_T1|break_even_2r", before=840.0, after=870.0,
                         path=state_path, now_ts=now)
        state = ts.load_state(state_path)
        rec = state["last_action"]["CAT_T1|break_even_2r"]
        assert rec["action"] == "approve"
        assert rec["before"] == 840.0
        assert rec["after"]  == 870.0
        assert rec["ts"] == now

    def test_short_grace_snooze_after_approve(self, state_path):
        """1h grace prevents the rule from immediately re-firing before
        the Supabase write has propagated."""
        now = 1_000_000.0
        ts.approve_task("CAT_T1|break_even_2r", before=840.0, after=870.0,
                         path=state_path, now_ts=now)
        active = ts.get_snoozes(state_path, now_ts=now + 1)
        assert "CAT_T1|break_even_2r" in active
        # But expires within ~1 hour
        active_after = ts.get_snoozes(state_path, now_ts=now + 7200)
        assert "CAT_T1|break_even_2r" not in active_after

    def test_approve_with_none_values(self, state_path):
        """Exit-type tasks have no before/after stop value."""
        ts.approve_task("CAT_T1|stop_breach", before=None, after=None,
                         path=state_path, now_ts=1_000_000.0)
        state = ts.load_state(state_path)
        rec = state["last_action"]["CAT_T1|stop_breach"]
        assert rec["before"] is None and rec["after"] is None


# ════════════════════════════════════════════════════════════════════════════════
# last_action
# ════════════════════════════════════════════════════════════════════════════════

class TestLastAction:
    def test_returns_none_when_no_history(self, state_path):
        assert ts.last_action("never|seen", state_path) is None

    def test_returns_recorded_action(self, state_path):
        ts.dismiss_task("k|x", state_path, now_ts=1_000_000.0)
        rec = ts.last_action("k|x", state_path)
        assert rec is not None
        assert rec["action"] == "snooze"


# ════════════════════════════════════════════════════════════════════════════════
# Defensive — never raises
# ════════════════════════════════════════════════════════════════════════════════

class TestDefensive:
    def test_save_to_unwritable_path_returns_false(self):
        ok = ts.save_state({"snoozed": {}, "last_action": {}},
                            "/proc/never/writable")
        assert ok is False

    def test_load_from_unreadable_path_returns_empty(self):
        state = ts.load_state("/this/path/cannot/exist")
        assert state == {"snoozed": {}, "last_action": {}}
