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

F5 (Meeting 21/05/2026 Wave 2) — `locked_base_price` extension:
  The campaign's at-entry anchor is correct (`locked_entry_price` column,
  qty-weighted across ALL BUYs). But `original_campaign_risk` is computed
  from `base_price` (first-day weighted avg) × `base_qty` — and base_price
  is itself a sum over the same `price` column that drifted with the MRVL
  bug. Without a first-day-locked anchor, downstream R math still rides
  the drifted column.

  This module now exposes a SECOND anchor: `locked_base_price`, computed
  by the qty-weighted average of `locked_entry_price` across FIRST-DAY
  BUYs only (the same scope engine_core uses to compute `base_price`).
  It is None when partial-lock / missing-column / first-day-buys-empty.
  Consumers can adopt it for `original_campaign_risk` math to make R
  drift-resistant. Strictly additive — `base_price` itself is untouched
  (engine_core is byte-locked) and existing callers that don't read
  `locked_base_price` are byte-identical.
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


def compute_first_day_lock_anchor(campaign_buys: pd.DataFrame):
    """F5 (Meeting 21/05/2026 Wave 2) — qty-weighted at-entry locked anchor
    for the FIRST DAY of a campaign's BUYs only. This is the drift-resistant
    sibling of engine_core's per-campaign `base_price` (which is computed
    from the same first-day scope but on the unlocked `price` column).

    Returns None when:
      - The lock column is absent from the frame (LOCKED-April fixture path).
      - The frame is empty or has no first-day BUYs.
      - Any first-day BUY has a NULL/0/negative/non-numeric lock (partial-lock).
      - The trade_date column is missing (cannot identify first day).

    When non-None, the value is the float anchor a consumer should adopt
    INSTEAD of `base_price` for `original_campaign_risk` math. Today, with
    post-RISK-1c locked rows that haven't drifted yet, this equals
    `base_price` byte-identically; the drift-resistance benefit kicks in
    only when a future IBKR re-sync corrupts the `price` column.

    ``campaign_buys`` MUST be the BUY rows for ONE campaign (same shape
    engine_core's per-campaign group exposes — needs `trade_date`,
    `quantity`, and `locked_entry_price` columns).
    """
    if campaign_buys is None or len(campaign_buys) == 0:
        return None
    if LOCK_COLUMN not in campaign_buys.columns:
        return None
    if "trade_date" not in campaign_buys.columns:
        return None
    if "quantity" not in campaign_buys.columns:
        return None

    try:
        # Mirror engine_core.get_open_positions_campaign:536-539: first_date is
        # the MIN trade_date among BUYs, first_day_buys are all BUYs with that
        # exact date (an add-on on the same calendar day counts as first day).
        first_date = campaign_buys["trade_date"].min()
        first_day_buys = campaign_buys[campaign_buys["trade_date"] == first_date]
    except Exception:
        return None

    if len(first_day_buys) == 0:
        return None

    locks = first_day_buys[LOCK_COLUMN]
    if locks.isna().any():
        return None
    try:
        locks_f = locks.astype(float)
        qty = first_day_buys["quantity"].astype(float)
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
    """Return ``open_positions_df`` with two new columns:
       - ``locked_entry_price`` (campaign-level qty-weighted anchor across
         ALL BUYs; powers the /portfolio entry display + banner).
       - ``locked_base_price`` (F5 — first-day-only qty-weighted anchor;
         the drift-resistant sibling of ``base_price`` for downstream R
         math).

    For each campaign in ``open_positions_df`` (indexed by ``campaign_id``),
    fetches the matching BUY rows from ``raw_trades_df`` and computes both
    anchors via the pure helpers above. Strictly additive: the existing
    columns of ``open_positions_df`` are untouched (mirrors RISK-1d's
    defaulted-kwarg discipline — every existing consumer keeps working
    byte-identically when the new columns are None).

    Handles every honest-empty case without raising:
      - ``open_positions_df`` is None or empty ⇒ returned as-is (with the
        columns added if possible — keeps callers' downstream
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

    # Always ensure the columns exist in the output, even on empty input
    # — keeps the resolver-downstream contract consistent (resolver always
    # calls row.get('locked_entry_price') and tolerates None).
    if open_positions_df.empty:
        out = open_positions_df.copy()
        out[LOCK_COLUMN] = pd.Series(dtype="float64")
        out["locked_base_price"] = pd.Series(dtype="float64")
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
        out["locked_base_price"] = None
        return out

    # Index BUY rows by campaign_id once (avoid per-row groupby cost).
    try:
        buys_only = raw_trades_df[
            raw_trades_df["side"].astype(str).str.upper() == "BUY"]
    except Exception:
        out[LOCK_COLUMN] = None
        out["locked_base_price"] = None
        return out

    if buys_only.empty:
        out[LOCK_COLUMN] = None
        out["locked_base_price"] = None
        return out

    campaign_anchors: list = []
    base_anchors: list = []
    for cid in out["campaign_id"]:
        camp_buys = buys_only[buys_only["campaign_id"] == cid]
        campaign_anchors.append(compute_campaign_lock_anchor(camp_buys))
        base_anchors.append(compute_first_day_lock_anchor(camp_buys))
    # dtype=object preserves Python None across the column instead of letting
    # pandas coerce it to np.nan when mixed with float anchors. The resolver
    # downstream tolerates both (nan > 0 is False ⇒ unlocked branch), but the
    # explicit None keeps the row.get('locked_entry_price') is None semantic
    # honest and avoids surprise for any future caller that compares with `is None`.
    out[LOCK_COLUMN] = pd.Series(campaign_anchors, index=out.index, dtype=object)
    out["locked_base_price"] = pd.Series(base_anchors, index=out.index, dtype=object)
    return out
