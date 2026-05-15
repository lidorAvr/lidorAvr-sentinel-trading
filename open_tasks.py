"""
open_tasks.py — the Open Tasks (Action-Items) engine.

Leaf module (same tier as ``telegram_formatters.py`` / ``audit_logger.py`` /
``user_context.py``). It turns the engine's existing authoritative position
state (``engine_core.compute_position_state()``, 10 states) into a list of
concrete, dedup'd, prioritized action items ("Open Tasks") with a
done/skip/note lifecycle.

What this module is NOT
-----------------------
It does **zero** new R / NAV / exposure / campaign math. ``derive_tasks`` is a
pure, referentially-transparent projection: the *caller* runs
``compute_position_state()`` and passes the result in (the same
"callers compute data and pass it in" contract ``telegram_formatters`` uses),
so this module physically cannot re-derive a trading number. Every
trigger→task→urgency→Hebrew-action mapping is read from ``_RULESET`` — a typed
constant transcribed verbatim from Mark's
``docs/teams/OPEN_TASKS_METHODOLOGY_SPEC.md`` §6 machine-readable block (one
``# spec:`` comment per entry; a CI drift test keeps the two in lockstep so
Mark stays the methodology owner).

Persistence model (OPEN_TASKS_ENGINE_DESIGN §2.1): the engine is the single
source of truth. Whether a task is *open* is **re-derived every render** and
never stored. Supabase stores **only lifecycle deltas** (done / skipped / user
notes) keyed by ``(user_id, campaign_id, task_type)`` in the ``open_tasks``
table — never ``trades`` / ``management_state`` / ``risk_monitor_state.json``.

Import discipline (leaf): MAY import ``engine_core`` (constants only),
``user_context``, stdlib. MUST NOT import ``telegram_*`` / ``bot_core`` /
``risk_monitor`` / ``dashboard``. ``sb`` (Supabase) and the audit logger are
dependency-injected, never module-level.

Red lines respected: read-only over engine math (G1); ALGO → info-only never
an action (G2); DATA_INCOMPLETE → no numeric task, never counted (G3); no task
ever instructs a stop loosen (G4 — RUNNER action embeds the engine's own
``compute_suggested_trail_stop`` text verbatim, never a computed stop); no new
push path / no double-notify (G5 — pull-only); SELECT-only derivation, writes
isolated to ``open_tasks`` (G6); P0–P3 reuse the existing ``ALERT_PRIORITY``
tiers (G7); P0 BROKEN exits never silently auto-close or silently skip
(G8 — audited ``skipped_critical_exit``); admin-only entry stays in the
Telegram layer (G9).
"""
from __future__ import annotations

import copy
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import engine_core as ec
import user_context

import audit_logger

_TASKS_TABLE = "open_tasks"

# Status vocabulary (the only values written to open_tasks.status).
STATUS_OPEN = "open"
STATUS_DONE = "done"
STATUS_SKIPPED = "skipped"

# Audited critical-exit skip event kind (metadata.kind on the audit_log row).
# A P0 BROKEN exit "skip" is NEVER a silent drop — spec §3 / G8.
_SKIPPED_CRITICAL_EXIT = "skipped_critical_exit"


class RulesetUnavailable(RuntimeError):
    """Raised when the ruleset cannot be resolved.

    Fail-loud, never a silent empty list — consistent with
    ``user_context.get_user_constant`` raising ``KeyError`` rather than
    returning ``None``.
    """


# ──────────────────────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TriggerSnapshot:
    """Frozen "why" at derivation time. SNAPSHOT ONLY — copied from the engine
    result, never recomputed, never read back as authoritative R/state."""

    state: str          # engine_core.POSITION_STATE_* at creation
    open_r: Optional[float]   # snapshot ONLY — copied from engine, never recomputed
    age_days: Optional[float]  # snapshot ONLY — copied from engine, never recomputed
    reason: str = ""    # engine_core state_result["reason"] verbatim (T1 vs T2 etc.)


