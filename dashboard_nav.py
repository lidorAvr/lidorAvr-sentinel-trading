"""dashboard_nav.py — Sprint-27 W1 (Mark P1-1 + Data D-F1).

Pure, import-light presentation helper for the dashboard sidebar NAV box.

Root closed here: the dashboard sidebar rendered `🏦 Live IBKR NAV` in a
GREEN success box UNCONDITIONALLY — even when the NAV was the stale /
no-timestamp / silent $7,500 fallback (`dashboard.load_settings` had its own
bare `except`). That is the exact "fallback-as-truth" class CLAUDE.md /
AGENTS #1 forbids and Sprint-25 B1 (`report_renderer._nav_disclosure_lines`)
closed for Telegram but was never applied to the dashboard surface.

This helper mirrors the B1 GATE *exactly* and reuses the already-honest
`account_state.load()` fields verbatim (`nav`, `nav_source`, `freshness`,
`is_stale`, `ok`, `freshness_label`) — invents NO field, performs ZERO
R/NAV/Expectancy/sizing math (presentation-only, additive). It deliberately
imports NOTHING (stdlib-free, no streamlit/engine) so it is unit-testable in
isolation, like B1's helper inside `report_renderer`.

Decision (== B1): broker+fresh ⇒ the BYTE-IDENTICAL pre-W1 green
"🏦 Live IBKR NAV: **$X**" success string; ANY non-broker-fresh state
(deposited / fallback / stale / critical / unknown / `ok=False`) ⇒ a clear
NON-green disclosure that reuses the verbatim `freshness_label` + the source.
"""
from typing import Tuple


def nav_sidebar_render(acc) -> Tuple[str, str]:
    """Decide how the sidebar NAV line is rendered from the canonical
    `account_state.load()` dict.

    Returns ``(kind, text)``:
      * ``("success", "🏦 Live IBKR NAV: **$X**")`` — ONLY on the broker+fresh
        happy path; the text is BYTE-IDENTICAL to the pre-W1 green box so the
        normal screen is unchanged (Mark-gate: broker+fresh byte-identical).
      * ``("warning", "<freshness_label> … מקור NAV: …")`` — any
        non-broker-fresh state: a clear NON-green disclosure reusing the
        already-honest `freshness_label` verbatim + the NAV source, so a
        fallback/stale figure is never presented as exact live truth.

    GATE (identical to `report_renderer._nav_disclosure_lines`, accuracy >
    confidence): broker+fresh iff ``nav_source == "broker"`` AND
    ``freshness == "fresh"`` AND NOT ``is_stale`` AND ``ok``. Anything else
    (incl. a non-dict / empty arg) ⇒ the honest non-green box.
    """
    a = acc if isinstance(acc, dict) else {}
    nav         = float(a.get("nav", a.get("total_deposited", 7500.0)))
    nav_source  = str(a.get("nav_source", "") or "")
    freshness   = str(a.get("freshness", "") or "")
    is_stale    = bool(a.get("is_stale", False))
    ok          = bool(a.get("ok", True))
    broker_fresh = (
        nav_source == "broker" and freshness == "fresh"
        and not is_stale and ok
    )
    if broker_fresh:
        # BYTE-IDENTICAL to the pre-W1 sidebar success box.
        return ("success", f"🏦 Live IBKR NAV: **${nav:,.2f}**")
    label = (str(a.get("freshness_label", "") or "").strip()
             or "NAV מקור/עדכניות לא ודאיים")
    return (
        "warning",
        f"🏦 NAV: **${nav:,.2f}** — לא Live\n\n"
        f"{label}\n\n"
        f"מקור NAV: `{nav_source or '—'}` · "
        f"ערך מוערך/לא-עדכני — לא נתון מדויק.",
    )
