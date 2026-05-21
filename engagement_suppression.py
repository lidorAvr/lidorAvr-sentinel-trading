"""
engagement_suppression.py — §X5 Silence-As-Beat primitive (leaf module).

Engagement-meeting Wave-3A (21/05/2026). Codifies MARK_MEETING_UX_RULINGS
§X5: *absence IS the surface* during missed-day / -2R-day / settle-period
windows. The mentor (Sentinel) is not offended by absence. "We noticed
you've been quiet" passive-aggressive messages are BANNED.

This module is the SHARED suppression gate that `risk_monitor.py` and
`report_scheduler.py` (and any future engagement caller) consult before
emitting an engagement push. It is intentionally a LEAF module: stdlib
only (datetime / typing), no imports from engine / formatters / bot —
zero cycle risk; importable from any layer.

The three rules (composite, hierarchical):
  1. TWO_R_DOWN  — today's closed R is at or below -2.0R. The founder
                   had a bad day; honour the loss, do not coach. Silent
                   until next 16:00 IL.
  2. SETTLE      — existing risk-settle-period (adaptive_risk_engine.
                   `get_risk_settle_info`) is active. Suppress risk-raise
                   reminders during this window.
  3. MISSED_DAY  — the founder has been quiet ≥ threshold hours. No
                   engagement pushes during the silence. The welcome-back
                   beat fires on user-return through a SEPARATE surface,
                   never on a "we noticed" timer.

Each rule is also exposed as a stand-alone predicate so callers can
ask "are we in a -2R day?" without the composite hierarchy. Tests pin
the hierarchy AND each predicate independently.

Public API:
  - is_two_r_down_day(todays_R)
  - is_settle_period_active(settle_info)
  - is_missed_day_window(days_since_last_interaction, threshold_hours)
  - should_suppress_engagement(...) — composite gate; returns dict with
        `suppress` (bool), `rule_id` (str), `reason` (str)

Mark §X5 binding: failure to suppress in any of the three windows is a
§X5 violation regardless of how warmly the message is phrased. The
escape hatch is silence, not nuance.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional


# ─── Defaults (tunable per caller; pinned by tests) ──────────────────────────

DEFAULT_TWO_R_THRESHOLD = -2.0
"""Today's closed R at or below this triggers TWO_R_DOWN. Mark §X5 binding."""

DEFAULT_MISSED_DAY_THRESHOLD_HOURS = 48.0
"""Hours since last user interaction that puts us in the MISSED_DAY window.
E4 missed-day rule: silence first 48h+ post-last-touch."""


# ─── Stand-alone predicates ─────────────────────────────────────────────────

def is_two_r_down_day(
    todays_R: Optional[float],
    threshold: float = DEFAULT_TWO_R_THRESHOLD,
) -> bool:
    """True iff today's closed R is at or below the -2R threshold.

    `None` means "no closed trades today" — NOT a -2R day. The honest
    default; never invent a verdict when the data is absent (Mark §3 /
    §X1). The threshold default is -2.0; callers can override but ALL
    overrides must remain ≤ -1.0 (a -0.5R day is not a "bad day" —
    softening the threshold would silently undo §X5).
    """
    if todays_R is None:
        return False
    return float(todays_R) <= float(threshold)


def is_settle_period_active(settle_info: Optional[dict]) -> bool:
    """True iff the settle-period dict from `get_risk_settle_info()`
    indicates an active settle window.

    `None` / empty / `active=False` all return False. Honest fallback:
    no settle info → no settle suppression (different rules may still
    apply).
    """
    if not settle_info:
        return False
    return bool(settle_info.get("active"))


def is_missed_day_window(
    days_since_last_interaction: Optional[float],
    threshold_hours: float = DEFAULT_MISSED_DAY_THRESHOLD_HOURS,
) -> bool:
    """True iff the gap since the founder's last interaction is ≥ the
    missed-day threshold.

    `None` means "we don't know when he last interacted" — NOT a missed
    day. Honest default; absent data is never spun into a verdict.
    """
    if days_since_last_interaction is None:
        return False
    hours_gap = float(days_since_last_interaction) * 24.0
    return hours_gap >= float(threshold_hours)


