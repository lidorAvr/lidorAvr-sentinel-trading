"""
RISK-1c.1 — campaign-level at-entry locked-price anchor enrichment.

This module exists because engine_core.py is byte-locked
(test_sprint25_byte_lock_redteam + 7 sibling guards) — the `locked_entry_price`
column added by RISK-1a migration 006 + populated by RISK-1b/RISK-1c was
silently stripped by engine_core.get_open_positions_campaign's per-campaign
output dict, so the downstream display surfaces (telegram_portfolio,
dashboard) never saw a populated lock anchor even AFTER the founder ran
RISK-1c and locked every BUY row at the Supabase layer. That left the
"⚠️ לא-נעול" banner permanently on for every position. Bug confirmed in
prod 21/05/2026 ~01:40 (MRVL showing the banner despite a clean RISK-1c
run).

Constraint: engine_core.py cannot be modified (byte-lock). The fix is an
enrichment layer that the 2 display surfaces call AFTER
get_open_positions_campaign, BEFORE converting the open-positions
DataFrame to per-row dicts that feed the resolver.

Pure / read-only: no Supabase, no engine_core, no telebot. Operates on
already-fetched DataFrames; safe to import from any layer (tests too).

Semantics (matches docs/DATA_CONTRACTS.md:70-78 RISK-1d contract):
  - A campaign is "lock-eligible" iff EVERY BUY row in the campaign has a
    non-NULL locked_entry_price. Partial-lock (any BUY NULL-locked) is
    treated as not-locked so the banner stays on — honest disclosure,
    never a silent substitution (AGENTS.md #1).
  - When lock-eligible, the campaign's `locked_entry_price` is the
    qty-weighted average of locked_entry_prices across all BUYs in the
    campaign, using the SAME weighting `avg_price` uses. For any campaign
    where `price` has not drifted from its captured lock (post-RISK-1c
    steady state — set_locked_entry copies `price` AT lock-time), this
    weighted average equals `avg_price` byte-identically; the displayed
    entry number does not move, only the banner clears. When IBKR later
    drifts `price` (the MRVL $87→$170 regression), the lock anchor stays
    put and the resolver returns the true at-entry value.
  - When the column does not exist in the input frame (LOCKED-April
    fixture path), every campaign gets None ⇒ April byte-identical.
"""
from __future__ import annotations

import pandas as pd

LOCK_COLUMN = "locked_entry_price"


def compute_campaign_lock_anchor(campaign_buys: pd.DataFrame):
    """Pure function: return the qty-weighted at-entry locked anchor for
    one campaign's BUY rows, or None when partial-lock / missing-column /
    empty-input / zero-qty.

    ``campaign_buys`` MUST be the BUY rows for ONE campaign (same shape the
    engine_core.split_side_first() / per-campaign group exposes). The caller
    is responsible for filtering to BUY rows + grouping by campaign_id.

    Never raises. Non-numeric / NaN values in the lock column collapse to
    "partial-lock" ⇒ None (no silent coercion).
    """
    if campaign_buys is None or len(campaign_buys) == 0:
        return None
    if LOCK_COLUMN not in campaign_buys.columns:
        return None
    locks = campaign_buys[LOCK_COLUMN]
    # All-BUYs-locked guard. .notna() catches NaN; we additionally require
    # every value to be > 0 (matches set_locked_entry's positive-only contract
    # in supabase_repository) to defend against rogue 0/negative locks.
    if locks.isna().any():
        return None
    try:
        locks_f = locks.astype(float)
        qty = campaign_buys["quantity"].astype(float)
    except (TypeError, ValueError):
        return None
    if (locks_f <= 0).any():
        return None
    total_qty = float(qty.sum())
    if total_qty <= 0:
        return None
    return float((locks_f * qty).sum() / total_qty)


def attach_lock_anchors(open_positions_df: pd.DataFrame,
                        raw_trades_df: pd.DataFrame) -> pd.DataFrame:
    """Return ``open_positions_df`` with a new ``locked_entry_price`` column.

    For each campaign in ``open_positions_df`` (indexed by ``campaign_id``),
    fetches the matching BUY rows from ``raw_trades_df`` and computes the
    weighted lock anchor via ``compute_campaign_lock_anchor``.

    Strictly additive: the existing columns of ``open_positions_df`` are
    untouched (mirrors RISK-1d's defaulted-kwarg discipline — every existing
    consumer keeps working byte-identically when the new column is None).

    Handles every honest-empty case without raising:
      - ``open_positions_df`` is None or empty ⇒ returned as-is (with the
        column added if possible — keeps callers' downstream
        ``.to_dict('records')`` shape stable when the frame is later
        non-empty).
      - ``raw_trades_df`` is None / empty / missing the campaign_id /
        side / locked_entry_price columns ⇒ every row gets None.
      - A campaign in ``open_positions_df`` has no matching BUY rows in
        ``raw_trades_df`` (caller-side data race) ⇒ that row gets None.
    """
    if open_positions_df is None:
        return open_positions_df
    if not isinstance(open_positions_df, pd.DataFrame):
        return open_positions_df

    # Always ensure the column exists in the output, even on empty input
    # — keeps the resolver-downstream contract consistent (resolver always
    # calls row.get('locked_entry_price') and tolerates None).
    if open_positions_df.empty:
        out = open_positions_df.copy()
        out[LOCK_COLUMN] = pd.Series(dtype="float64")
        return out

    out = open_positions_df.copy()

    # Honest-empty path: if raw frame can't supply lock data, fill None
    # for every campaign (the resolver will banner-flag, which is correct).
    if (raw_trades_df is None
            or not isinstance(raw_trades_df, pd.DataFrame)
            or raw_trades_df.empty
            or "campaign_id" not in raw_trades_df.columns
            or "side" not in raw_trades_df.columns):
        out[LOCK_COLUMN] = None
        return out

    # Index BUY rows by campaign_id once (avoid per-row groupby cost).
    try:
        buys_only = raw_trades_df[
            raw_trades_df["side"].astype(str).str.upper() == "BUY"]
    except Exception:
        out[LOCK_COLUMN] = None
        return out

    if buys_only.empty:
        out[LOCK_COLUMN] = None
        return out

    anchors: list = []
    for cid in out["campaign_id"]:
        camp_buys = buys_only[buys_only["campaign_id"] == cid]
        anchors.append(compute_campaign_lock_anchor(camp_buys))
    # dtype=object preserves Python None across the column instead of letting
    # pandas coerce it to np.nan when mixed with float anchors. The resolver
    # downstream tolerates both (nan > 0 is False ⇒ unlocked branch), but the
    # explicit None keeps the row.get('locked_entry_price') is None semantic
    # honest and avoids surprise for any future caller that compares with `is None`.
    out[LOCK_COLUMN] = pd.Series(anchors, index=out.index, dtype=object)
    return out
