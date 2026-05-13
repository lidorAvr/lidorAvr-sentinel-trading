"""
Supabase data-access layer for Sentinel Trading.

All functions receive a Supabase client as first argument (dependency injection).
No module-level state, no Telegram dependencies — safe to import anywhere.
"""

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


def get_campaigns_pnl(sb):
    return sb.table("trades").select("campaign_id,pnl_usd,trade_date").execute().data or []


def update_trade(sb, trade_id, fields):
    sb.table("trades").update(fields).eq("trade_id", trade_id).execute()


def update_stop_for_campaign(sb, campaign_id, stop_price):
    sb.table("trades").update({"stop_loss": stop_price}).eq("campaign_id", campaign_id).eq("side", "BUY").execute()


def update_management_notes(sb, campaign_id, note):
    sb.table("trades").update({"management_notes": note}).eq("campaign_id", campaign_id).eq("side", "BUY").execute()


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
    """Return campaign_id of the most recent open BUY campaign for symbol, or None."""
    res = (
        sb.table("trades")
        .select("campaign_id")
        .eq("symbol", symbol)
        .eq("side", "BUY")
        .order("trade_date", desc=True)
        .limit(1)
        .execute()
    )
    data = res.data if res and res.data else []
    return data[0]["campaign_id"] if data else None


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