# ─── Composite gate ─────────────────────────────────────────────────────────

def should_suppress_engagement(
    *,
    todays_R: Optional[float] = None,
    settle_info: Optional[dict] = None,
    days_since_last_interaction: Optional[float] = None,
    two_r_threshold: float = DEFAULT_TWO_R_THRESHOLD,
    missed_day_threshold_hours: float = DEFAULT_MISSED_DAY_THRESHOLD_HOURS,
) -> dict:
    """Composite §X5 suppression gate.

    Returns:
        {
            'suppress':  bool — True to NOT emit an engagement push,
            'rule_id':   one of 'TWO_R_DOWN' / 'SETTLE' / 'MISSED_DAY' / 'NONE',
            'reason':    short human-readable string (logged when suppress=True),
        }

    Hierarchy (first matching rule wins):
        1. TWO_R_DOWN  — strongest signal; the founder is hurting.
        2. SETTLE      — existing risk-settle window; respect it.
        3. MISSED_DAY  — the founder has been quiet.
        4. NONE        — proceed with the engagement push.

    The hierarchy is intentional. A -2R day inside an active settle
    window should LOG as TWO_R_DOWN (the more emotionally load-bearing
    rule). A missed-day window during a -2R day stays TWO_R_DOWN until
    the next 16:00 IL boundary (which the caller is responsible for
    enforcing — this module is pure-functional, no clock state).

    All inputs are optional; absent inputs default to "no signal in
    this rule" (NOT a positive trigger). Mark §3 / §X1: absent data
    must NEVER imply a verdict.
    """
    if is_two_r_down_day(todays_R, threshold=two_r_threshold):
        return {
            "suppress": True,
            "rule_id": "TWO_R_DOWN",
            "reason": (
                f"-2R day floor — silent until next 16:00 IL "
                f"(today's R={float(todays_R):.2f}R)"
            ),
        }

    if is_settle_period_active(settle_info):
        hrs = float((settle_info or {}).get("hours_remaining", 0) or 0)
        direction = str((settle_info or {}).get("dir", "") or "")
        return {
            "suppress": True,
            "rule_id": "SETTLE",
            "reason": (
                f"Settle-period active — {hrs:.0f}h remaining"
                + (f" (dir={direction})" if direction else "")
            ),
        }

    if is_missed_day_window(
        days_since_last_interaction,
        threshold_hours=missed_day_threshold_hours,
    ):
        return {
            "suppress": True,
            "rule_id": "MISSED_DAY",
            "reason": (
                f"Missed-day window — last interaction "
                f"{float(days_since_last_interaction):.1f}d ago "
                f"(threshold {missed_day_threshold_hours/24:.1f}d)"
            ),
        }

    return {"suppress": False, "rule_id": "NONE", "reason": ""}


# ─── Convenience: format the suppression decision for audit/log line ─────────

def format_suppression_for_audit(decision: dict, now: Optional[datetime] = None) -> str:
    """Render a one-line audit log entry for a suppression event.

    Stable shape for forensic queries — callers should write this string
    to their existing logger (`risk_monitor` stdout, `report_scheduler`
    logger). No I/O in this function.

    Example output (clock-prefixed when `now` is supplied):
        '[2026-05-21T22:30:00] §X5 SUPPRESS rule=TWO_R_DOWN reason="-2R day floor..."'

    A non-suppress decision returns "" so callers can do
    `if line: print(line)` cleanly.
    """
    if not decision.get("suppress"):
        return ""
    prefix = f"[{now.isoformat(timespec='seconds')}] " if now else ""
    rule = str(decision.get("rule_id", "?"))
    reason = str(decision.get("reason", "")).strip()
    return f'{prefix}§X5 SUPPRESS rule={rule} reason="{reason}"'
