"""Phase REPORT-2 — pure, deterministic, read-only position units-lifecycle
helper + the SINGLE source-of-truth Hebrew formatter (anti-drift; Phase
ALGO-2A §5 doctrine).

Authoritative spec: ``docs/teams/PHASE_REPORT2_SCOPE.md`` (governs).

WHAT THIS IS
------------
The Telegram position card and the dashboard position table show only the
current net ``quantity`` ("כמות: 1.0"). The founder cannot tell whether a
position is FULL or whether a partial profit was already realized. This
module re-derives, **read-only from the raw trade rows the report builders
already hold**, the per-campaign units lifecycle:

  * ``original``  = Σ|quantity| over BUY rows  (= the engine's own
                    ``_c2_buys_qty``)
  * ``realized``  = Σ|quantity| over SELL rows (= the engine's own
                    ``_c2_sells_qty``)
  * ``remaining`` = original − realized        (= the engine's ``net_qty``
                    = the ``quantity`` already on every open record)
  * ``realized_pct`` = realized / original × 100  (only when original > 0)

It NEVER changes any campaign P&L / R / NAV / exposure / aggregation math —
it is a read-only re-projection of the SAME legs the byte-locked engine
already splits in ``engine_core.split_side_first`` /
``get_open_positions_campaign``. The derivation MIRRORS that doctrine
exactly: ``str(side).upper().strip()`` ∈ {BUY, SELL}; ``quantity`` treated
as a magnitude (``abs``); the same exact-``trade_id`` dedup guard
(``drop_duplicates(subset=["trade_id"], keep="first")`` when a ``trade_id``
column/key is present — DATA_CONTRACTS F4) so the derived ``net`` is
byte-identical to the engine's ``net_qty``/``quantity``.

HONEST EMPTY (INVIOLABLE — AGENTS.md #1; absence ≠ data)
--------------------------------------------------------
When the legs are missing or ambiguous the lifecycle is rendered as ``—``
with the explicit Hebrew marker ``לא ניתן לאמת`` — **NEVER a fabricated
number, NEVER a silent zero**. Every empty path sets ``ok=False`` and a
machine ``reason``. The card's existing ``quantity``/``כמות``/``Qty``
number is **never** replaced — the lifecycle is a strictly ADDITIVE line.

PURITY
------
Zero import of ``engine_core``/``analytics_engine``/``period_data_probe``/
``risk_monitor``/Supabase/network. Pure, deterministic, idempotent, no
state, no write, never raises (boundary-input discipline; any
missing/empty/ambiguous input ⇒ honest empty, never zero-as-truth). The
caller (each surface) detects nothing — it passes the raw rows + the
engine's authoritative ``engine_net_qty`` in; this module decides.
"""
from typing import Any

# RTL mark — byte-identical to bot_core.RTL / telegram_formatters.RTL
# ("‏"). Inlined (not imported) to keep this module a pure leaf with
# zero engine/telegram/Supabase import (SCOPE §2). A test pins equality.
RTL = "‏"

# The single honest-empty marker (Hebrew). Rendered whenever the legs are
# missing or ambiguous — never a number, never a silent zero.
UNVERIFIABLE_HE = "לא ניתן לאמת"

# The engine's own net-reconciliation tolerance (engine_core.py:531
# `if net_qty <= 0.001`). Inlined as a literal constant (no engine import);
# a test pins it == 0.001 so it can never silently drift from the engine.
RECON_TOL = 0.001

__all__ = [
    "RTL",
    "UNVERIFIABLE_HE",
    "RECON_TOL",
    "compute_units_lifecycle",
    "format_units_lifecycle",
]


def _to_float(v: Any) -> float:
    """Best-effort float coercion; never raises. Non-numeric / None ⇒ 0.0
    (mirrors the engine's `pd.to_numeric(..., errors="coerce").fillna(0)`
    discipline at engine_core.py:522, applied row-wise here)."""
    try:
        if v is None:
            return 0.0
        f = float(v)
        # NaN / inf are not trustworthy magnitudes → treat as 0.0 (the
        # engine's coerce+fillna(0) collapses NaN the same way).
        if f != f or f in (float("inf"), float("-inf")):
            return 0.0
        return f
    except (TypeError, ValueError):
        return 0.0


def _empty(reason: str) -> dict:
    """An honest-empty lifecycle result — `ok=False`, no numbers asserted.
    The formatter renders this as `—` + `לא ניתן לאמת` (never zero)."""
    return {
        "original": None,
        "remaining": None,
        "realized": None,
        "realized_pct": None,
        "ok": False,
        "reason": reason,
    }


