"""task_state.py — Persist acks and snoozes for the Task Review feature.

State file: `/app/task_state.json`. Schema:
    {
        "snoozed": {
            "<campaign_id>|<kind>": <unix_ts_until_active_again>
        },
        "last_action": {
            "<campaign_id>|<kind>": {
                "action": "approve"|"snooze"|"dismiss",
                "ts": <unix>,
                "before": <value_or_null>,
                "after":  <value_or_null>
            }
        }
    }

Acks (approval) write to `last_action` for audit; the dedup_key is
removed from `snoozed` so the user sees the task again if the
underlying position state still satisfies the rule (e.g., they
approved BE-at-2R but didn't actually update the stop in Supabase —
the rule will surface it again).

Snooze writes `snoozed[key]` with an expiry timestamp.

All functions are defensive: missing file, corrupt JSON, write errors
are swallowed (return False / no-op). Never raises.
"""
from __future__ import annotations
import json
import os
import time
from typing import Optional


TASK_STATE_FILE = "/app/task_state.json"

# Snooze durations (seconds)
SNOOZE_SHORT = 24 * 3600        # 1 day  — "⏰ דחה"
SNOOZE_LONG  = 30 * 24 * 3600   # 30 days — "❌ דלג"


def _empty() -> dict:
    return {"snoozed": {}, "last_action": {}}


def _resolve_path(path: Optional[str]) -> str:
    """Resolve the state-file path. Defaulting to None and looking up
    `TASK_STATE_FILE` at call time (instead of binding it as a function
    default) makes the module variable monkey-patchable from tests and
    overridable at runtime if/when a per-user state file is needed.

    Python binds default arguments at function-definition time, so
    `def f(path: str = TASK_STATE_FILE)` would freeze whatever value
    TASK_STATE_FILE had at import. CI runners without /app/ would
    silently write to a non-existent dir."""
    return path if path is not None else TASK_STATE_FILE


def load_state(path: Optional[str] = None) -> dict:
    """Return the persisted state or an empty skeleton on any failure."""
    path = _resolve_path(path)
    try:
        if not os.path.exists(path):
            return _empty()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _empty()
        data.setdefault("snoozed", {})
        data.setdefault("last_action", {})
        return data
    except Exception:
        return _empty()


def save_state(state: dict, path: Optional[str] = None) -> bool:
    """Atomic write (tmp + os.replace). Returns True on success."""
    path = _resolve_path(path)
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _purge_expired(snoozed: dict, now_ts: float) -> dict:
    """Drop keys whose expiry has passed."""
    return {k: v for k, v in snoozed.items() if v > now_ts}


def get_snoozes(path: Optional[str] = None,
                 now_ts: Optional[float] = None) -> dict:
    """Return active snoozes (expired ones cleaned out)."""
    now_ts = now_ts if now_ts is not None else time.time()
    state = load_state(path)
    return _purge_expired(state.get("snoozed", {}), now_ts)


def snooze_task(dedup_key: str, duration_sec: int,
                path: Optional[str] = None,
                now_ts: Optional[float] = None) -> bool:
    """Snooze a task until now_ts + duration_sec. Also records the
    action in last_action for audit."""
    now_ts = now_ts if now_ts is not None else time.time()
    state = load_state(path)
    state["snoozed"][dedup_key] = now_ts + duration_sec
    state["last_action"][dedup_key] = {
        "action": "snooze",
        "ts": now_ts,
        "duration_sec": duration_sec,
    }
    return save_state(state, path)


def dismiss_task(dedup_key: str, path: Optional[str] = None,
                  now_ts: Optional[float] = None) -> bool:
    """Long snooze (30 days) — "❌ דלג"."""
    return snooze_task(dedup_key, SNOOZE_LONG, path, now_ts)


def approve_task(dedup_key: str, before: Optional[float],
                  after: Optional[float],
                  path: Optional[str] = None,
                  now_ts: Optional[float] = None) -> bool:
    """Record an approve action. Does NOT auto-snooze — the underlying
    rule will re-fire next cycle if the position state still satisfies
    it (catches "user approved but Supabase write failed" cases).

    The caller is responsible for the actual stop update in Supabase
    and the audit_log entry — this function only records the
    task-state side.
    """
    now_ts = now_ts if now_ts is not None else time.time()
    state = load_state(path)
    state["last_action"][dedup_key] = {
        "action": "approve",
        "ts": now_ts,
        "before": before,
        "after": after,
    }
    # Short snooze after approval — avoids the task re-firing on the
    # same cycle BEFORE Supabase write propagates. The rule will pick
    # it up again ~1 day later if the state still satisfies (no harm,
    # just a reminder).
    state["snoozed"][dedup_key] = now_ts + 3600  # 1 hour grace
    return save_state(state, path)


def last_action(dedup_key: str, path: Optional[str] = None) -> Optional[dict]:
    """Return the last recorded action for a task, or None."""
    state = load_state(path)
    return state.get("last_action", {}).get(dedup_key)
