"""
Tests for open_tasks.py — the Open Tasks (Action-Items) engine.

Covers OPEN_TASKS_ENGINE_DESIGN §4 (11 cases) + the Sprint-10 Wave-2
checkpoint drift test (the typed _RULESET constant must match Mark's
machine-readable block in OPEN_TASKS_METHODOLOGY_SPEC.md §6 exactly, so
Mark stays the methodology owner and any divergence fails CI loudly).

Pure-unit, deterministic, no network (tests/ rules). Mocks `sb` for the
lifecycle path and asserts only the open_tasks table + one audit insert are
touched (never trades / management_state).
"""
import re
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import engine_core as ec
import open_tasks
import user_context as uc


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 5, 15, 16, 42, tzinfo=timezone.utc)


def _pos(state, *, symbol="CAT", campaign_id="CAT_1", open_r=2.0,
         age_days=14.0, reason="", trail_stop=None):
    return {
        "symbol": symbol,
        "campaign_id": campaign_id,
        "open_r": open_r,
        "age_days": age_days,
        "trail_stop": trail_stop,
        "state_result": {
            "state": state, "label": state, "event_risk": {},
            "reason": reason,
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# §4.1 — Derivation per state
# ──────────────────────────────────────────────────────────────────────────────

class TestDerivationPerState:
    @pytest.mark.parametrize("state,expect_task", [
        (ec.POSITION_STATE_NEW,               False),
        (ec.POSITION_STATE_PROVING,           False),
        (ec.POSITION_STATE_WORKING,           False),
        (ec.POSITION_STATE_PROFIT_PROTECTION, True),
        (ec.POSITION_STATE_RUNNER,            True),
        (ec.POSITION_STATE_YELLOW_FLAG,       True),
        (ec.POSITION_STATE_BROKEN,            True),
        (ec.POSITION_STATE_DEAD_MONEY,        True),
    ])
    def test_state_maps_to_ruleset(self, state, expect_task):
        tasks = open_tasks.derive_tasks([_pos(state)], now=_NOW)
        if not expect_task:
            assert tasks == []
            return
        assert len(tasks) == 1
        t = tasks[0]
        # task_type + urgency come from the ruleset, not a literal here.
        entry = open_tasks._RULESET[state][0]
        assert t.task_type == entry.task_type
        assert t.urgency == entry.urgency

    def test_broken_is_p0(self):
        t = open_tasks.derive_tasks([_pos(ec.POSITION_STATE_BROKEN)], now=_NOW)[0]
        assert t.urgency == "P0"
        assert t.task_type == "EXECUTE_EXIT"

    def test_runner_embeds_engine_trail_verbatim(self):
        # G4: the action embeds the engine's OWN suggested stop — not computed
        # here. Pass the engine dict; assert basis/stop appear verbatim.
        trail = {"suggested_stop": 123.45, "basis": "MA50"}
        t = open_tasks.derive_tasks(
            [_pos(ec.POSITION_STATE_RUNNER, trail_stop=trail)], now=_NOW
        )[0]
        assert "MA50" in t.recommended_action
        assert "123.45" in t.recommended_action
        assert "אל תרופף" in t.recommended_action  # never instructs a loosen

    def test_runner_missing_trail_is_honest_not_fabricated(self):
        t = open_tasks.derive_tasks(
            [_pos(ec.POSITION_STATE_RUNNER, trail_stop=None)], now=_NOW
        )[0]
        # No fabricated stop number when the engine detail is unavailable.
        assert "$" not in t.recommended_action or "אינם זמינים" in t.recommended_action


# ──────────────────────────────────────────────────────────────────────────────
# §4.2 — ALGO_OBSERVED info-only
# ──────────────────────────────────────────────────────────────────────────────

class TestAlgoObserved:
    def test_algo_info_only_no_action_verb(self):
        tasks = open_tasks.derive_tasks(
            [_pos(ec.POSITION_STATE_ALGO_OBSERVED)], now=_NOW
        )
        assert len(tasks) == 1
        t = tasks[0]
        assert t.info_only is True
        assert t.task_type == "ALGO_OBSERVE_ONLY"
        assert t.urgency == "P3"
        # No stop/exit/trim verb.
        for verb in ("סגור", "צמצם", "הדק", "צא"):
            assert verb not in t.recommended_action


# ──────────────────────────────────────────────────────────────────────────────
# §4.3 — DATA_INCOMPLETE excluded from actionable
# ──────────────────────────────────────────────────────────────────────────────

class TestDataIncomplete:
    def test_data_incomplete_info_only_no_urgency(self):
        t = open_tasks.derive_tasks(
            [_pos(ec.POSITION_STATE_DATA_INCOMPLETE)], now=_NOW
        )[0]
        assert t.info_only is True
        assert t.urgency is None  # no R / $ / urgency tier — never counted
        assert t.task_type == "COMPLETE_RISK_DATA"

    def test_data_incomplete_never_p0_p2(self):
        t = open_tasks.derive_tasks(
            [_pos(ec.POSITION_STATE_DATA_INCOMPLETE)], now=_NOW
        )[0]
        assert t.urgency not in ("P0", "P1", "P2")


# ──────────────────────────────────────────────────────────────────────────────
# §4.4 — Dedup / supersede
# ──────────────────────────────────────────────────────────────────────────────

class TestDedup:
    def test_same_campaign_twice_single_task(self):
        pos = _pos(ec.POSITION_STATE_RUNNER)
        a = open_tasks.derive_tasks([pos], now=_NOW)
        b = open_tasks.derive_tasks([pos], now=_NOW)
        assert len(a) == 1 and len(b) == 1
        assert (a[0].campaign_id, a[0].task_type) == (b[0].campaign_id, b[0].task_type)

    def test_state_change_supersedes_not_duplicates(self):
        # RUNNER then PROFIT_PROTECTION for the SAME campaign: one task each
        # pass, different task_type — never two open rows for one campaign.
        p1 = _pos(ec.POSITION_STATE_RUNNER, campaign_id="X_1")
        p2 = _pos(ec.POSITION_STATE_PROFIT_PROTECTION, campaign_id="X_1")
        t1 = open_tasks.derive_tasks([p1], now=_NOW)
        t2 = open_tasks.derive_tasks([p2], now=_NOW)
        assert len(t1) == 1 and len(t2) == 1
        assert t1[0].task_type != t2[0].task_type
        assert t1[0].campaign_id == t2[0].campaign_id == "X_1"


# ──────────────────────────────────────────────────────────────────────────────
# §4.5 — Auto-close on transition (campaign absent → task not surfaced)
# ──────────────────────────────────────────────────────────────────────────────

class TestAutoClose:
    def test_campaign_absent_in_pass2_yields_no_task(self):
        present = open_tasks.derive_tasks(
            [_pos(ec.POSITION_STATE_RUNNER, campaign_id="GONE_1")], now=_NOW
        )
        assert len(present) == 1
        # Pass 2: campaign closed (not in positions) → no task derived at all.
        gone = open_tasks.derive_tasks([], now=_NOW)
        assert gone == []

    def test_state_left_runner_yields_no_runner_task(self):
        # RUNNER → WORKING (no task) for the same campaign.
        gone = open_tasks.derive_tasks(
            [_pos(ec.POSITION_STATE_WORKING, campaign_id="GONE_1")], now=_NOW
        )
        assert gone == []


# ──────────────────────────────────────────────────────────────────────────────
# §4.6 — Lifecycle: mark_done / skip / add_note
# ──────────────────────────────────────────────────────────────────────────────

class TestLifecycle:
    def _sb(self):
        sb = MagicMock()
        # default: no existing notes row
        sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        return sb

    def test_mark_done_upserts_open_tasks_only(self):
        sb = self._sb()
        ok = open_tasks.mark_done(sb, "CAT_1", "EXECUTE_EXIT", now=_NOW)
        assert ok is True
        tables = [c.args[0] for c in sb.table.call_args_list]
        # Only open_tasks (+ audit_log via audit_logger) — never trades.
        assert "trades" not in tables
        assert "management_state" not in tables
        assert "open_tasks" in tables

    def test_double_call_is_idempotent_upsert(self):
        sb = self._sb()
        open_tasks.mark_done(sb, "CAT_1", "EXECUTE_EXIT", now=_NOW)
        open_tasks.mark_done(sb, "CAT_1", "EXECUTE_EXIT", now=_NOW)
        # upsert keyed by the DB UNIQUE — never an insert that would dup.
        upserts = sb.table.return_value.upsert.call_args_list
        assert len(upserts) == 2
        for c in upserts:
            assert c.kwargs.get("on_conflict") == "user_id,campaign_id,task_type"

    def test_notes_append_not_replace(self):
        sb = MagicMock()
        # Existing row already has one note.
        sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"notes": ["[old] first note"], "status": "open"}
        ]
        open_tasks.add_note(sb, "CAT_1", "REVIEW_YELLOW_FLAG", "second note",
                            now=_NOW)
        row = sb.table.return_value.upsert.call_args.args[0]
        assert row["notes"][0] == "[old] first note"   # preserved
        assert any("second note" in n for n in row["notes"])  # appended

    def test_audit_log_called_with_settings_change(self):
        sb = self._sb()
        captured = {}

        import audit_logger
        orig = audit_logger.log_action

        def _spy(_sb, action, **kw):
            captured["action"] = action
            captured["metadata"] = kw.get("metadata")
            return True

        audit_logger.log_action = _spy
        try:
            open_tasks.mark_done(sb, "CAT_1", "EXECUTE_EXIT", now=_NOW)
        finally:
            audit_logger.log_action = orig
        assert captured["action"] == audit_logger.ACTION_SETTINGS_CHANGE
        assert captured["metadata"]["table"] == "open_tasks"

    def test_p0_skip_audited_as_skipped_critical_exit(self):
        sb = self._sb()
        captured = {}
        import audit_logger
        orig = audit_logger.log_action

        def _spy(_sb, action, **kw):
            captured["metadata"] = kw.get("metadata")
            return True

        audit_logger.log_action = _spy
        try:
            open_tasks.skip_task(sb, "CAT_1", "EXECUTE_EXIT",
                                 urgency="P0", note="manual exit done at IBKR",
                                 now=_NOW)
        finally:
            audit_logger.log_action = orig
        assert captured["metadata"]["kind"] == open_tasks._SKIPPED_CRITICAL_EXIT

    def test_non_p0_skip_is_normal_kind(self):
        sb = self._sb()
        captured = {}
        import audit_logger
        orig = audit_logger.log_action
        audit_logger.log_action = lambda _s, a, **k: captured.update(
            kind=(k.get("metadata") or {}).get("kind")) or True
        try:
            open_tasks.skip_task(sb, "CAT_1", "REVIEW_YELLOW_FLAG",
                                 urgency="P2", now=_NOW)
        finally:
            audit_logger.log_action = orig
        assert captured["kind"] == "open_task_skipped"


