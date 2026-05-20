"""
Supabase data-access layer for Sentinel Trading.

All functions receive a Supabase client as first argument (dependency injection).
No module-level state, no Telegram dependencies — safe to import anywhere.
"""
from collections import defaultdict

import audit_logger

_INCOMPLETE_TRADES_QUERY = (
    "setup_type.is.null,"
    "quality.is.null,"
    "and(side.eq.BUY,initial_stop.is.null),"
    "and(side.eq.BUY,initial_stop.eq.0),"
    "and(side.eq.SELL,score.is.null),"
    "and(side.eq.SELL,image_url.is.null),"
    "and(side.eq.SELL,management_notes.is.null)"
)


def get_all_trades(sb):
    return sb.table("trades").select("*").execute().data or []


def get_trades_by_symbol(sb, symbol):
    return sb.table("trades").select("*").eq("symbol", symbol).execute().data or []


def get_incomplete_trades(sb, limit=100):
    return (
        sb.table("trades")
        .select("*")
        .or_(_INCOMPLETE_TRADES_QUERY)
        .order("trade_date", desc=False)
        .order("trade_id", desc=False)
        .limit(limit)
        .execute()
        .data or []
    )


def get_earlier_buys_for_campaign(sb, campaign_id, before_date):
    return (
        sb.table("trades")
        .select("*")
        .eq("campaign_id", campaign_id)
        .eq("side", "BUY")
        .lt("trade_date", before_date)
        .execute()
        .data or []
    )


def get_old_trades(sb, before_date):
    return sb.table("trades").select("*").lt("trade_date", before_date).execute().data or []


def get_trades_since(sb, since_date):
    """READ-ONLY: every trade row on/after `since_date` (ISO 'YYYY-MM-DD'),
    oldest-first. Phase ALGO-2 T-C2 — backs the SEPARATE longer-rolling
    stat-base read for the risk-raise/Heat base (it does NOT touch the
    DEC-20260516-020 `_fetch_trades_df` report fetch / report period). Pure
    SELECT — no insert/update/delete, no Supabase mutation. Mirrors the
    report fetch's column contract (`select("*")`, `gte('trade_date', …)`,
    `.order('trade_date')`) so `compute_closed_campaigns` consumes it
    unchanged."""
    return (
        sb.table("trades")
        .select("*")
        .gte("trade_date", since_date)
        .order("trade_date", desc=False)
        .execute()
        .data or []
    )


def get_campaigns_pnl(sb):
    return sb.table("trades").select("campaign_id,pnl_usd,trade_date").execute().data or []


def update_trade(sb, trade_id, fields):
    sb.table("trades").update(fields).eq("trade_id", trade_id).execute()


def update_stop_for_campaign(sb, campaign_id, stop_price):
    sb.table("trades").update({"stop_loss": stop_price}).eq("campaign_id", campaign_id).eq("side", "BUY").execute()


def get_management_notes(sb, campaign_id: str) -> str:
    """Read the current management_notes blob for a campaign.

    Returns empty string when the campaign exists but has no notes yet,
    or when no row matches. Caller can rely on str return type.
    """
    res = (
        sb.table("trades")
        .select("management_notes")
        .eq("campaign_id", campaign_id)
        .eq("side", "BUY")
        .order("trade_date", desc=False)  # earliest BUY = the canonical row
        .limit(1)
        .execute()
    )
    data = res.data if res and res.data else []
    if not data:
        return ""
    return data[0].get("management_notes") or ""


def update_management_notes(sb, campaign_id, note):
    """Append a timestamped note to the campaign's management history.

    Sprint 8 #8 (Compliance): switched from REPLACE to APPEND. Without this,
    every Add-On confirmation overwrote the prior note — so a regulator
    asking "when was the last addon?" got only the most recent answer.
    History is now preserved in the column directly, in addition to the
    audit_log row that audit_logger writes (defense in depth: even if
    migration 002 hasn't been applied and audit_log is unreachable, the
    notes column itself preserves the trail).

    Each entry is prefixed with a timestamp `[YYYY-MM-DD HH:MM]` for
    grep-ability and human readability when displayed in Telegram.
    """
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entry = f"[{ts}] {note}"

    previous = get_management_notes(sb, campaign_id)
    full_notes = f"{previous}\n{new_entry}" if previous else new_entry

    sb.table("trades").update({"management_notes": full_notes}).eq("campaign_id", campaign_id).eq("side", "BUY").execute()
    # Audit: addon confirmations and stop adjustments flow through here.
    # log_action is fail-open — never raises, prints to stderr on failure.
    audit_logger.log_action(
        sb, audit_logger.ACTION_ADDON_CONFIRM,
        before={"previous_notes_chars": len(previous)},
        after={"campaign_id": campaign_id, "appended": new_entry},
    )


def get_latest_buy_trade_id(sb, symbol: str, campaign_id: str) -> str | None:
    """Return trade_id of the most recent BUY entry for this campaign (for addon marking)."""
    res = (
        sb.table("trades")
        .select("trade_id")
        .eq("campaign_id", campaign_id)
        .eq("side", "BUY")
        .order("trade_date", desc=True)
        .limit(1)
        .execute()
    )
    data = res.data if res and res.data else []
    return data[0]["trade_id"] if data else None


