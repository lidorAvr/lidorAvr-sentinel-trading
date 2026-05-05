from datetime import datetime, timezone
import math
import json

_WARNED = set()

def _now():
    return datetime.now(timezone.utc).isoformat()

def _safe_float(v, default=0.0):
    try:
        if v is None:
            return default
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except Exception:
        return default

def _warn_once(key, msg):
    if key in _WARNED:
        return
    _WARNED.add(key)
    print(f"Journal warning: {msg}")

def _row_base(symbol=None, payload=None):
    p = payload or {}
    return {
        "symbol": symbol or p.get("symbol"),
        "created_at": _now(),
        "raw_payload": p,
    }

def write_position_snapshot(supabase, symbol=None, payload=None, **kwargs):
    p = dict(payload or {})
    p.update(kwargs)
    row = _row_base(symbol, p)
    row.update({
        "snapshot_at": p.get("snapshot_at") or _now(),
        "status": p.get("status"),
        "position_state": p.get("position_state") or p.get("state"),
        "decision_bias": p.get("decision_bias") or p.get("decision"),
        "current_price": _safe_float(p.get("current_price"), None),
        "entry_price": _safe_float(p.get("entry_price"), None),
        "open_r": _safe_float(p.get("open_r"), None),
        "total_r": _safe_float(p.get("total_r"), None),
    })
    try:
        return supabase.table("position_snapshots").insert(row).execute()
    except Exception as e:
        _warn_once("position_snapshots", f"position_snapshots write failed: {e}")
        return None

def write_decision_journal(supabase, symbol=None, payload=None, **kwargs):
    p = dict(payload or {})
    p.update(kwargs)
    row = _row_base(symbol, p)
    row.update({
        "decision_at": p.get("decision_at") or _now(),
        "status": p.get("status"),
        "position_state": p.get("position_state") or p.get("state"),
        "primary_action": p.get("primary_action") or p.get("action"),
        "decision_bias": p.get("decision_bias") or p.get("decision"),
        "severity": p.get("severity") or p.get("priority"),
    })
    try:
        return supabase.table("decision_journal").insert(row).execute()
    except Exception as e:
        _warn_once("decision_journal", f"decision_journal write failed: {e}")
        return None

def write_rule_violation(supabase, symbol=None, payload=None, **kwargs):
    p = dict(payload or {})
    p.update(kwargs)
    row = _row_base(symbol, p)
    row.update({
        "timestamp": p.get("timestamp") or _now(),
        "violation_type": p.get("violation_type") or p.get("type"),
        "severity": p.get("severity") or p.get("priority"),
        "message": p.get("message") or p.get("reason"),
    })
    try:
        return supabase.table("rule_violations").insert(row).execute()
    except Exception as e:
        _warn_once("rule_violations", f"rule_violations write failed: {e}")
        return None

def record_position_decision(*args, **kwargs):
    supabase = kwargs.pop("supabase", None)
    if args and supabase is None:
        supabase = args[0]
    if supabase is None:
        return None
    symbol = kwargs.get("symbol")
    payload = kwargs.get("payload") or kwargs
    write_position_snapshot(supabase, symbol=symbol, payload=payload)
    write_decision_journal(supabase, symbol=symbol, payload=payload)
    violations = payload.get("violations") or []
    if isinstance(violations, str):
        violations = [violations]
    for v in violations:
        if isinstance(v, dict):
            vp = v
        else:
            vp = {"violation_type": str(v), "message": str(v)}
        write_rule_violation(supabase, symbol=symbol, payload=vp)
    return True

def write_journal(*args, **kwargs):
    return record_position_decision(*args, **kwargs)

def log_decision(*args, **kwargs):
    return record_position_decision(*args, **kwargs)


# --- Compatibility layer for older risk_monitor journal hooks ---

def _looks_like_supabase(obj):
    return hasattr(obj, "table")

def _merge_payload(*items, **kwargs):
    payload = {}
    for item in items:
        if isinstance(item, dict):
            payload.update(item)
    payload.update({k: v for k, v in kwargs.items() if k != "supabase"})
    return payload

def record_position_cycle(*args, **kwargs):
    """
    Compatibility wrapper used by risk_monitor.
    Accepts any old/new call shape and records what it safely can.
    It must never crash the monitor.
    """
    try:
        supabase = kwargs.get("supabase")
        rest = list(args)

        if rest and _looks_like_supabase(rest[0]):
            supabase = rest.pop(0)

        payload = _merge_payload(*rest, **kwargs)
        symbol = payload.get("symbol")

        if not symbol:
            for item in rest:
                if isinstance(item, dict) and item.get("symbol"):
                    symbol = item.get("symbol")
                    break

        if supabase is not None:
            try:
                return record_position_decision(supabase=supabase, symbol=symbol, payload=payload)
            except Exception as e:
                _warn_once("record_position_cycle", f"record_position_cycle write failed: {e}")
                return None

        return None
    except Exception as e:
        _warn_once("record_position_cycle_outer", f"record_position_cycle skipped: {e}")
        return None