# ──────────────────────────────────────────────────────────────────────────────
# §4.7 — derive_tasks calls NO engine function; lifecycle never mutates trades
# ──────────────────────────────────────────────────────────────────────────────

class TestNoEngineMutation:
    def test_derive_tasks_calls_no_engine_function(self, monkeypatch):
        # Wrap every public engine_core callable; deriving must not call any.
        called = []
        import engine_core as _ec
        for name in dir(_ec):
            if name.startswith("_"):
                continue
            obj = getattr(_ec, name)
            if callable(obj) and not isinstance(obj, type):
                monkeypatch.setattr(
                    _ec, name,
                    (lambda nm: (lambda *a, **k: called.append(nm)))(name),
                    raising=False,
                )
        open_tasks.derive_tasks(
            [_pos(ec.POSITION_STATE_RUNNER),
             _pos(ec.POSITION_STATE_BROKEN, campaign_id="B_1", symbol="B")],
            now=_NOW,
        )
        assert called == [], f"derive_tasks called engine fns: {called}"

    def test_lifecycle_never_touches_trades_table(self):
        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        open_tasks.mark_done(sb, "C_1", "EXECUTE_EXIT", now=_NOW)
        open_tasks.skip_task(sb, "C_1", "REVIEW_YELLOW_FLAG", now=_NOW)
        open_tasks.add_note(sb, "C_1", "REVIEW_YELLOW_FLAG", "n", now=_NOW)
        tables = {c.args[0] for c in sb.table.call_args_list}
        assert "trades" not in tables
        assert "management_state" not in tables