@dataclass
class Task:
    task_type: str            # ruleset key, e.g. "PROTECT_RUNNER_PROFIT"
    campaign_id: str
    symbol: str
    urgency: Optional[str]    # "P0".."P3" from ruleset; None for DATA_INCOMPLETE
    trigger_snapshot: TriggerSnapshot
    recommended_action: str   # Hebrew, rendered from the ruleset template
    status: str               # "open" | "done" | "skipped"
    info_only: bool           # True → never an action; never enters a count
    notes: list = field(default_factory=list)   # timestamped, append-only
    created_ts: str = ""      # ISO8601 UTC
    closed_ts: Optional[str] = None
    user_id: str = ""         # additive; default = user_context sentinel


@dataclass(frozen=True)
class RuleEntry:
    """One trigger→task mapping, transcribed verbatim from Mark's spec §6."""

    task_type: str
    urgency: Optional[str]   # "P0".."P3" or None (DATA_INCOMPLETE: no tier)
    info_only: bool
    action_he: str           # Hebrew template; may contain {basis}/{stop}


# ──────────────────────────────────────────────────────────────────────────────
# _RULESET — typed constant, transcribed VERBATIM from Mark's spec §6.
#
# CHECKPOINT (Sprint-10 Wave-2): the Wave-1 "parse Mark's .md at runtime"
# design was rejected as fragile. This typed constant is the runtime source;
# OPEN_TASKS_METHODOLOGY_SPEC.md §6 is the audit source. The drift test
# tests/test_open_tasks.py::test_ruleset_matches_methodology_spec re-reads
# Mark's fenced block and asserts THIS constant matches it exactly, so Mark
# stays the methodology owner and any divergence fails CI loudly.
#
# States NEW / PROVING / WORKING are intentionally absent → no task
# (spec §1: the table only lists the actionable/observed states T1–T8).
# ──────────────────────────────────────────────────────────────────────────────
_RULESET: dict[str, list[RuleEntry]] = {
    # spec: §1 row T4 (PROFIT_PROTECTION, P2, "‏🛡️ 2R+ — שקול הדקת סטופ להגנת רווח.")
    ec.POSITION_STATE_PROFIT_PROTECTION: [
        RuleEntry(
            task_type="TIGHTEN_STOP_PROFIT",
            urgency="P2",
            info_only=False,
            action_he="‏🛡️ 2R+ — שקול הדקת סטופ להגנת רווח.",
        ),
    ],
    # spec: §1 row T3 (RUNNER, P1, action embeds compute_suggested_trail_stop
    #       output verbatim — {basis}/{stop} — never a self-computed stop; G4)
    ec.POSITION_STATE_RUNNER: [
        RuleEntry(
            task_type="PROTECT_RUNNER_PROFIT",
            urgency="P1",
            info_only=False,
            action_he="‏🏃 Runner — הדק סטופ לפי ההמלצה ({basis}, ${stop}). אל תרופף.",
        ),
    ],
    # spec: §1 row T6 (YELLOW_FLAG, P2, "‏🟡 דגל צהוב — בדוק חריגה, החלט אם להדק/לצאת.")
    ec.POSITION_STATE_YELLOW_FLAG: [
        RuleEntry(
            task_type="REVIEW_YELLOW_FLAG",
            urgency="P2",
            info_only=False,
            action_he="‏🟡 דגל צהוב — בדוק חריגה, החלט אם להדק/לצאת.",
        ),
    ],
    # spec: §1 rows T1+T2 (BROKEN, P0). Engine collapses price-through-stop
    #       and violation>=6 into state=BROKEN; the task + P0 tier are
    #       identical, the engine reason field carries the T1-vs-T2 "why".
    ec.POSITION_STATE_BROKEN: [
        RuleEntry(
            task_type="EXECUTE_EXIT",
            urgency="P0",
            info_only=False,
            action_he=(
                "‏🔴 מחיר חצה את הסטופ / ניקוד חריגות שבור — "
                "*סגור עכשיו*. אין שיקול דעת."
            ),
        ),
    ],
    # spec: §1 row T5 (DEAD_MONEY, P3, "‏⏳ הון מת — החלט: לצמצם / לצאת ולפנות הון.")
    ec.POSITION_STATE_DEAD_MONEY: [
        RuleEntry(
            task_type="TRIM_OR_EXIT_DEAD_MONEY",
            urgency="P3",
            info_only=False,
            action_he="‏⏳ הון מת — החלט: לצמצם / לצאת ולפנות הון.",
        ),
    ],
    # spec: §1 row T8 (ALGO_OBSERVED, P3, info-only — NEVER a stop/exit/trim;
    #       DEC-20260511-001 / AGENTS.md #5/#8 / G2)
    ec.POSITION_STATE_ALGO_OBSERVED: [
        RuleEntry(
            task_type="ALGO_OBSERVE_ONLY",
            urgency="P3",
            info_only=True,
            action_he="‏🤖 ALGO — בקרה בלבד. אין פעולת ניהול מטעם Sentinel.",
        ),
    ],
    # spec: § "DATA_INCOMPLETE produces no numeric task at all" — no R/$/
    #       urgency, never counted (AGENTS.md invariant #8 / G3). urgency=None.
    ec.POSITION_STATE_DATA_INCOMPLETE: [
        RuleEntry(
            task_type="COMPLETE_RISK_DATA",
            urgency=None,
            info_only=True,
            action_he="‏⚠️ נתוני סיכון חסרים — השלם entry/stop כדי שהפוזיציה תיכלל.",
        ),
    ],
}