def compute_units_lifecycle(campaign_rows, *, engine_net_qty) -> dict:
    """Re-derive the units lifecycle for ONE campaign, read-only, never raises.

    ``campaign_rows`` — an iterable of per-campaign raw trade-leg mappings
    (each a dict / Mapping with at least ``side`` and ``quantity``; an
    optional ``trade_id``). This is exactly the SAME set of legs the engine
    splits in ``split_side_first``; the caller slices it read-only from the
    raw ``df`` it already holds (no new data source, no Supabase, no
    network).

    ``engine_net_qty`` (keyword-only) — the engine's OWN authoritative
    ``quantity``/``net_qty`` for this position record
    (``engine_core.py:560``). Used solely for the §3 reconciliation gate:
    if the re-derived ``net`` does not match it within ``RECON_TOL`` the
    WHOLE line is honest-empty (a leg-split we cannot trust is never
    guessed).

    Returns a structured dict
    ``{original, remaining, realized, realized_pct, ok, reason}``. On every
    honest-empty path ``ok=False`` and a machine ``reason``; numbers are
    ``None`` (never a fabricated 0). Idempotent, deterministic, pure.
    """
    # ── No-campaign gate (§3.4): absent / empty rows ⇒ honest empty. ──────
    if campaign_rows is None:
        return _empty("no_rows")
    try:
        rows = list(campaign_rows)
    except TypeError:
        return _empty("no_rows")
    if len(rows) == 0:
        return _empty("no_rows")

    # ── Exact-trade_id dedup guard (DATA_CONTRACTS F4 — mirror
    # engine_core.py:528). Guarded on the column/key's PRESENCE: only when
    # EVERY row carries a non-empty trade_id do we dedup keep="first"
    # (absent ⇒ no-op, byte-identical with no duplicates — provable
    # identity on an all-unique key). A re-exported/double-synced SELL is
    # not counted twice, exactly as the engine does it. ─────────────────
    def _row_get(r, key):
        try:
            return r.get(key)
        except AttributeError:
            return None

    has_trade_id = len(rows) > 0 and all(
        _row_get(r, "trade_id") not in (None, "") for r in rows
    )
    if has_trade_id:
        seen = set()
        deduped = []
        for r in rows:
            tid = _row_get(r, "trade_id")
            if tid in seen:
                continue
            seen.add(tid)
            deduped.append(r)
        rows = deduped

    # ── Side split — EXACTLY engine_core.split_side_first doctrine:
    # str(side).upper().strip() ∈ {BUY, SELL}; quantity as a magnitude
    # (abs). Rows whose side is neither BUY nor SELL are ignored (the
    # engine's eq("BUY")/eq("SELL")) masks do the same). ─────────────────
    buys_qty = 0.0
    sells_qty = 0.0
    for r in rows:
        side = str(_row_get(r, "side")).upper().strip()
        qty = abs(_to_float(_row_get(r, "quantity")))
        if side == "BUY":
            buys_qty += qty
        elif side == "SELL":
            sells_qty += qty

    # ── Base gate (§3.2): cannot establish an original base ⇒ honest
    # empty (NOT zero, NOT a guess). ─────────────────────────────────────
    if buys_qty <= 0:
        return _empty("buys_qty_le_0")

    # ── Sign gate (§3.3): Σ|SELL| > Σ|BUY| is an over-export artifact —
    # we cannot trust the split ⇒ honest empty. ─────────────────────────
    if sells_qty > buys_qty:
        return _empty("sells_gt_buys")

    net = buys_qty - sells_qty

    # ── Reconciliation gate (§3.1 — the strongest honesty gate): the
    # re-derived net MUST equal the engine's own quantity for this record
    # within the SAME 0.001 tolerance the engine uses (engine_core.py:531).
    # A mismatch means the leg split is not trustworthy ⇒ the WHOLE line is
    # honest-empty; we never render a partial / guessed lifecycle. ───────
    eng_net = _to_float(engine_net_qty)
    if abs(net - eng_net) > RECON_TOL:
        return _empty("net_recon_mismatch")

    realized_pct = (sells_qty / buys_qty) * 100.0  # buys_qty > 0 here

    return {
        "original": buys_qty,
        "remaining": net,
        "realized": sells_qty,
        "realized_pct": realized_pct,
        "ok": True,
        "reason": "ok",
    }


def _fmt_qty(v: float) -> str:
    """Render a units magnitude compactly: integral values without a
    trailing `.0` (e.g. `15`), fractional values at up to 4 dp trimmed
    (e.g. `1.5`, `0.3333`). Deterministic, locale-free."""
    if v == int(v):
        return str(int(v))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def format_units_lifecycle(lc: dict) -> str:
    """THE single-source-of-truth display text — the ONE Hebrew lifecycle
    line BOTH surfaces emit, byte-identical for identical input (anti-drift,
    SCOPE §5 / Phase ALGO-2A §5).

    Honest empty (``ok`` falsy / missing) ⇒ the ``—`` + ``לא ניתן לאמת``
    line (NEVER a fabricated number, NEVER a silent zero). Valid ⇒ the
    original / remaining / realized + realized-% line. Additive only — it
    returns a NEW line; it never re-formats / reorders / recomputes any
    existing card number or string. Never raises (any malformed input ⇒ the
    honest-empty line).
    """
    try:
        ok = bool(lc.get("ok")) if isinstance(lc, dict) else False
    except Exception:
        ok = False

    if not ok:
        # Honest empty — units unknown / unverifiable. The existing
        # quantity/כמות/Qty number on the card is untouched; this is the
        # additive line only, and it asserts nothing.
        return f"{RTL}מחזור יחידות: — ({UNVERIFIABLE_HE})"

    original = lc.get("original")
    remaining = lc.get("remaining")
    realized = lc.get("realized")
    realized_pct = lc.get("realized_pct")

    # Defensive: a malformed "ok" dict with missing numbers ⇒ honest empty
    # (never assert a number we do not have).
    if original is None or remaining is None or realized is None \
            or realized_pct is None:
        return f"{RTL}מחזור יחידות: — ({UNVERIFIABLE_HE})"

    return (
        f"{RTL}מחזור יחידות: מקורי {_fmt_qty(original)} · "
        f"נותרו {_fmt_qty(remaining)} · "
        f"מומשו {_fmt_qty(realized)} ({realized_pct:.0f}%)"
    )
