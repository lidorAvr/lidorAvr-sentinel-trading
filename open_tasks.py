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

# ──────────────────────────────────────────────────────────────────────────────
# T7 — portfolio-level drawdown-acknowledgement task (Sprint-12; Mark §1).
#
# STRUCTURAL RED LINE (Mark §1.7 / SPRINT12_DESIGN §1.1): T7 has NO
# engine_core.POSITION_STATE_* state. It MUST NOT be added to ``_RULESET`` nor
# to the §6 ```yaml block nor emitted by ``derive_tasks``'s position loop —
# doing so would add a key to exactly one side of the bidirectional
# ``set(_RULESET)==set(spec §6 yaml)`` drift test and break CI. T7 is a
# SEPARATE, parallel derivation (``derive_portfolio_tasks``) that joins the
# SAME lifecycle table + the SAME list/cache/render. The drift test only
# guards ``_RULESET``; it is untouched by construction.
#
# It is read-only over ``adaptive_risk_engine.drawdown_auto_cut_recommendation``
# (the SAME engine call risk_monitor already consumes — zero new R/NAV/PnL
# math; constants live in adaptive_risk_engine, never copied here). PULL-ONLY:
# T7 emits ZERO Telegram push (the push channel is risk_monitor.py:938-997
# exclusively — Mark §1.5 HARD rule). Firewalled from every stat: the
# ``__PORTFOLIO__`` campaign_id is never a real campaign, never enters
# compute_position_state / WR / Expectancy / PF / total_r (Mark §1.6).
# ──────────────────────────────────────────────────────────────────────────────

# Reserved synthetic campaign_id (Mark §1.6). NOT a real {SYMBOL}_{tradeID}
# (DEC-20260512-004 format) so it can never collide with a campaign and any
# stat aggregator that filters this value out stays correct.
PORTFOLIO_CID = "__PORTFOLIO__"

# Mark §1.6/§1.7 — the verbatim task_type for the ack lifecycle row.
TASK_ACK_DRAWDOWN_CUT = "ACK_DRAWDOWN_CUT"

# Snapshot label string ONLY (TriggerSnapshot.state) — NEVER an
# engine_core.POSITION_STATE_* and NEVER a _RULESET key. It exists only so the
# "why" block can show a human label; it does not drive any lookup.
_PORTFOLIO_DRAWDOWN_STATE_LABEL = "PORTFOLIO_DRAWDOWN"

# Mark §1.3 — urgency is P3, reusing ALERT_PRIORITY["adaptive_risk"] verbatim
# (risk_monitor.py:77). Held as a literal here (open_tasks is a leaf and must
# NOT import risk_monitor — G5/import discipline); it mirrors that constant and
# invents no new severity scale (Mark §1.3 / spec §4 G7).
_T7_URGENCY = "P3"

# Mark §1.7 spec-bullet: T7 is "info_only:false" ack-task. It is NOT
# info-only. It is nonetheless firewalled from every stat by being a
# __PORTFOLIO__-keyed task that never reaches compute_position_state / any
# campaign stat (Mark §1.6); info_only is NOT T7's firewall mechanism.
_T7_INFO_ONLY = False

# Mark §1.6 ⟨MARK: T7 audit kind⟩ — surface-able kind so the ack shows in the
# user's "🧾 הפעולות שלי" review (DEC-008 SURFACE list: task lifecycle done).
# mark_done() already writes audit_kind="open_task_done" for the lifecycle row;
# this constant is the metadata.kind used when the task auto-clears as
# condition_cleared (never status=done — Mark §1.4 honesty).
_T7_CONDITION_CLEARED_KIND = "portfolio_drawdown_condition_cleared"

# Mark §1.2 — VERBATIM ack Hebrew (descriptive; zero imperative trading verb;
# states the cut already happened automatically). {drawdown_pct} is the
# engine's own round(drawdown_pct,2); 0.40 is DRAWDOWN_CUT_TO_PCT literal-from-
# constant. Engineering invents none of this wording — copied from Mark §1.2.
_T7_ACTION_HE = (
    "‏🩸 ירידה של {drawdown_pct}% ב-30 יום — הסיכון כבר הורד אוטומטית ל-0.40%.\n"
    "‏זו הודעה לאישור בלבד. אין פעולת מסחר. אשר שראית."
)