def load_ruleset() -> dict[str, list[RuleEntry]]:
    """Return the active ruleset.

    Public seam (Phase B can swap the body to a DB/profile-backed source
    without touching ``derive_tasks``). Returns a deep copy so callers cannot
    mutate the module constant.

    Fail-loud: if the constant were ever empty/None this raises
    ``RulesetUnavailable`` rather than silently returning ``[]`` — mirrors
    ``user_context.get_user_constant`` raising on the unknown case.
    """
    if not _RULESET:
        raise RulesetUnavailable(
            "open_tasks._RULESET is empty — refusing to derive zero tasks "
            "silently (fail-loud)."
        )
    return copy.deepcopy(_RULESET)


def ruleset_for_state(state: str, ruleset: Optional[dict] = None) -> list[RuleEntry]:
    """Look up the rule entries for an engine state.

    Fail-loud on an UNKNOWN state (never silent ``None``/``[]``), mirroring
    ``user_context.get_user_constant`` raising ``KeyError``. A *known* state
    that legitimately maps to no task (NEW / PROVING / WORKING) returns ``[]``
    — that is an explicit Mark ruling, not a typo.
    """
    rs = ruleset if ruleset is not None else load_ruleset()
    if state in rs:
        return rs[state]
    # Known engine states that intentionally produce no task.
    if state in (
        ec.POSITION_STATE_NEW,
        ec.POSITION_STATE_PROVING,
        ec.POSITION_STATE_WORKING,
    ):
        return []
    raise RulesetUnavailable(
        f"Unknown engine state {state!r} queried against the Open Tasks "
        f"ruleset (fail-loud — never silently None/empty)."
    )


# ──────────────────────────────────────────────────────────────────────────────
# derive_tasks — PURE projection (no engine call, no I/O, no clock)
# ──────────────────────────────────────────────────────────────────────────────


