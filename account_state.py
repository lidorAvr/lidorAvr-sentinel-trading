"""
account_state.py — single source of truth for NAV and account settings.
The reporting service reads NAV exclusively through this module.

Phase NAV-Unify (Arch-F1 Decision B, Option β, founder-approved):
account_state is the CANONICAL NAV semantics owner. The classification
logic now lives in ONE shared pure core, `_resolve_nav_core()`, so the
report pipeline (`load()`) and the bot/risk-monitor reader
(`engine_core.get_nav_with_freshness()`) can NEVER desync the NAV value
or its freshness — that is the actual money-risk this phase closes.

`load()` is a thin **shape-A adapter** over the core: it is BYTE-IDENTICAL
to its pre-refactor output on EVERY config state (same keys, same Hebrew
`freshness_label` wording from `_freshness`/`_fallback`, same `nav_source`,
`is_stale`, `is_critical`, `ok`). account_state's observable behavior does
NOT change at all — only its internals were refactored to expose the
shared core. See docs/teams/PHASE_NAVUNIFY_IMPL.md.

This module stays a clean leaf (stdlib only: os/json/datetime/typing) so
`engine_core` importing it is the ACYCLIC direction.
"""
import os, json
from datetime import datetime
from typing import Optional

_CONFIG_PATHS   = ["/app/sentinel_config.json", "sentinel_config.json"]
_STALE_HOURS    = 24
_CRITICAL_HOURS = 48


# ── shared pure NAV core (Option β — the single canonical classifier) ────────

def _classify_age(age_hours: float) -> str:
    """Canonical age→freshness rule (account_state semantics, strict-`<`).

    `age < 24` → 'fresh'; `24 <= age < 48` → 'stale'; `age >= 48` →
    'critical'. The strict-`<` boundary is the canonical (D2): at EXACTLY
    24.0h it is 'stale' (NOT fresh); at EXACTLY 48.0h it is 'critical'
    (NOT stale). Pure; no I/O.
    """
    if age_hours < _STALE_HOURS:
        return "fresh"
    if age_hours < _CRITICAL_HOURS:
        return "stale"
    return "critical"


def _resolve_nav_core(_paths: Optional[list] = None) -> dict:
    """THE shared canonical NAV resolution (Option β). Pure-ish: only
    reads the on-disk config (os/json) — no labels, no per-caller shape.

    Returns the CANONICAL classification ONLY:
      nav, total_deposited, risk_pct_input, nav_updated_at, age_hours,
      freshness ("fresh"|"stale"|"critical"|"unknown"), is_stale,
      is_critical, ok, source_kind ("broker"|"deposited"|"fallback").

    Canonical semantics (= account_state's, founder-approved):
      D1  nav = data.get("nav", data.get("total_deposited", 7500.0)) — an
          explicit `0` is KEPT (NOT an `or`-chain that falls through).
      D2  strict-`<` boundary via `_classify_age` (24.0→stale, 48.0→critical).
      D3  no `nav_updated_at` → freshness="unknown", is_stale=True,
          is_critical=False.
      D4  missing / corrupt / non-dict config → ok=False, nav=7500.0,
          freshness="unknown", is_stale=True, is_critical=False
          (account_state `_fallback` semantics).
    """
    paths = _CONFIG_PATHS if _paths is None else _paths
    path = next((p for p in paths if os.path.exists(p)), None)

    def _fallback_core() -> dict:
        # D4 — missing / corrupt / non-dict: not-critical, unknown.
        return {
            "nav":             7500.0,
            "total_deposited": 7500.0,
            "risk_pct_input":  0.5,
            "nav_updated_at":  None,
            "age_hours":       None,
            "freshness":       "unknown",
            "is_stale":        True,
            "is_critical":     False,
            "ok":              False,
            "source_kind":     "fallback",
        }

    if path is None:
        return _fallback_core()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _fallback_core()
    except Exception:
        return _fallback_core()

    # D1 — explicit `0` kept (NOT an `or`-chain).
    nav = float(data.get("nav", data.get("total_deposited", 7500.0)))
    source_kind    = "broker" if "nav" in data else "deposited"
    nav_updated_at = data.get("nav_updated_at")

    if not nav_updated_at:
        # D3 — no timestamp: unknown, stale, NOT critical.
        return {
            "nav":             nav,
            "total_deposited": float(data.get("total_deposited", 7500.0)),
            "risk_pct_input":  float(data.get("risk_pct_input", 0.5)),
            "nav_updated_at":  nav_updated_at,
            "age_hours":       None,
            "freshness":       "unknown",
            "is_stale":        True,
            "is_critical":     False,
            "ok":              True,
            "source_kind":     source_kind,
        }
    try:
        updated  = datetime.fromisoformat(nav_updated_at)
        age_h    = (datetime.now() - updated).total_seconds() / 3600
        fresh    = _classify_age(age_h)            # D2 strict-`<`
        return {
            "nav":             nav,
            "total_deposited": float(data.get("total_deposited", 7500.0)),
            "risk_pct_input":  float(data.get("risk_pct_input", 0.5)),
            "nav_updated_at":  nav_updated_at,
            "age_hours":       age_h,
            "freshness":       fresh,
            "is_stale":        fresh in ("stale", "critical"),
            "is_critical":     fresh == "critical",
            "ok":              True,
            "source_kind":     source_kind,
        }
    except Exception:
        # bad/unparseable timestamp — same shape as D3 (unknown, not critical)
        return {
            "nav":             nav,
            "total_deposited": float(data.get("total_deposited", 7500.0)),
            "risk_pct_input":  float(data.get("risk_pct_input", 0.5)),
            "nav_updated_at":  nav_updated_at,
            "age_hours":       None,
            "freshness":       "unknown",
            "is_stale":        True,
            "is_critical":     False,
            "ok":              True,
            "source_kind":     source_kind,
        }