def record_campaign_cycle(*args, **kwargs):
    return record_position_cycle(*args, **kwargs)

def record_cycle(*args, **kwargs):
    return record_position_cycle(*args, **kwargs)

def record_position_snapshot(*args, **kwargs):
    return record_position_cycle(*args, **kwargs)

def __getattr__(name):
    # Keep risk-monitor alive if an older Journal hook name is still referenced.
    if name.startswith(("record_", "write_", "log_", "save_")):
        def _noop(*args, **kwargs):
            _warn_once(name, f"{name} compatibility noop")
            return None
        return _noop
    raise AttributeError(name)


# --- JSON-safe journal overrides ---

def _json_safe(v):
    try:
        from datetime import date, datetime
        if v is None or isinstance(v, (str, int, float, bool)):
            return v
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        if hasattr(v, "item"):
            return _json_safe(v.item())
        if isinstance(v, dict):
            return {str(k): _json_safe(val) for k, val in v.items()}
        if isinstance(v, (list, tuple, set)):
            return [_json_safe(x) for x in v]
        return str(v)
    except Exception:
        return str(v)

def _insert_safe(supabase, table, row, warn_key):
    try:
        return supabase.table(table).insert(_json_safe(row)).execute()
    except Exception as e:
        _warn_once(warn_key, f"{table} write failed: {e}")
        return None

def _row_base(symbol=None, payload=None):
    p = _json_safe(payload or {})
    return {
        "symbol": symbol or (p.get("symbol") if isinstance(p, dict) else None),
        "created_at": _now(),
        "raw_payload": p,
    }

def write_position_snapshot(supabase, symbol=None, payload=None, **kwargs):
    p = dict(payload or {})
    p.update(kwargs)
    row = _row_base(symbol, p)
    row.update({
        "snapshot_at": p.get("snapshot_at") or _now(),
        "status": p.get("status"),
        "position_state": p.get("position_state") or p.get("state"),
        "decision_bias": p.get("decision_bias") or p.get("decision"),
        "current_price": _safe_float(p.get("current_price"), None),
        "entry_price": _safe_float(p.get("entry_price"), None),
        "open_r": _safe_float(p.get("open_r"), None),
        "total_r": _safe_float(p.get("total_r"), None),
    })
    return _insert_safe(supabase, "position_snapshots", row, "position_snapshots")

def write_decision_journal(supabase, symbol=None, payload=None, **kwargs):
    p = dict(payload or {})
    p.update(kwargs)
    row = _row_base(symbol, p)
    row.update({
        "decision_at": p.get("decision_at") or _now(),
        "status": p.get("status"),
        "position_state": p.get("position_state") or p.get("state"),
        "primary_action": p.get("primary_action") or p.get("action"),
        "decision_bias": p.get("decision_bias") or p.get("decision"),
        "severity": p.get("severity") or p.get("priority"),
    })
    return _insert_safe(supabase, "decision_journal", row, "decision_journal")

def write_rule_violation(supabase, symbol=None, payload=None, **kwargs):
    p = dict(payload or {})
    p.update(kwargs)
    row = _row_base(symbol, p)
    row.update({
        "timestamp": p.get("timestamp") or _now(),
        "violation_type": p.get("violation_type") or p.get("type"),
        "severity": p.get("severity") or p.get("priority"),
        "message": p.get("message") or p.get("reason"),
    })
    return _insert_safe(supabase, "rule_violations", row, "rule_violations")

def record_position_decision(*args, **kwargs):
    supabase = kwargs.pop("supabase", None)
    rest = list(args)
    if rest and hasattr(rest[0], "table"):
        supabase = rest.pop(0)
    if supabase is None:
        return None

    payload = {}
    for item in rest:
        if isinstance(item, dict):
            payload.update(item)
    payload.update(kwargs)

    symbol = payload.get("symbol")
    write_position_snapshot(supabase, symbol=symbol, payload=payload)
    write_decision_journal(supabase, symbol=symbol, payload=payload)

    violations = payload.get("violations") or []
    if isinstance(violations, str):
        violations = [violations]
    for v in violations:
        vp = v if isinstance(v, dict) else {"violation_type": str(v), "message": str(v)}
        write_rule_violation(supabase, symbol=symbol, payload=vp)
    return True


# --- Schema-adaptive journal insert overrides ---
# Supabase tables in this project evolved over time. These writers retry without
# columns that are not present, so journal logging never breaks risk monitoring.

import re as _sentinel_re

def _missing_column_from_error(exc):
    msg = str(exc)
    m = _sentinel_re.search(r"Could not find the '([^']+)' column", msg)
    return m.group(1) if m else None

def _insert_safe(supabase, table, row, warn_key):
    clean = _json_safe(row)
    if not isinstance(clean, dict):
        clean = {}

    dropped = []
    last_error = None

    for _ in range(20):
        try:
            return supabase.table(table).insert(clean).execute()
        except Exception as e:
            last_error = e
            col = _missing_column_from_error(e)
            if col and col in clean:
                dropped.append(col)
                clean.pop(col, None)
                continue
            break

    _warn_once(warn_key, f"{table} write skipped after schema adaptation: {last_error}; dropped={dropped}")
    return None