def _utc_iso(now: datetime) -> str:
    """ISO8601 UTC string from the INJECTED ``now`` (never reads the clock)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).isoformat()


def _render_action(template: str, position: dict) -> str:
    """Render a Hebrew action template.

    For RUNNER the template may embed ``{basis}``/``{stop}`` — these come from
    the caller-supplied ``trail_stop`` dict, which is the engine's OWN
    ``compute_suggested_trail_stop()`` output passed in verbatim. This module
    NEVER computes a stop (G4: a task never instructs a loosen; it only
    describes the engine's already-ratcheted suggestion).
    """
    if "{basis}" not in template and "{stop}" not in template:
        return template
    trail = position.get("trail_stop") or {}
    basis = trail.get("basis")
    stop = trail.get("suggested_stop")
    if basis is None or stop is None:
        # Honest fallback — never fabricate a stop number (CLAUDE.md /
        # AGENTS.md #1 no fallback-as-truth).
        return (
            "‏🏃 Runner — הדק סטופ לפי המלצת המנוע "
            "(פרטי ההמלצה אינם זמינים כעת — בדוק בחדר מצב)."
        )
    return template.format(basis=basis, stop=f"{float(stop):.2f}")


def derive_tasks(
    positions: list,
    *,
    now: datetime,
    ruleset: Optional[dict] = None,
) -> list[Task]:
    """Project open positions → action-item tasks. PURE.

    ``positions``: the list of open-position dicts. Each MUST carry a
    ``state_result`` key (the dict returned by
    ``engine_core.compute_position_state()`` — keys ``state``/``label``/
    ``event_risk``/``reason``). The caller obtains that itself; ``derive_tasks``
    **does not call the engine**, so it cannot accidentally re-derive
    R/NAV/campaign math (G1; OPEN_TASKS_ENGINE_DESIGN §1.4).

    Optional per-position keys (snapshot/why only — never recomputed here):
    ``open_r``, ``age_days``, ``trail_stop`` (the engine's own
    ``compute_suggested_trail_stop()`` dict, for the RUNNER template).

    Referentially transparent: same ``positions`` + same ``now`` + same
    ``ruleset`` → identical list. No I/O, no Supabase, no clock except the
    injected ``now``.
    """
    rs = ruleset if ruleset is not None else load_ruleset()
    created = _utc_iso(now)
    uid = user_context.get_current_user_id()

    tasks: list[Task] = []
    for pos in positions:
        sr = pos.get("state_result")
        if not sr or not isinstance(sr, dict):
            # No engine verdict supplied → cannot project. Skip rather than
            # invent a state (fail-quiet on a missing input is correct here:
            # absence of a verdict ≠ a task; the bot still re-derives next
            # render once the caller supplies state_result).
            continue
        state = sr.get("state")
        if not state:
            continue

        entries = ruleset_for_state(state, rs)
        if not entries:
            continue

        symbol = str(pos.get("symbol", "?"))
        campaign_id = str(pos.get("campaign_id", ""))
        open_r = pos.get("open_r")
        age_days = pos.get("age_days")
        reason = str(sr.get("reason", ""))

        for entry in entries:
            snap = TriggerSnapshot(
                state=state,
                open_r=open_r,
                age_days=age_days,
                reason=reason,
            )
            action = _render_action(entry.action_he, pos)
            tasks.append(
                Task(
                    task_type=entry.task_type,
                    campaign_id=campaign_id,
                    symbol=symbol,
                    urgency=entry.urgency,
                    trigger_snapshot=snap,
                    recommended_action=action,
                    status=STATUS_OPEN,
                    info_only=entry.info_only,
                    notes=[],
                    created_ts=created,
                    closed_ts=None,
                    user_id=uid,
                )
            )
    return tasks


# ──────────────────────────────────────────────────────────────────────────────
# Lifecycle API — the ONLY Supabase-touching surface (DI ``sb`` first arg)
# ──────────────────────────────────────────────────────────────────────────────


def _resolve_uid(user_id: Optional[str]) -> str:
    """Phase-A: never None, never raises (HYPERSCALER §2 — reuse
    get_current_user_id, never hard-code/inline the sentinel)."""
    return user_id or user_context.get_current_user_id()


def _read_lifecycle(sb: Any, user_id: str) -> dict:
    """Read stored done/skip/notes rows for a user. SELECT only.

    Returns ``{(campaign_id, task_type): row}``. Best-effort: on any backend
    error returns ``{}`` (the engine still re-derives the open set; a missing
    overlay just means "show as open" — never fabricate a status).
    """
    if sb is None:
        return {}
    try:
        res = (
            sb.table(_TASKS_TABLE)
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        rows = (res.data if res and getattr(res, "data", None) else []) or []
    except Exception as e:
        print(
            f"[open_tasks] lifecycle read failed: {type(e).__name__}: {e}",
            file=sys.stderr,
            flush=True,
        )
        return {}
    out: dict = {}
    for row in rows:
        key = (str(row.get("campaign_id", "")), str(row.get("task_type", "")))
        out[key] = row
    return out


def list_tasks(
    sb: Any,
    positions: list,
    *,
    now: datetime,
    user_id: Optional[str] = None,
) -> list[Task]:
    """Derive (live) ⟕ lifecycle (stored).

    1. ``derived = derive_tasks(positions, now=now)`` — the live open set.
    2. Left-join stored done/skipped/notes overlays on
       ``(campaign_id, task_type)``: a derived task with a stored
       ``done``/``skipped`` overlay is returned with that status (so the bot
       can grey/hide it) and its stored notes attached.
    3. Auto-close on state transition / supersede is *implicit*: a stored
       overlay whose ``task_type`` the engine no longer emits simply isn't in
       ``derived`` so it is not surfaced — no engine state is mutated, and a
       P0 exit is NEVER laundered away (it only drops off once the campaign
       genuinely closes / the engine stops emitting it; spec §3 / K5 / G8).

    No write here. Pull-only (G5: no new push path).
    """
    uid = _resolve_uid(user_id)
    derived = derive_tasks(positions, now=now)
    overlays = _read_lifecycle(sb, uid)
    for task in derived:
        ov = overlays.get((task.campaign_id, task.task_type))
        if not ov:
            continue
        status = ov.get("status")
        if status in (STATUS_DONE, STATUS_SKIPPED):
            task.status = status
            task.closed_ts = ov.get("closed_ts")
        notes = ov.get("notes")
        if isinstance(notes, list) and notes:
            task.notes = list(notes)
    return derived


def _existing_notes(sb: Any, user_id: str, campaign_id: str, task_type: str) -> list:
    """Current stored notes list for a (user,campaign,task) — for append."""
    if sb is None:
        return []
    try:
        res = (
            sb.table(_TASKS_TABLE)
            .select("notes")
            .eq("user_id", user_id)
            .eq("campaign_id", campaign_id)
            .eq("task_type", task_type)
            .limit(1)
            .execute()
        )
        data = (res.data if res and getattr(res, "data", None) else []) or []
    except Exception:
        return []
    if not data:
        return []
    notes = data[0].get("notes")
    return list(notes) if isinstance(notes, list) else []


def _upsert_lifecycle(
    sb: Any,
    *,
    user_id: str,
    campaign_id: str,
    task_type: str,
    status: str,
    note: Optional[str],
    now: datetime,
    audit_kind: str,
) -> bool:
    """Upsert ONE lifecycle row keyed by (user_id, campaign_id, task_type).

    Notes are APPENDED (never replaced) — same discipline as
    ``supabase_repository.update_management_notes``. Writes ONLY the
    ``open_tasks`` table (never ``trades``/``management_state``). Then a
    fail-open ``audit_logger.log_action(ACTION_SETTINGS_CHANGE)`` row — audit
    failure NEVER blocks the user (audit_logger contract).

    Idempotent: the DB UNIQUE(user_id,campaign_id,task_type) makes a Telegram
    double-tap a no-op upsert, not a duplicate row.
    """
    if sb is None:
        return False
    ts = _utc_iso(now)
    prior_notes = _existing_notes(sb, user_id, campaign_id, task_type)
    new_notes = list(prior_notes)
    if note is not None and str(note).strip():
        new_notes.append(f"[{ts}] {str(note).strip()}")

    row = {
        "user_id": user_id,
        "campaign_id": campaign_id,
        "task_type": task_type,
        "status": status,
        "notes": new_notes,
        "closed_ts": ts if status in (STATUS_DONE, STATUS_SKIPPED) else None,
    }
    try:
        sb.table(_TASKS_TABLE).upsert(
            row, on_conflict="user_id,campaign_id,task_type"
        ).execute()
    except Exception as e:
        print(
            f"[open_tasks] lifecycle upsert failed status={status} "
            f"{campaign_id}/{task_type}: {type(e).__name__}: {e}",
            file=sys.stderr,
            flush=True,
        )
        return False

    # Fail-open audit (never blocks the user; mirrors guard_stop_write).
    audit_logger.log_action(
        sb,
        audit_logger.ACTION_SETTINGS_CHANGE,
        metadata={
            "kind": audit_kind,
            "table": _TASKS_TABLE,
            "user_id": user_id,
            "campaign_id": campaign_id,
            "task_type": task_type,
            "status": status,
            "note_appended": bool(note is not None and str(note).strip()),
        },
    )
    return True


def mark_done(
    sb: Any,
    campaign_id: str,
    task_type: str,
    *,
    user_id: Optional[str] = None,
    note: Optional[str] = None,
    now: Optional[datetime] = None,
) -> bool:
    """Record an explicit user 'done' decision for a task.

    Upsert one row (status=done), append the optional note, write a fail-open
    audit row. Never touches ``trades``/``management_state``.
    """
    uid = _resolve_uid(user_id)
    n = now or datetime.now(timezone.utc)
    return _upsert_lifecycle(
        sb,
        user_id=uid,
        campaign_id=str(campaign_id),
        task_type=str(task_type),
        status=STATUS_DONE,
        note=note,
        now=n,
        audit_kind="open_task_done",
    )


def skip_task(
    sb: Any,
    campaign_id: str,
    task_type: str,
    *,
    user_id: Optional[str] = None,
    note: Optional[str] = None,
    urgency: Optional[str] = None,
    now: Optional[datetime] = None,
) -> bool:
    """Record an explicit user 'skip' decision (a recorded decision, not a
    deletion — spec §3 "Skip semantics").

    A P0 skip (BROKEN exit) is the highest-methodology-risk action: it is
    audited as an explicit ``skipped_critical_exit`` event (G8 / spec §3 —
    never a silent drop). The caller (Telegram layer) is responsible for
    refusing an empty P0 reason BEFORE calling this; this layer enforces the
    audit-kind escalation so even a programmatic P0 skip is never silent.
    """
    uid = _resolve_uid(user_id)
    n = now or datetime.now(timezone.utc)
    audit_kind = (
        _SKIPPED_CRITICAL_EXIT if urgency == "P0" else "open_task_skipped"
    )
    return _upsert_lifecycle(
        sb,
        user_id=uid,
        campaign_id=str(campaign_id),
        task_type=str(task_type),
        status=STATUS_SKIPPED,
        note=note,
        now=n,
        audit_kind=audit_kind,
    )


def add_note(
    sb: Any,
    campaign_id: str,
    task_type: str,
    note: str,
    *,
    user_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> bool:
    """Append a free-text note to a task's lifecycle row WITHOUT changing its
    status (append-only; operational metadata, never trading data — spec §3
    "Notes lifecycle"). A note on an as-yet-untouched task creates the row in
    the open-but-annotated state (``status=open``)."""
    uid = _resolve_uid(user_id)
    n = now or datetime.now(timezone.utc)
    if note is None or not str(note).strip():
        return False
    # Preserve the existing status if a row already exists; otherwise the row
    # is created as STATUS_OPEN with closed_ts NULL (a note never closes).
    existing_status = STATUS_OPEN
    if sb is not None:
        try:
            res = (
                sb.table(_TASKS_TABLE)
                .select("status")
                .eq("user_id", uid)
                .eq("campaign_id", str(campaign_id))
                .eq("task_type", str(task_type))
                .limit(1)
                .execute()
            )
            data = (res.data if res and getattr(res, "data", None) else []) or []
            if data and data[0].get("status"):
                existing_status = data[0]["status"]
        except Exception:
            pass
    return _upsert_lifecycle(
        sb,
        user_id=uid,
        campaign_id=str(campaign_id),
        task_type=str(task_type),
        status=existing_status,
        note=note,
        now=n,
        audit_kind="open_task_note",
    )
