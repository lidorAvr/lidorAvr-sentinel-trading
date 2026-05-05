import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "action_queue_state.json"

def _now():
    return datetime.now(timezone.utc).isoformat()

def load_state():
    if not STATE_FILE.exists():
        return {"version": "action_queue_state_v1", "actions": {}, "notes": []}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": "action_queue_state_v1", "actions": {}, "notes": []}
        data.setdefault("version", "action_queue_state_v1")
        data.setdefault("actions", {})
        data.setdefault("notes", [])
        return data
    except Exception:
        return {"version": "action_queue_state_v1", "actions": {}, "notes": []}

def save_state(state):
    state.setdefault("version", "action_queue_state_v1")
    state.setdefault("actions", {})
    state.setdefault("notes", [])
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state

def load_action_state():
    return load_state()

def save_action_state(state):
    return save_state(state)

def _val(action, *names):
    if not isinstance(action, dict):
        return None
    for name in names:
        v = action.get(name)
        if v not in (None, "", []):
            return v
    return None

def action_key(action=None, symbol=None, campaign_id=None, decision=None, **kwargs):
    if isinstance(action, dict):
        campaign_id = campaign_id or _val(action, "campaign_id")
        symbol = symbol or _val(action, "symbol")
        decision = decision or _val(action, "decision_bias", "decision", "primary_decision")
        setup = _val(action, "setup_type", "setup")
        if campaign_id:
            return f"campaign:{campaign_id}"
        return "action:" + "|".join(str(x or "") for x in [symbol, setup, decision]).strip("|")

    key = kwargs.get("key") or kwargs.get("action_key")
    if key:
        return str(key)
    if campaign_id:
        return f"campaign:{campaign_id}"
    return f"symbol:{symbol or action or 'unknown'}"

def compute_fingerprint(action=None, **kwargs):
    if isinstance(action, dict):
        fields = [
            "symbol", "campaign_id", "setup_type", "decision_bias", "decision",
            "primary_action", "action", "trigger", "priority", "status",
            "current_stop", "entry_price", "current_price", "open_r", "total_r",
            "violations", "violation_count",
        ]
        raw = {k: action.get(k) for k in fields if action.get(k) not in (None, "", [])}
    else:
        raw = dict(kwargs)
        raw["action"] = action

    text = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()

def action_fingerprint(action=None, **kwargs):
    return compute_fingerprint(action, **kwargs)

def get_action_record(action=None, fingerprint=None, **kwargs):
    state = load_state()
    key = action_key(action, **kwargs)
    rec = state.get("actions", {}).get(key, {})
    return rec if isinstance(rec, dict) else {}

def _same_or_unknown(rec, fingerprint):
    if not fingerprint:
        return True
    saved = rec.get("fingerprint")
    return not saved or saved == fingerprint

def is_action_done(action=None, fingerprint=None, **kwargs):
    rec = get_action_record(action, fingerprint=fingerprint, **kwargs)
    return rec.get("status") == "done" and _same_or_unknown(rec, fingerprint)

def is_action_muted(action=None, fingerprint=None, **kwargs):
    rec = get_action_record(action, fingerprint=fingerprint, **kwargs)
    if rec.get("status") not in ("muted", "snoozed", "not_done"):
        return False
    if not _same_or_unknown(rec, fingerprint):
        return False

    until = rec.get("snooze_until")
    if until:
        try:
            return datetime.fromisoformat(until) > datetime.now(timezone.utc)
        except Exception:
            return True
    return True

def should_hide_action(action=None, fingerprint=None, **kwargs):
    fp = fingerprint or compute_fingerprint(action, **kwargs)
    return is_action_done(action, fp, **kwargs) or is_action_muted(action, fp, **kwargs)

def should_skip_action(action=None, fingerprint=None, **kwargs):
    return should_hide_action(action, fingerprint, **kwargs)

def hidden_reason(action=None, fingerprint=None, **kwargs):
    fp = fingerprint or compute_fingerprint(action, **kwargs)
    rec = get_action_record(action, fingerprint=fp, **kwargs)
    if rec.get("status") == "done" and _same_or_unknown(rec, fp):
        return "בוצע"
    if rec.get("status") in ("muted", "snoozed", "not_done") and _same_or_unknown(rec, fp):
        return "מושתק עד שינוי"
    return None

def mark_action_done(action=None, fingerprint=None, note=None, **kwargs):
    state = load_state()
    key = action_key(action, **kwargs)
    fp = fingerprint or compute_fingerprint(action, **kwargs)
    rec = state.setdefault("actions", {}).setdefault(key, {})
    rec.update({
        "status": "done",
        "fingerprint": fp,
        "note": note,
        "done_at": _now(),
        "updated_at": _now(),
    })
    save_state(state)
    return rec

def mark_done(*args, **kwargs):
    action = args[0] if args else kwargs.pop("action", None)
    return mark_action_done(action, **kwargs)

def mute_action(action=None, fingerprint=None, note=None, hours=None, **kwargs):
    state = load_state()
    key = action_key(action, **kwargs)
    fp = fingerprint or compute_fingerprint(action, **kwargs)
    rec = state.setdefault("actions", {}).setdefault(key, {})
    payload = {
        "status": "snoozed" if hours else "muted",
        "fingerprint": fp,
        "note": note,
        "updated_at": _now(),
    }
    if hours:
        payload["snooze_until"] = (datetime.now(timezone.utc) + timedelta(hours=float(hours))).isoformat()
    rec.update(payload)
    save_state(state)
    return rec

def snooze_action(action=None, fingerprint=None, hours=4, note=None, **kwargs):
    return mute_action(action, fingerprint=fingerprint, note=note, hours=hours, **kwargs)

def mark_not_done(action=None, fingerprint=None, note=None, hours=4, **kwargs):
    rec = snooze_action(action, fingerprint=fingerprint, hours=hours, note=note, **kwargs)
    rec["status"] = "not_done"
    state = load_state()
    key = action_key(action, **kwargs)
    state.setdefault("actions", {})[key] = rec
    state.setdefault("notes", []).append({
        "at": _now(),
        "action_key": key,
        "fingerprint": rec.get("fingerprint"),
        "note": note,
        "type": "not_done",
    })
    save_state(state)
    return rec

def add_action_note(action=None, note=None, fingerprint=None, **kwargs):
    state = load_state()
    key = action_key(action, **kwargs)
    state.setdefault("notes", []).append({
        "at": _now(),
        "action_key": key,
        "fingerprint": fingerprint or compute_fingerprint(action, **kwargs),
        "note": note,
        "type": "note",
    })
    save_state(state)
    return True

def reset_action(action=None, **kwargs):
    state = load_state()
    key = action_key(action, **kwargs)
    state.setdefault("actions", {}).pop(key, None)
    save_state(state)
    return True

# Compatibility aliases for older helper modules.
is_done = is_action_done
is_muted = is_action_muted
is_hidden = should_hide_action
mark_muted = mute_action
mark_snoozed = snooze_action
record_not_done = mark_not_done
add_note = add_action_note