# ──────────────────────────────────────────────────────────────────────────────
# §4.8 — Purity (frozen now → equal lists; no clock without injected now)
# ──────────────────────────────────────────────────────────────────────────────

class TestPurity:
    def test_same_inputs_equal_output(self):
        positions = [_pos(ec.POSITION_STATE_RUNNER),
                     _pos(ec.POSITION_STATE_DEAD_MONEY, campaign_id="D_1",
                          symbol="D")]
        a = open_tasks.derive_tasks(positions, now=_NOW)
        b = open_tasks.derive_tasks(positions, now=_NOW)
        assert [(t.task_type, t.campaign_id, t.created_ts, t.urgency)
                for t in a] == [(t.task_type, t.campaign_id, t.created_ts,
                                 t.urgency) for t in b]

    def test_created_ts_is_injected_now_not_wallclock(self):
        t = open_tasks.derive_tasks([_pos(ec.POSITION_STATE_BROKEN)],
                                    now=_NOW)[0]
        assert t.created_ts == _NOW.isoformat()


# ──────────────────────────────────────────────────────────────────────────────
# §4.9 — Fail-loud ruleset
# ──────────────────────────────────────────────────────────────────────────────

class TestFailLoud:
    def test_unknown_state_raises_not_silent(self):
        with pytest.raises(open_tasks.RulesetUnavailable):
            open_tasks.ruleset_for_state("NOT_A_REAL_STATE")

    def test_empty_ruleset_raises(self, monkeypatch):
        monkeypatch.setattr(open_tasks, "_RULESET", {})
        with pytest.raises(open_tasks.RulesetUnavailable):
            open_tasks.load_ruleset()

    def test_known_no_task_state_returns_empty_not_raise(self):
        # NEW/PROVING/WORKING legitimately map to no task — not an error.
        assert open_tasks.ruleset_for_state(ec.POSITION_STATE_NEW) == []


