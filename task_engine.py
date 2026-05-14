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


# Task "kind" — used as the dedupe key for ack/snooze state.
KIND_BREAK_EVEN_2R    = "break_even_2r"
KIND_TRAIL_UP_3R      = "trail_up_3r"
KIND_DEAD_MONEY       = "dead_money"
KIND_STOP_BREACH      = "stop_breach"
KIND_TIGHTEN_TO_MA21  = "tighten_to_ma21"


# Urgency ranks — higher = more urgent. Display sorts descending by this.
URGENCY = {
    KIND_STOP_BREACH:     100,
    KIND_DEAD_MONEY:       80,
    KIND_BREAK_EVEN_2R:    60,
    KIND_TRAIL_UP_3R:      55,
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
    """Held > 21 days with open_r < 0.3 — capital tied up without progress."""
    days_held = int(row.get("days_held") or 0)
    open_r    = float(row.get("open_r") or 0)
    if days_held > 21 and open_r < 0.3:
        return Task(
            campaign_id=row["campaign_id"], symbol=row["symbol"],
            kind=KIND_DEAD_MONEY, urgency=URGENCY[KIND_DEAD_MONEY],
            title="⏳ הון מת — שקול יציאה",
            detail=(f"מוחזק `{days_held}` ימים, open R `{open_r:+.2f}`. "
                    f"הון נעול בלי תוצאה — פנה ייצור ליעדים אחרים."),
            suggested_level=None, suggested_action="exit",
        )
    return None


def _task_break_even_2r(row: dict) -> Optional[Task]:
    """At 2R or higher with stop still at-or-below entry — promote to BE."""
    open_r       = float(row.get("open_r") or 0)
    stop         = float(row.get("stop_loss") or 0)
    entry        = float(row.get("entry_price") or 0)
    if open_r >= 2.0 and entry > 0 and stop > 0 and stop <= entry * 1.001:
        return Task(
            campaign_id=row["campaign_id"], symbol=row["symbol"],
            kind=KIND_BREAK_EVEN_2R, urgency=URGENCY[KIND_BREAK_EVEN_2R],
            title="🛡️ הגיע ל-2R — קדם סטופ ל-Break-even",
            detail=(f"open R `{open_r:+.2f}` ≥ 2R. הקבע סטופ ב-`${entry:.2f}` "
                    f"(מחיר הכניסה) כדי לנעול את הכניסה ולהפוך את העסקה ל-risk-free."),
            suggested_level=round(entry, 2),
            suggested_action="update_stop",
        )
    return None


def _task_trail_up_3r(row: dict) -> Optional[Task]:
    """At 3R+ — trail stop to entry + 1R so 1R of profit is locked.

    Skipped if break_even_2r still pending (we want stops to climb
    monotonically — handle one rung at a time)."""
    open_r       = float(row.get("open_r") or 0)
    stop         = float(row.get("stop_loss") or 0)
    entry        = float(row.get("entry_price") or 0)
    initial_stop = float(row.get("initial_stop") or 0)
    if open_r < 3.0 or entry <= 0 or initial_stop <= 0 or initial_stop >= entry:
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
        title="📈 +3R — קדם סטופ ל-+1R",
        detail=(f"open R `{open_r:+.2f}` ≥ 3R. סטופ נוכחי `${stop:.2f}`. "
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
    _task_dead_money,
    _task_break_even_2r,
    _task_trail_up_3r,
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
