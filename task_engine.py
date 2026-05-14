"""task_engine.py — Open-task computation for the "📋 סקירת משימות" UI.

Each position can have zero or more open management tasks (move stop,
exit dead money, etc.). The Telegram bot surfaces them grouped by symbol;
the user can approve (with confirmation of the suggested level OR a
manual edit) or snooze.

Design:
  - Pure functions. No bot, no supabase, no I/O. Caller passes the
    aggregated campaign rows (engine_core.get_open_positions_campaign
    output) and current state file (task acks/snoozes).
  - Returns a list of `Task` dataclass instances, sorted by urgency
    descending.
  - Stops-only MVP per 2026-05-14 user choice. Earnings/MA/cluster
    tasks deferred.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
import math
import time
from typing import Optional

import setup_profile as sp


# Task "kind" — used as the dedupe key for ack/snooze state.
KIND_BREAK_EVEN_2R    = "break_even_2r"
KIND_TRAIL_UP_3R      = "trail_up_3r"
KIND_DEAD_MONEY       = "dead_money"
KIND_STOP_BREACH      = "stop_breach"
KIND_TIGHTEN_TO_MA21  = "tighten_to_ma21"
KIND_LOOSE_STOP       = "loose_stop"  # Sprint 11 — flag initial-stop > setup's max


# Urgency ranks — higher = more urgent. Display sorts descending by this.
URGENCY = {
    KIND_STOP_BREACH:     100,
    KIND_DEAD_MONEY:       80,
    KIND_BREAK_EVEN_2R:    60,
    KIND_TRAIL_UP_3R:      55,
    KIND_LOOSE_STOP:       50,
    KIND_TIGHTEN_TO_MA21:  30,
}


@dataclass
class Task:
    """One open management task on one campaign.

    The dedupe key is (campaign_id, kind). Once acked, the same task
    won't reappear until either the position state changes (e.g., stop
    is actually moved) or the snooze expires.
    """
    campaign_id: str
    symbol: str
    kind: str
    urgency: int
    title: str
    detail: str
    suggested_level: Optional[float]    # None for "exit" tasks; price for stop tasks
    suggested_action: str               # "update_stop" / "exit" / "review"

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def dedup_key(self) -> str:
        return f"{self.campaign_id}|{self.kind}"


# ── Per-task rules ─────────────────────────────────────────────────────────────

def _task_stop_breach(row: dict) -> Optional[Task]:
    """Current price below or at the stop, OR open_r ≤ -1.0. Exit now."""
    open_r = float(row.get("open_r") or 0)
    stop   = float(row.get("stop_loss") or 0)
    curr   = float(row.get("current_price") or 0)
    if stop <= 0 or curr <= 0:
        return None
    if open_r <= -1.0 or curr <= stop:
        return Task(
            campaign_id=row["campaign_id"], symbol=row["symbol"],
            kind=KIND_STOP_BREACH, urgency=URGENCY[KIND_STOP_BREACH],
            title="🚨 חריגה מהסטופ — צא כעת",
            detail=(f"מחיר נוכחי `${curr:.2f}` ≤ סטופ `${stop:.2f}`, "
                    f"open R `{open_r:+.2f}`. עזיבת השוק לפי התוכנית."),
            suggested_level=None, suggested_action="exit",
        )
    return None


def _task_dead_money(row: dict) -> Optional[Task]:
    """Held longer than the SETUP's dead_money_days with low R.

    BLOCKER #3 fix (research audit 2026-05-14): the previous fixed
    threshold (21d / 0.3R) was past EP's shelf life — by D21 an EP is
    long gone, so the rule only ever fired for VCP. Now the profile
    decides:
        VCP   → 21d / 0.3R   (unchanged)
        EP    → 10d / 1.5R   (matches Mark's "exit by week 2-3" rule)
        SWING → 14d / 0.5R
    """
    days_held = int(row.get("days_held") or 0)
    open_r    = float(row.get("open_r") or 0)
    profile   = sp.get_profile(row.get("setup_type", ""))
    if days_held > profile.dead_money_days and open_r < profile.dead_money_r:
        return Task(
            campaign_id=row["campaign_id"], symbol=row["symbol"],
            kind=KIND_DEAD_MONEY, urgency=URGENCY[KIND_DEAD_MONEY],
            title="⏳ הון מת — שקול יציאה",
            detail=(f"מוחזק `{days_held}` ימים (סף *{profile.label}*: "
                    f"`{profile.dead_money_days}d`), open R `{open_r:+.2f}` "
                    f"(סף: `{profile.dead_money_r:+.2f}R`). "
                    f"הון נעול בלי תוצאה — פנה ייצור ליעדים אחרים."),
            suggested_level=None, suggested_action="exit",
        )
    return None


def _task_loose_stop(row: dict) -> Optional[Task]:
    """BLOCKER #2 (research audit 2026-05-14): initial stop wider than
    the setup's max_initial_stop_pct = a methodology breach silently
    accepted by the engine. Surface it as a task so the user either
    tightens the stop or acknowledges the deviation (e.g., for a
    deliberately wider swing entry).
    """
    entry = float(row.get("entry_price") or 0)
    init  = float(row.get("initial_stop") or 0)
    grade_info = sp.validate_initial_stop(entry, init, row.get("setup_type", ""))
    if grade_info["grade"] != sp.STOP_GRADE_OUT_OF_SPEC:
        return None
    return Task(
        campaign_id=row["campaign_id"], symbol=row["symbol"],
        kind=KIND_LOOSE_STOP, urgency=URGENCY[KIND_LOOSE_STOP],
        title="🔴 סטופ התחלתי חורג מהמתודולוגיה",
        detail=(f"סטופ התחלתי `${init:.2f}` = "
                f"`{grade_info['stop_pct']:.1f}%` מתחת לכניסה `${entry:.2f}`. "
                f"סף {sp.get_profile(row.get('setup_type', '')).label}: "
                f"עד `{grade_info['max_allowed_pct']:.0f}%`. "
                f"שקול הידוק הסטופ או סגירה ידנית של הקמפיין."),
        suggested_level=None, suggested_action="review",
    )


def _task_break_even_2r(row: dict) -> Optional[Task]:
    """At profit_protect_r (per setup) or higher with stop still at-or-below
    entry — promote to BE. Sprint 11: threshold is now setup-aware. EP's
    profit_protect_r=1.5 (move stop to BE earlier; the EP "pop" is the
    move) vs VCP's 2.0 (classic Minervini)."""
    open_r       = float(row.get("open_r") or 0)
    stop         = float(row.get("stop_loss") or 0)
    entry        = float(row.get("entry_price") or 0)
    profile      = sp.get_profile(row.get("setup_type", ""))
    if (open_r >= profile.profit_protect_r and entry > 0 and stop > 0
            and stop <= entry * 1.001):
        return Task(
            campaign_id=row["campaign_id"], symbol=row["symbol"],
            kind=KIND_BREAK_EVEN_2R, urgency=URGENCY[KIND_BREAK_EVEN_2R],
            title=f"🛡️ הגיע ל-{profile.profit_protect_r:.1f}R — קדם סטופ ל-Break-even",
            detail=(f"open R `{open_r:+.2f}` ≥ `{profile.profit_protect_r:.1f}R` "
                    f"(סף *{profile.label}*). הקבע סטופ ב-`${entry:.2f}` "
                    f"(מחיר הכניסה) כדי לנעול את הכניסה ולהפוך את העסקה ל-risk-free."),
            suggested_level=round(entry, 2),
            suggested_action="update_stop",
        )
    return None


def _task_trail_up_3r(row: dict) -> Optional[Task]:
    """At profit_protect_r + 1R — trail stop to entry + 1R so 1R of profit
    is locked. Sprint 11: setup-aware. For VCP this fires at 3R (same as
    before). For EP this fires at 2.5R (profit_protect 1.5 + 1).

    Skipped if break_even_2r still pending (we want stops to climb
    monotonically)."""
    open_r       = float(row.get("open_r") or 0)
    stop         = float(row.get("stop_loss") or 0)
    entry        = float(row.get("entry_price") or 0)
    initial_stop = float(row.get("initial_stop") or 0)
    profile      = sp.get_profile(row.get("setup_type", ""))
    trail_trigger_r = profile.profit_protect_r + 1.0
    if open_r < trail_trigger_r or entry <= 0 or initial_stop <= 0 or initial_stop >= entry:
        return None
    one_r_dollars = entry - initial_stop
    target_stop = round(entry + one_r_dollars, 2)
    # Only suggest if we'd actually be moving UP (no recommending a
    # tighter-then-current step in a stable direction).
    if stop >= target_stop:
        return None
    # Defer to break_even_2r when stop is still below entry — that one
    # is the prerequisite step.
    if stop <= entry * 1.001:
        return None
    return Task(
        campaign_id=row["campaign_id"], symbol=row["symbol"],
        kind=KIND_TRAIL_UP_3R, urgency=URGENCY[KIND_TRAIL_UP_3R],
        title=f"📈 +{trail_trigger_r:.1f}R — קדם סטופ ל-+1R",
        detail=(f"open R `{open_r:+.2f}` ≥ `{trail_trigger_r:.1f}R` "
                f"(סף *{profile.label}*). סטופ נוכחי `${stop:.2f}`. "
                f"העלה ל-`${target_stop:.2f}` (כניסה + 1R) — נועל לפחות 1R רווח."),
        suggested_level=target_stop,
        suggested_action="update_stop",
    )


def _task_tighten_to_ma21(row: dict) -> Optional[Task]:
    """When price is firmly above MA21 and current stop is far below it,
    suggest tightening to just under MA21 (Minervini-style trail)."""
    curr  = float(row.get("current_price") or 0)
    stop  = float(row.get("stop_loss") or 0)
    ma21  = float(row.get("ma21") or 0)
    if curr <= 0 or stop <= 0 or ma21 <= 0:
        return None
    # Trigger: price clearly above MA21 (≥2%) AND stop is more than
    # ~3% below MA21 (room to tighten without whipsaw).
    if curr < ma21 * 1.02:
        return None
    if stop >= ma21 * 0.97:
        return None
    target_stop = round(ma21 * 0.98, 2)
    if target_stop <= stop:
        return None
    return Task(
        campaign_id=row["campaign_id"], symbol=row["symbol"],
        kind=KIND_TIGHTEN_TO_MA21, urgency=URGENCY[KIND_TIGHTEN_TO_MA21],
        title="🎯 הדק סטופ מתחת ל-MA21",
        detail=(f"מחיר `${curr:.2f}` מעל MA21 `${ma21:.2f}`. "
                f"סטופ נוכחי `${stop:.2f}` רחוק מתחת ל-MA21. "
                f"שקול הידוק ל-`${target_stop:.2f}` (~2% מתחת ל-MA21)."),
        suggested_level=target_stop,
        suggested_action="update_stop",
    )


_RULES = [
    _task_stop_breach,     # always evaluated first (most urgent)
    _task_dead_money,      # Sprint 11: setup-aware threshold
    _task_break_even_2r,   # Sprint 11: setup-aware threshold
    _task_trail_up_3r,     # Sprint 11: setup-aware threshold
    _task_loose_stop,      # Sprint 11: surface initial-stop > setup's max
    _task_tighten_to_ma21,
]


def compute_open_tasks(positions: list[dict],
                        snoozed: Optional[dict] = None,
                        now_ts: Optional[float] = None) -> list[Task]:
    """For each position, evaluate every rule and collect Tasks. Filter
    out tasks whose dedup_key is still snoozed.

    Args:
        positions: list of dicts with keys
            campaign_id, symbol, current_price, entry_price, stop_loss,
            initial_stop, open_r, days_held, setup_type, ma21 (optional).
            ALGO setups are skipped entirely — they're externally managed.
        snoozed: dict {dedup_key: unix_ts_until_active_again}
        now_ts: override current time for testing

    Returns:
        Tasks sorted by (urgency desc, symbol asc).
    """
    snoozed = snoozed or {}
    now_ts = now_ts if now_ts is not None else time.time()
    out: list[Task] = []
    for pos in positions:
        if str(pos.get("setup_type", "")).upper() == "ALGO":
            continue  # ALGO is externally managed — never gets management tasks
        if not pos.get("campaign_id") or not pos.get("symbol"):
            continue
        for rule in _RULES:
            try:
                t = rule(pos)
            except Exception:
                # A bad row must not bring down the whole task review
                continue
            if t is None:
                continue
            # Honor snooze: skip if its expiry is in the future
            if snoozed.get(t.dedup_key, 0) > now_ts:
                continue
            out.append(t)
    out.sort(key=lambda x: (-x.urgency, x.symbol))
    return out


def group_by_symbol(tasks: list[Task]) -> dict[str, list[Task]]:
    """Convenience: group tasks by symbol for the menu listing.
    Each symbol's task list stays in the input urgency order."""
    grouped: dict[str, list[Task]] = {}
    for t in tasks:
        grouped.setdefault(t.symbol, []).append(t)
    return grouped


def render_task_line(task: Task) -> str:
    """Single-line Hebrew rendering of a task for the inline list view."""
    return f"▸ {task.title}"


def render_task_detail(task: Task) -> str:
    """Multi-line Hebrew rendering for the per-task confirmation screen."""
    lines = [task.title, "", task.detail]
    if task.suggested_level is not None:
        lines.append("")
        lines.append(f"רמה מוצעת: `${task.suggested_level:.2f}`")
    return "\n".join(lines)
