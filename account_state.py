"""
account_state.py — single source of truth for NAV and account settings.
The reporting service reads NAV exclusively through this module.
Existing bot/engine code keeps its own getters; a future refactor will
consolidate everything here.
"""
import os, json
from datetime import datetime
from typing import Optional

_CONFIG_PATHS   = ["/app/sentinel_config.json", "sentinel_config.json"]
_STALE_HOURS    = 24
_CRITICAL_HOURS = 48


def load() -> dict:
    """
    Load account state from sentinel_config.json.
    Always returns a safe dict — never raises.

    Keys returned:
        nav, total_deposited, risk_pct_input,
        nav_source ("broker" | "deposited" | "fallback"),
        nav_updated_at, age_hours,
        freshness ("fresh" | "stale" | "critical" | "unknown"),
        freshness_label, is_stale, is_critical, ok
    """
    path = _find_config()
    if path is None:
        return _fallback("sentinel_config.json לא נמצא")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _fallback("תצורת JSON לא תקינה — לא אובייקט")
    except Exception as e:
        return _fallback(f"שגיאת קריאה: {e}")

    nav = float(data.get("nav", data.get("total_deposited", 7500.0)))
    nav_source    = "broker" if "nav" in data else "deposited"
    nav_updated_at = data.get("nav_updated_at")
    age_hours, freshness, freshness_label = _freshness(nav_updated_at)

    return {
        "nav":             nav,
        "total_deposited": float(data.get("total_deposited", 7500.0)),
        "risk_pct_input":  float(data.get("risk_pct_input", 0.5)),
        "nav_source":      nav_source,
        "nav_updated_at":  nav_updated_at,
        "age_hours":       age_hours,
        "freshness":       freshness,
        "freshness_label": freshness_label,
        "is_stale":        freshness in ("stale", "critical", "unknown"),
        "is_critical":     freshness == "critical",
        "ok":              True,
    }


def target_risk_usd(account: dict) -> float:
    """Convenience: nav * risk_pct / 100."""
    return account["nav"] * account["risk_pct_input"] / 100


# ── internals ──────────────────────────────────────────────────────────────────

def _find_config() -> Optional[str]:
    for p in _CONFIG_PATHS:
        if os.path.exists(p):
            return p
    return None


def _freshness(nav_updated_at: Optional[str]) -> tuple:
    if not nav_updated_at:
        return None, "unknown", "🟠 NAV ללא חותמת זמן"
    try:
        updated = datetime.fromisoformat(nav_updated_at)
        age_h   = (datetime.now() - updated).total_seconds() / 3600
        if age_h < _STALE_HOURS:
            return age_h, "fresh",    f"✅ NAV עדכני ({age_h:.1f}h)"
        elif age_h < _CRITICAL_HOURS:
            return age_h, "stale",    f"🟡 NAV ישן ({age_h:.0f}h)"
        else:
            return age_h, "critical", f"🔴 NAV קריטי ({age_h:.0f}h)"
    except Exception:
        return None, "unknown", "🟠 NAV — חותמת זמן לא תקינה"


def _fallback(reason: str) -> dict:
    return {
        "nav":             7500.0,
        "total_deposited": 7500.0,
        "risk_pct_input":  0.5,
        "nav_source":      "fallback",
        "nav_updated_at":  None,
        "age_hours":       None,
        "freshness":       "unknown",
        "freshness_label": f"🟠 Fallback NAV — {reason}",
        "is_stale":        True,
        "is_critical":     False,
        "ok":              False,
    }