def update_addon_record(sb, trade_id: str, base_campaign_lot_id: str, addon_sequence: int) -> None:
    """Mark a trade as an add-on and link it to the base campaign lot.
    Requires migration 001_addon_phase2.sql to be applied first."""
    sb.table("trades").update({
        "is_addon": True,
        "base_campaign_lot_id": base_campaign_lot_id,
        "addon_sequence": addon_sequence,
    }).eq("trade_id", trade_id).execute()


def get_open_campaign_for_symbol(sb, symbol: str) -> str | None:
    """Return campaign_id of the most recent OPEN campaign for symbol, or None.

    A campaign is "open" when its net quantity (signed sum of all BUY/SELL rows)
    is strictly positive. Closed campaigns (net qty ≤ 0) are excluded so that
    add-on flows never bind to a campaign that was already fully sold.

    Per Supabase schema: BUY rows store positive quantity, SELL rows store
    negative quantity (matches adaptive_risk_engine.compute_closed_campaigns
    grouping logic).
    """
    rows = (
        sb.table("trades")
        .select("campaign_id, quantity, trade_date")
        .eq("symbol", symbol)
        .execute()
        .data or []
    )
    if not rows:
        return None

    net_qty: dict = defaultdict(float)
    latest_date: dict = {}
    for r in rows:
        cid = r.get("campaign_id")
        if not cid:
            continue
        net_qty[cid] += float(r.get("quantity") or 0)
        d = r.get("trade_date") or ""
        if d > latest_date.get(cid, ""):
            latest_date[cid] = d

    open_cids = [cid for cid, q in net_qty.items() if q > 0]
    if not open_cids:
        return None

    open_cids.sort(key=lambda c: latest_date.get(c, ""), reverse=True)
    return open_cids[0]


def get_existing_trade_ids(sb) -> set:
    """Return the set of trade_id values already in Supabase (as strings)."""
    rows = sb.table("trades").select("trade_id").execute().data or []
    return {str(r.get("trade_id")) for r in rows if r.get("trade_id") is not None}


def insert_trades(sb, trades: list) -> int:
    """Bulk-insert trade dicts into Supabase. Returns number of rows inserted.
    Caller is responsible for deduplication."""
    if not trades:
        return 0
    res = sb.table("trades").insert(trades).execute()
    data = res.data if hasattr(res, "data") else None
    return len(data) if data else 0


# ── RISK-1a — at-entry locked-immutable entry-price helpers ───────────────────
# Backed by migration 006_add_locked_entry_to_trades.sql. Reads/writes the 4
# lock columns: locked_entry_price, locked_entry_at, lock_source, lock_method.
# When locked_entry_price is NULL the trade is "not yet locked" — callers must
# treat that as the legitimate sentinel (banner-flagged in the formatter; the
# legacy `price` column still drives the historical April / mode='historical'
# path unchanged).

def get_locked_entry(sb, trade_id: str) -> dict | None:
    """Return the 4 lock columns for a single trade, or None when missing.

    Shape on success:
        {"locked_entry_price": float|None,
         "locked_entry_at":    str|None,   # ISO timestamp from Supabase
         "lock_source":        str|None,
         "lock_method":        str|None}

    Returns None when the trade_id has no row at all. A row that exists but
    has locked_entry_price IS NULL returns the dict with None values — the
    caller distinguishes "row missing" from "row not yet locked".
    """
    res = (
        sb.table("trades")
        .select("locked_entry_price, locked_entry_at, lock_source, lock_method")
        .eq("trade_id", trade_id)
        .limit(1)
        .execute()
    )
    data = res.data if res and res.data else []
    if not data:
        return None
    row = data[0]
    return {
        "locked_entry_price": row.get("locked_entry_price"),
        "locked_entry_at":    row.get("locked_entry_at"),
        "lock_source":        row.get("lock_source"),
        "lock_method":        row.get("lock_method"),
    }


def set_locked_entry(sb, trade_id: str, *, price: float,
                     source: str, method: str) -> None:
    """Write the locked-entry record for a trade. All 4 lock columns are set
    atomically in a single UPDATE; locked_entry_at is stamped server-acceptable
    ISO-UTC at the moment of this call (NOT row-insert time — we want the
    lock-time, which is when the wizard / backfill / admin-correction ran).

    `source` must be one of: 'broker_avg_fill', 'reuters_open',
    'declared_by_user', 'unknown'. `method` must be one of: 'wizard',
    'backfill', 'admin_correction'. Application-layer validation only — the
    SQL has no CHECK constraint (Phase A keeps DDL flexible).

    No-op on the `audit_log` row here — the call sites (RISK-1b wizard, RISK-1c
    backfill, RISK-1d /at_entry_correct) log their own action-specific audit
    rows via audit_logger.log_action with richer before/after context than
    this helper has access to.
    """
    from datetime import datetime, timezone
    locked_at_iso = datetime.now(timezone.utc).isoformat()
    sb.table("trades").update({
        "locked_entry_price": price,
        "locked_entry_at":    locked_at_iso,
        "lock_source":        source,
        "lock_method":        method,
    }).eq("trade_id", trade_id).execute()