def _row_base(symbol=None, payload=None):
    p = _json_safe(payload or {})
    return {
        "symbol": symbol or (p.get("symbol") if isinstance(p, dict) else None),
        "raw_payload": p,
    }

def write_position_snapshot(supabase, symbol=None, payload=None, **kwargs):
    p = dict(payload or {})
    p.update(kwargs)
    row = _row_base(symbol, p)
    row.update({
        "snapshot_at": p.get("snapshot_at") or _now(),
        "status": p.get("status"),
        "position_state": p.get("position_state") or p.get("state"),
        "decision_bias": p.get("decision_bias") or p.get("decision"),
        "current_price": _safe_float(p.get("current_price"), None),
        "entry_price": _safe_float(p.get("entry_price"), None),
        "open_r": _safe_float(p.get("open_r"), None),
        "total_r": _safe_float(p.get("total_r"), None),
    })
    return _insert_safe(supabase, "position_snapshots", row, "position_snapshots")

def write_decision_journal(supabase, symbol=None, payload=None, **kwargs):
    p = dict(payload or {})
    p.update(kwargs)
    row = _row_base(symbol, p)
    row.update({
        "decision_at": p.get("decision_at") or _now(),
        "status": p.get("status"),
        "position_state": p.get("position_state") or p.get("state"),
        "primary_action": p.get("primary_action") or p.get("action"),
        "decision_bias": p.get("decision_bias") or p.get("decision"),
        "severity": p.get("severity") or p.get("priority"),
    })
    return _insert_safe(supabase, "decision_journal", row, "decision_journal")

def write_rule_violation(supabase, symbol=None, payload=None, **kwargs):
    p = dict(payload or {})
    p.update(kwargs)
    row = _row_base(symbol, p)
    row.update({
        "timestamp": p.get("timestamp") or _now(),
        "violation_type": p.get("violation_type") or p.get("type"),
        "severity": p.get("severity") or p.get("priority"),
        "message": p.get("message") or p.get("reason"),
    })
    return _insert_safe(supabase, "rule_violations", row, "rule_violations")

# --- BEGIN Sentinel journal action fields inline patch 2026-05-04 ---
def _sentinel_primary(payload):
    card = payload.get("decision_card") or {}
    if not isinstance(card, dict):
        card = {}
    return card, (card.get("primary_action") or payload.get("suggested_action") or payload.get("preferred_action") or payload.get("action"))

def write_position_snapshot(supabase, symbol=None, payload=None, **kwargs):
    p = dict(payload or {})
    p.update(kwargs)
    card, primary = _sentinel_primary(p)
    row = _row_base(symbol, p)
    row.update({
        "campaign_id": p.get("campaign_id"), "trade_id": p.get("trade_id"), "date": p.get("date"),
        "snapshot_at": p.get("snapshot_at") or _now(), "status": p.get("status"),
        "position_state": p.get("position_state") or p.get("state"), "management_state": p.get("management_state"),
        "setup_type": p.get("setup_type"), "decision_bias": card.get("bias_he") or p.get("decision_bias") or p.get("decision"),
        "suggested_action": primary, "suggested_stop": _safe_float(p.get("suggested_stop"), None),
        "current_stop": _safe_float(p.get("current_stop") or p.get("stop_loss"), None),
        "violation_count": p.get("violation_count"), "state_he": p.get("state_he"),
        "violations": p.get("violations") or [], "decision_card": card, "features": p.get("features") or {},
        "current_price": _safe_float(p.get("current_price"), None), "entry_price": _safe_float(p.get("entry_price"), None),
        "open_r": _safe_float(p.get("open_r"), None), "total_r": _safe_float(p.get("total_r"), None),
        "exposure_pct": _safe_float(p.get("exposure_pct"), None),
        "locked_profit": _safe_float(p.get("locked_profit"), None),
        "giveback_risk": _safe_float(p.get("giveback_risk"), None),
    })
    return _insert_safe(supabase, "position_snapshots", row, "position_snapshots")

def write_decision_journal(supabase, symbol=None, payload=None, **kwargs):
    p = dict(payload or {})
    p.update(kwargs)
    card, primary = _sentinel_primary(p)
    row = _row_base(symbol, p)
    row.update({
        "campaign_id": p.get("campaign_id"), "trade_id": p.get("trade_id"),
        "decision_at": p.get("decision_at") or _now(), "status": p.get("status"),
        "position_state": p.get("position_state") or p.get("state"), "primary_action": primary,
        "decision_bias": card.get("bias_he") or p.get("decision_bias") or p.get("decision"),
        "severity": p.get("severity") or p.get("priority"), "urgency": card.get("urgency") or p.get("urgency"),
        "violation_count": p.get("violation_count"), "reasons": card.get("reasons") or p.get("reasons") or [],
        "decision_card": card,
    })
    return _insert_safe(supabase, "decision_journal", row, "decision_journal")
# --- END Sentinel journal action fields inline patch 2026-05-04 ---