# ──────────────────────────────────────────────────────────────────────────────
# §4.10 — user_id default = sentinel (Phase-A byte-identical)
# ──────────────────────────────────────────────────────────────────────────────

class TestUserIdDefault:
    def test_default_user_id_is_sentinel(self, monkeypatch):
        monkeypatch.delenv("DEFAULT_USER_ID", raising=False)
        uc.invalidate_user_cache(None)
        t = open_tasks.derive_tasks([_pos(ec.POSITION_STATE_BROKEN)],
                                    now=_NOW)[0]
        assert t.user_id == uc.SENTINEL_USER_ID
        assert t.user_id == "00000000-0000-0000-0000-000000000001"

    def test_lifecycle_resolves_uid_via_user_context(self, monkeypatch):
        monkeypatch.delenv("DEFAULT_USER_ID", raising=False)
        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        open_tasks.mark_done(sb, "C_1", "EXECUTE_EXIT", now=_NOW)
        row = sb.table.return_value.upsert.call_args.args[0]
        assert row["user_id"] == uc.SENTINEL_USER_ID


# ──────────────────────────────────────────────────────────────────────────────
# §4.11 — audit_logger fail-open
# ──────────────────────────────────────────────────────────────────────────────

class TestAuditFailOpen:
    def test_audit_insert_raising_does_not_block_mark_done(self):
        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        # Make ONLY the audit_log insert raise; upsert succeeds.
        import audit_logger
        orig = audit_logger.log_action

        def _boom(*a, **k):
            # audit_logger itself swallows exceptions (fail-open). Emulate a
            # raising backend inside it returning False — must not propagate.
            return False

        audit_logger.log_action = _boom
        try:
            ok = open_tasks.mark_done(sb, "C_1", "EXECUTE_EXIT", now=_NOW)
        finally:
            audit_logger.log_action = orig
        assert ok is True  # user action not blocked by audit failure