# auto-clear reason recorded when the engine call later returns None AND the
# 48h settle elapsed (Mark §1.4 — honest, never as status=done).
T7_REASON_CONDITION_CLEARED = "condition_cleared"


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
    # DEC-20260515-007 / Mark §1.3: declarative suppression key. The string is
    # interpreted by derive_tasks (NOT new math) — RUNNER's
    # "current_stop_meets_suggested_within_trail_ma_buffer" suppresses a
    # redundant no-op tighten when the engine's own suggested stop is already
    # satisfied within the engine's own MA buffer. Default None = no
    # suppression (every non-RUNNER row).
    suppress_when: Optional[str] = None


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
    #       output verbatim — {basis}/{stop} — never a self-computed stop; G4).
    #       suppress_when: Mark §1.3 / DEC-20260515-007 — read-only no-op
    #       suppression vs the engine's own suggested stop (no new math).
    ec.POSITION_STATE_RUNNER: [
        RuleEntry(
            task_type="PROTECT_RUNNER_PROFIT",
            urgency="P1",
            info_only=False,
            action_he="‏🏃 Runner — הדק סטופ לפי ההמלצה ({basis}, ${stop}). אל תרופף.",
            suppress_when="current_stop_meets_suggested_within_trail_ma_buffer",
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


# DEC-20260515-007 / Mark §1 — the ONLY suppression key the ruleset declares.
# Kept as a named constant so derive_tasks dispatches on the spec string, not a
# magic literal scattered in logic.
_SUPPRESS_RUNNER_WITHIN_TRAIL_BUFFER = (
    "current_stop_meets_suggested_within_trail_ma_buffer"
)


def _runner_task_suppressed(position: dict) -> bool:
    """DEC-20260515-007 / Mark §1.2 — read-only no-op RUNNER suppression.

    Returns True only when the campaign's already-stored ``current_stop`` is
    ALREADY at or beyond the engine's OWN ``compute_suggested_trail_stop()``
    suggestion, within the engine's OWN MA buffer. This is a comparison of two
    engine-produced numbers — it computes **no** new R/NAV/exposure/campaign
    math (G1; AGENTS.md #2; CLAUDE.md). ``_TRAIL_MA_BUFFER_PCT`` is read LIVE
    from ``engine_core`` (Mark §1.1 — never hard-copied).

    Tighten-only: suppression triggers only when the stop is already protected;
    it never produces, recommends, or implies a *lower* stop, so it cannot
    conflict with the ratchet-up rule (Mark §1.2).

    Honest on absent/invalid engine output: ``suggested_stop is None`` /
    ``basis == "none"`` / ``current_stop <= 0`` → NOT suppressed (the task IS
    emitted — never suppress on missing engine output; AGENTS.md #1).
    """
    trail = position.get("trail_stop") or {}
    S = trail.get("suggested_stop")
    B = trail.get("basis")
    if S is None or B == "none":
        return False
    C = position.get("current_stop")
    try:
        S = float(S)
        if C is None:
            return False
        C = float(C)
    except (TypeError, ValueError):
        return False
    if C <= 0 or S <= 0:
        return False
    # ε = _TRAIL_MA_BUFFER_PCT × suggested_stop, the constant read LIVE from
    # engine_core (Mark §1.1 ruling — anchored, never invented/hard-copied).
    epsilon = ec._TRAIL_MA_BUFFER_PCT * S
    side = str(position.get("side", "BUY")).upper()
    if side in ("SELL", "SHORT"):
        # Short side is symmetric (Mark §1.2): already-protected = stop at or
        # below suggested + ε.
        return C <= S + epsilon
    # Long (the only side in this Minervini long-momentum data model): already
    # protected = stop at or above suggested − ε.
    return C >= S - epsilon


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
            # DEC-20260515-007 / Mark §1: suppress a redundant no-op RUNNER
            # tighten when the engine's own suggested stop is already met
            # within the engine's own MA buffer. Read-only over the engine
            # output; a *material* tighten (gap > ε) still surfaces. The
            # RUNNER position state itself is unchanged — only this one
            # action-item is withheld (Mark §1.2).
            if (
                entry.suppress_when == _SUPPRESS_RUNNER_WITHIN_TRAIL_BUFFER
                and _runner_task_suppressed(pos)
            ):
                continue
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
# T7 — derive_portfolio_tasks: a SEPARATE pure helper (NOT a _RULESET entry,
# NOT inside derive_tasks's position loop). Drift-test-safe by construction
# (Mark §1.7 / SPRINT12_DESIGN §1.3).
# ──────────────────────────────────────────────────────────────────────────────


def _t7_episode_token(drawdown_rec: Optional[dict]) -> str:
    """The drawdown-episode identity token (Mark §1.4 / SPRINT12_DESIGN
    §1.5(4)).

    Mark §1.7 anchors the episode to the engine's OWN window + reason. The
    engine's ``reason`` string embeds the rolling ``DRAWDOWN_WINDOW_DAYS``
    bucket, the observed dd%, the $ PnL and the cut target — it changes iff the
    underlying drawdown FACT changes. So two observations are "the same
    episode" iff their engine ``reason`` strings are equal. This invents no
    equivalence of our own — it reuses the engine's own output verbatim
    (zero new math; AGENTS.md #1/#2).
    """
    if not drawdown_rec or not isinstance(drawdown_rec, dict):
        return ""
    return str(drawdown_rec.get("reason", ""))


def derive_portfolio_tasks(
    *,
    drawdown_rec: Optional[dict],
    now: datetime,
    ruleset: Optional[dict] = None,  # accepted for call-shape parity; unused
) -> list[Task]:
    """Pure. ``drawdown_rec`` is the CALLER-supplied output of
    ``adaptive_risk_engine.drawdown_auto_cut_recommendation`` (or ``None``).

    Returns ``[]`` when ``drawdown_rec`` is ``None`` — absence of a forced cut
    is NOT a task; never fabricate an ack for a cut that did not happen
    (AGENTS.md #1; Mark §1.1). Emits **exactly one** ack Task when present,
    keyed ``(__PORTFOLIO__, ACK_DRAWDOWN_CUT)`` (Mark §1.6).

    Read-only over the engine output: it copies the engine's own
    ``round(drawdown_pct,2)`` into the Hebrew text and the ``reason`` verbatim
    into the snapshot. It computes **zero** new R/NAV/PnL/campaign/drawdown
    math (Mark §1.1; G1). Referentially transparent: same ``drawdown_rec`` +
    same ``now`` → identical list.

    NOT a ``_RULESET`` row, NOT emitted by ``derive_tasks``: the drift test
    (``test_ruleset_matches_methodology_spec``) is untouched by construction
    (Mark §1.7 / SPRINT12_DESIGN §1.3).
    """
    if not drawdown_rec or not isinstance(drawdown_rec, dict):
        return []
    created = _utc_iso(now)
    uid = user_context.get_current_user_id()

    dd_pct = drawdown_rec.get("drawdown_pct")
    # The engine ALREADY rounded this (adaptive_risk_engine.py:252). We display
    # the engine's own number — never recompute (Mark §1.1/§1.2; AGENTS.md #1).
    dd_pct_str = (
        f"{dd_pct}" if isinstance(dd_pct, (int, float)) else "—"
    )
    reason = str(drawdown_rec.get("reason", ""))

    action = _T7_ACTION_HE.format(drawdown_pct=dd_pct_str)
    snap = TriggerSnapshot(
        state=_PORTFOLIO_DRAWDOWN_STATE_LABEL,  # label string ONLY, never a
        open_r=None,                            # POSITION_STATE_*; never a
        age_days=None,                          # _RULESET key.
        reason=reason,
    )
    return [
        Task(
            task_type=TASK_ACK_DRAWDOWN_CUT,
            campaign_id=PORTFOLIO_CID,
            symbol="תיק",  # portfolio, not a ticker (SPRINT12_DESIGN §1.3)
            urgency=_T7_URGENCY,
            trigger_snapshot=snap,
            recommended_action=action,
            status=STATUS_OPEN,
            info_only=_T7_INFO_ONLY,
            notes=[],
            created_ts=created,
            closed_ts=None,
            user_id=uid,
        )
    ]


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


# T7 — the episode token is persisted append-only inside the existing
# lifecycle ``notes`` list (NO schema change — _upsert_lifecycle already
# supports notes; Mark §1.4 / SPRINT12_DESIGN §1.5(4)). A note line that
# begins with this marker carries the drawdown episode the user acked. The
# overlay join treats a stored ``done`` as satisfying T7 ONLY when the acked
# episode equals the CURRENT engine episode (else it is a NEW episode → the
# old ack does not mask it; surfaced again exactly once, still pull-only).
_T7_EPISODE_NOTE_PREFIX = "T7_EPISODE::"


def t7_episode_note(drawdown_rec: Optional[dict]) -> str:
    """The note string the Telegram ack layer passes to ``mark_done`` so the
    acked episode is persisted (append-only) on the existing lifecycle row.
    Empty when there is no episode (defensive)."""
    tok = _t7_episode_token(drawdown_rec)
    return f"{_T7_EPISODE_NOTE_PREFIX}{tok}" if tok else ""


def _acked_t7_episodes(notes: Any) -> set:
    """Episode tokens the user has acked, parsed from the stored notes
    (read-only over what was written; no fabrication)."""
    out: set = set()
    if not isinstance(notes, list):
        return out
    for n in notes:
        s = str(n)
        i = s.find(_T7_EPISODE_NOTE_PREFIX)
        if i != -1:
            out.add(s[i + len(_T7_EPISODE_NOTE_PREFIX):].strip())
    return out


def list_tasks(
    sb: Any,
    positions: list,
    *,
    now: datetime,
    user_id: Optional[str] = None,
    portfolio_drawdown: Optional[dict] = None,
    risk_settle_active: Optional[bool] = None,
) -> list[Task]:
    """Derive (live) ⟕ lifecycle (stored).

    1. ``derived = derive_tasks(positions, now=now)`` — the live per-position
       open set — plus, when ``portfolio_drawdown`` is supplied,
       ``derive_portfolio_tasks(...)`` appended (the T7 ack; Mark §1 /
       SPRINT12_DESIGN §1.3). T7 joins the SAME lifecycle table; it is NOT a
       ``_RULESET`` row (drift test untouched).
    2. Left-join stored done/skipped/notes overlays on
       ``(campaign_id, task_type)``: a derived task with a stored
       ``done``/``skipped`` overlay is returned with that status (so the bot
       can grey/hide it) and its stored notes attached.
    3. Auto-close on state transition / supersede is *implicit*: a stored
       overlay whose ``task_type`` the engine no longer emits simply isn't in
       ``derived`` so it is not surfaced — no engine state is mutated, and a
       P0 exit is NEVER laundered away (spec §3 / K5 / G8).
    4. T7 episode-keying (Mark §1.4): a stored ``done`` overlay satisfies T7
       ONLY when the acked episode token equals the CURRENT engine episode. A
       NEW episode (different engine ``reason``) is surfaced again exactly
       once — an old ack never masks a new drawdown.
    5. T7 auto-clear (Mark §1.4): when ``portfolio_drawdown is None`` (the
       engine call now returns None) AND ``risk_settle_active is False`` (the
       48h settle elapsed), an un-acked stored T7 row is NOT resurfaced — but
       its closure is honest: it closes as ``reason=condition_cleared``,
       NEVER as ``done`` unless the user actually acked (the cut was
       automatic, not a user duty; AGENTS.md #1). Since T7 is re-derived every
       render, "not resurfaced" == it simply does not appear in ``derived``
       once the engine stops returning a rec; no laundering of a user duty
       occurs because the ack is not a trade action (Mark §1.4).

    No write here. Pull-only (G5: no new push path; risk_monitor untouched).
    """
    uid = _resolve_uid(user_id)
    derived = derive_tasks(positions, now=now)
    if portfolio_drawdown is not None:
        derived.extend(
            derive_portfolio_tasks(drawdown_rec=portfolio_drawdown, now=now)
        )
    overlays = _read_lifecycle(sb, uid)
    cur_episode = _t7_episode_token(portfolio_drawdown)
    for task in derived:
        ov = overlays.get((task.campaign_id, task.task_type))
        if not ov:
            continue
        status = ov.get("status")
        notes = ov.get("notes")
        if (
            task.task_type == TASK_ACK_DRAWDOWN_CUT
            and task.campaign_id == PORTFOLIO_CID
        ):
            # T7 episode-keyed satisfaction (Mark §1.4): a stored done/skip
            # only counts if it acked THIS episode. A new episode → ignore the
            # stale overlay so the new drawdown surfaces again exactly once.
            if (
                status in (STATUS_DONE, STATUS_SKIPPED)
                and cur_episode
                and cur_episode in _acked_t7_episodes(notes)
            ):
                task.status = status
                task.closed_ts = ov.get("closed_ts")
            if isinstance(notes, list) and notes:
                task.notes = list(notes)
            continue
        if status in (STATUS_DONE, STATUS_SKIPPED):
            task.status = status
            task.closed_ts = ov.get("closed_ts")
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