def lock_entry_from_trade_price(sb, trade_id: str, *,
                                 chat_id: int | None = None,
                                 method: str = "wizard") -> bool:
    """RISK-1b/1c — at-entry-price lock helper. Idempotent + fail-soft.

    Reads the trade's existing `price` field (the IBKR-Flex-imported broker
    fill stored by ibkr_sync_runner.py) and writes it to `locked_entry_price`
    with lock_source='broker_avg_fill'. `method` records WHO triggered the
    lock:
      - 'wizard'   (default — RISK-1b forward-capture from the
                    journal-completion wizard at telegram_bot.py:752+).
      - 'backfill' (RISK-1c admin-triggered retroactive batch — see
                    risk1c_backfill.run_backfill).
      - 'admin_correction' (RISK-1d future /at_entry override).
    Caller chooses; the helper's behaviour is byte-identical across methods,
    only the lock_method column + the audit row metadata change. Audit-logs
    the outcome.

    Returns True if a new lock was written, False otherwise (already locked,
    no row, missing/anomalous price). Never raises — the wizard call site
    must never block on a lock failure.

    Idempotent: if `locked_entry_price` is already non-NULL, the helper
    no-ops and returns False (no second audit row). Safe to call from
    multiple wizard steps OR re-runs of the RISK-1c batch; only the FIRST
    call to reach a row locks it.

    Fail-soft skip cases (each writes one ACTION_AT_ENTRY_SKIP audit row
    with the reason in metadata; the trade row stays NULL-locked, which the
    RISK-1d formatter banner-flags downstream):
      - trade_id has no matching row in `trades` (caller bug — but we don't
        raise; the wizard's other update_trade calls would also no-op)
      - `price` is None / 0 / negative / non-numeric (broker-data anomaly)

    Success case writes one ACTION_AT_ENTRY_LOCK audit row with the locked
    price + the legacy `price` value + the lock_method in metadata
    (defense-in-depth: even if the column-write itself silently fails, the
    audit row preserves the intent).
    """
    try:
        res = (
            sb.table("trades")
            .select("price, locked_entry_price, symbol")
            .eq("trade_id", trade_id)
            .limit(1)
            .execute()
        )
        rows = res.data if res and res.data else []
        if not rows:
            audit_logger.log_action(
                sb, audit_logger.ACTION_AT_ENTRY_SKIP,
                chat_id=chat_id,
                metadata={"trade_id": trade_id, "reason": "no_trade_row"},
            )
            return False
        row = rows[0]
        if row.get("locked_entry_price") is not None:
            return False
        price = row.get("price")
        try:
            price_f = float(price) if price is not None else None
        except (TypeError, ValueError):
            price_f = None
        if price_f is None or price_f <= 0:
            audit_logger.log_action(
                sb, audit_logger.ACTION_AT_ENTRY_SKIP,
                chat_id=chat_id,
                metadata={
                    "trade_id": trade_id,
                    "symbol":   row.get("symbol"),
                    "reason":   "missing_or_anomalous_price",
                    "raw_price": price,
                },
            )
            return False
        set_locked_entry(
            sb, trade_id,
            price=price_f, source="broker_avg_fill", method=method,
        )
        audit_logger.log_action(
            sb, audit_logger.ACTION_AT_ENTRY_LOCK,
            chat_id=chat_id,
            before={"locked_entry_price": None},
            after={
                "trade_id":           trade_id,
                "symbol":             row.get("symbol"),
                "locked_entry_price": price_f,
                "lock_source":        "broker_avg_fill",
                "lock_method":        method,
                "broker_price_copied_from": price,
            },
        )
        return True
    except Exception as e:
        try:
            audit_logger.log_action(
                sb, audit_logger.ACTION_AT_ENTRY_SKIP,
                chat_id=chat_id,
                metadata={
                    "trade_id": trade_id,
                    "reason":   "exception",
                    "error":    f"{type(e).__name__}: {str(e)[:120]}",
                },
            )
        except Exception:
            pass
        return False


def get_trades_missing_lock(sb, *, symbol: str | None = None) -> list:
    """Return BUY trades that have no locked_entry_price yet.

    Filters in Python (not in SQL): fetches all BUY rows for the optional
    `symbol` (or every BUY row when symbol is None), then keeps the rows with
    locked_entry_price IS NULL. Chosen over a `.is_('locked_entry_price',
    'null')` filter because that supabase-py syntax is not used elsewhere in
    this codebase, and prod scale (<500 BUY rows total) makes the in-Python
    filter free. RISK-1c may add a partial SQL index if backfill batches grow.

    Used by:
      - RISK-1c admin backfill (operator-driven; lists every row still needing
        a lock so the founder can confirm coverage).
      - RISK-1d formatter banner ("X positions not yet locked — use /at_entry
        to add").
    """
    q = sb.table("trades").select("*").eq("side", "BUY")
    if symbol is not None:
        q = q.eq("symbol", symbol)
    rows = q.execute().data or []
    return [r for r in rows if r.get("locked_entry_price") is None]