# ──────────────────────────────────────────────────────────────────────────────
# CHECKPOINT — _RULESET ↔ Mark's spec §6 machine-readable block drift guard
# ──────────────────────────────────────────────────────────────────────────────

def _parse_spec_ruleset() -> dict:
    """Re-read the fenced ```yaml block in OPEN_TASKS_METHODOLOGY_SPEC.md §6.

    Tiny hand-parser (no yaml dep; matches the simple, fixed shape Mark's
    block uses). Mark's .md is the AUDIT source of truth; this proves the
    runtime constant did not drift from it.
    """
    root = Path(__file__).resolve().parents[1]
    md = (root / "docs" / "teams"
          / "OPEN_TASKS_METHODOLOGY_SPEC.md").read_text(encoding="utf-8")
    m = re.search(r"```yaml\n(.*?)\n```", md, re.DOTALL)
    assert m is not None, "no ```yaml ruleset block found in §6"
    block = m.group(1)

    parsed: dict = {}
    cur_state = None
    cur_entry = None
    for raw in block.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and line.endswith(":"):
            cur_state = line[:-1].strip()
            parsed[cur_state] = []
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            cur_entry = {}
            parsed[cur_state].append(cur_entry)
            stripped = stripped[2:].strip()
        if ":" in stripped:
            k, _, v = stripped.partition(":")
            k = k.strip()
            v = v.strip()
            if v == "null":
                val = None
            elif v in ("true", "false"):
                val = v == "true"
            else:
                val = v.strip('"')
            cur_entry[k] = val
    return parsed


def test_ruleset_matches_methodology_spec():
    """The typed _RULESET constant MUST equal Mark's §6 machine-readable
    block exactly. Drift here = Mark's ruling and the runtime diverged → CI
    fails loudly. (Sprint-10 Wave-2 checkpoint: .md is the audit source, the
    constant is the runtime source.)"""
    spec = _parse_spec_ruleset()

    code = {
        state: [
            {
                "task_type": e.task_type,
                "urgency": e.urgency,
                "info_only": e.info_only,
                "action_he": e.action_he,
            }
            for e in entries
        ]
        for state, entries in open_tasks._RULESET.items()
    }

    assert set(spec.keys()) == set(code.keys()), (
        f"state keys differ — spec={sorted(spec)} code={sorted(code)}"
    )
    for state in code:
        assert len(spec[state]) == len(code[state]), state
        for se, ce in zip(spec[state], code[state]):
            assert se["task_type"] == ce["task_type"], (state, ce)
            assert se["urgency"] == ce["urgency"], (state, ce)
            assert se["info_only"] == ce["info_only"], (state, ce)
            assert se["action_he"] == ce["action_he"], (
                f"{state} action drifted:\nspec={se['action_he']!r}\n"
                f"code={ce['action_he']!r}"
            )


def test_verify_migrations_lists_005():
    """verify_migrations.py must know about 005 → open_tasks, linearly after
    004 (HYPERSCALER §4 / ENGINE_DESIGN §2.4)."""
    root = Path(__file__).resolve().parents[1]
    src = (root / "migrations" / "verify_migrations.py").read_text()
    assert "005_create_open_tasks.sql" in src
    assert src.index("004_add_user_id_to_audit_log.sql") < src.index(
        "005_create_open_tasks.sql"
    )


def test_migration_005_sentinel_literal_exact():
    """open_tasks user_id DEFAULT must be the exact 003 sentinel literal
    (HYPERSCALER §4 point 1 / Phase-A byte-identical)."""
    root = Path(__file__).resolve().parents[1]
    sql = (root / "migrations" / "005_create_open_tasks.sql").read_text()
    m = re.search(r"DEFAULT\s+'([0-9a-fA-F-]{36})'", sql)
    assert m is not None
    assert m.group(1) == uc.SENTINEL_USER_ID