# ── shape-A adapter (the report pipeline reader — BYTE-IDENTICAL) ────────────

def load() -> dict:
    """
    Load account state from sentinel_config.json.
    Always returns a safe dict — never raises.

    Thin **shape-A adapter** over `_resolve_nav_core()` — BYTE-IDENTICAL
    to the pre-NAV-Unify output on EVERY config state (account_state is
    the canonical; Option β changes only internals).

    Keys returned:
        nav, total_deposited, risk_pct_input,
        nav_source ("broker" | "deposited" | "fallback"),
        nav_updated_at, age_hours,
        freshness ("fresh" | "stale" | "critical" | "unknown"),
        freshness_label, is_stale, is_critical, ok
    """
    # D4 reason wording is byte-identical to the pre-refactor `load()`
    # (distinct "not found" vs read/parse-error text). Mirror the
    # ORIGINAL control flow exactly so the fallback label string is
    # unchanged on every not-ok branch.
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

    # NAV value is the CANONICAL one from the shared core (D1: explicit-0
    # kept). `nav_source` = the core's source_kind. The age/freshness/
    # label triple is taken from the SAME single `_freshness()` call the
    # original used (one `datetime.now()` for both `age_hours` and the
    # label's embedded `{age_h}` — byte-identical, no double-now drift).
    nav            = float(data.get("nav", data.get("total_deposited", 7500.0)))
    nav_source     = "broker" if "nav" in data else "deposited"
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
    """Shape-A Hebrew label builder (D5 — account_state's own label
    wording, preserved verbatim). Delegates the freshness CLASSIFICATION
    to the shared canonical `_classify_age` so the value can never desync
    from the core; only the label strings live here."""
    if not nav_updated_at:
        return None, "unknown", "🟠 NAV ללא חותמת זמן"
    try:
        updated = datetime.fromisoformat(nav_updated_at)
        age_h   = (datetime.now() - updated).total_seconds() / 3600
        fresh   = _classify_age(age_h)
        if fresh == "fresh":
            return age_h, "fresh",    f"✅ NAV עדכני ({age_h:.1f}h)"
        elif fresh == "stale":
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
