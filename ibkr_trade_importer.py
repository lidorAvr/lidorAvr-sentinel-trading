"""
IBKR XML → Supabase trade importer.

Parses <Trade> elements from a Flex Query XML and inserts trades that
don't yet exist in Supabase, identified by IBKR's `tradeID` (mapped to
the `trade_id` column).

Key conventions (must match engine_core.get_open_positions_campaign):
- `quantity` is signed: BUY positive, SELL negative. The engine sums
  trades within a campaign and treats `net_qty <= 0` as a closed campaign.
- `campaign_id` is `{SYMBOL}_{tradeID of first BUY}` (matches the
  production format observed in Supabase). Add-on BUYs join the
  currently-open campaign for the symbol; the next BUY after a campaign
  closes (net=0) starts a new campaign.

Pure functions — no Telegram, no logging side-effects. Caller is
responsible for sending notifications about the result.
"""
import xml.etree.ElementTree as ET
import supabase_repository as repo


def parse_trades_from_xml(xml_text: str) -> list:
    """Parse <Trade> elements from an IBKR Flex Query XML string.

    Returns a list of dicts matching the Supabase `trades` schema:
        trade_id, symbol, side, quantity, price, trade_date, pnl_usd

    Fields not present in the XML (setup_type, quality, score, stop_loss,
    initial_stop, image_url, management_notes, campaign_id) are left
    unset so the backlog journal can prompt the user to fill them.

    Malformed XML returns []. Individual trades that fail field parsing
    are silently skipped — never raised — so a single bad row doesn't
    abort the whole import.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    parsed = []
    for trade in root.findall(".//Trade"):
        trade_id = (trade.get("tradeID") or "").strip()
        if not trade_id:
            continue

        side = (trade.get("buySell") or "").upper().strip()
        if side not in ("BUY", "SELL"):
            continue

        symbol = (trade.get("symbol") or "").strip()
        if not symbol:
            continue

        try:
            qty_signed = float(trade.get("quantity") or 0)
            price = float(trade.get("tradePrice") or 0)
        except (ValueError, TypeError):
            continue
        if qty_signed == 0 or price <= 0:
            continue
        # Force sign convention to match the rest of the system:
        # BUY positive, SELL negative — independent of what the XML says.
        qty = abs(qty_signed)
        signed_qty = qty if side == "BUY" else -qty

        date_raw = (trade.get("tradeDate") or "").strip()
        if len(date_raw) != 8 or not date_raw.isdigit():
            continue
        trade_date = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"

        try:
            pnl_usd = float(trade.get("fifoPnlRealized") or 0)
        except (ValueError, TypeError):
            pnl_usd = 0.0

        parsed.append({
            "trade_id":   trade_id,
            "symbol":     symbol,
            "side":       side,
            "quantity":   signed_qty,
            "price":      price,
            "trade_date": trade_date,
            "pnl_usd":    pnl_usd,
        })
    return parsed


def _assign_campaign_ids(new_trades: list, existing_trades: list) -> None:
    """Mutate `new_trades` in-place, setting `campaign_id` on each item.

    Algorithm:
    - From existing trades, compute net signed quantity per campaign_id
      and which symbols currently have an open campaign.
    - Walk new trades in chronological order. For each:
        * If symbol has an open campaign → join it (add-on / SELL).
        * Else if BUY → start a new campaign: `{SYMBOL}_{tradeID}`.
        * Else (SELL with no open campaign) → orphan, leave NULL.
      Update running net qty after assignment; close the campaign when
      net returns to zero so a subsequent BUY can start a fresh one.
    """
    campaign_state = {}  # cid -> {"symbol": str, "net_qty": float}
    for t in existing_trades:
        cid = t.get("campaign_id")
        if not cid:
            continue
        try:
            qty = float(t.get("quantity") or 0)
        except (ValueError, TypeError):
            qty = 0
        if cid not in campaign_state:
            campaign_state[cid] = {"symbol": t.get("symbol"), "net_qty": 0}
        campaign_state[cid]["net_qty"] += qty

    open_cid_by_sym = {
        info["symbol"]: cid
        for cid, info in campaign_state.items()
        if info["net_qty"] > 0.001 and info["symbol"]
    }

    # Process chronologically so add-ons line up correctly
    new_trades.sort(key=lambda t: (t["trade_date"], t["trade_id"]))

    for t in new_trades:
        sym = t["symbol"]
        qty = t["quantity"]  # already signed

        if sym in open_cid_by_sym:
            t["campaign_id"] = open_cid_by_sym[sym]
        elif qty > 0:                              # BUY, no open campaign
            new_cid = f"{sym}_{t['trade_id']}"
            t["campaign_id"] = new_cid
            open_cid_by_sym[sym] = new_cid
            campaign_state[new_cid] = {"symbol": sym, "net_qty": 0}
        else:                                       # SELL with no open campaign
            t["campaign_id"] = None
            continue

        cid = t["campaign_id"]
        campaign_state[cid]["net_qty"] += qty
        if campaign_state[cid]["net_qty"] <= 0.001:
            open_cid_by_sym.pop(sym, None)


def import_new_trades(sb, xml_text: str) -> dict:
    """Parse trades from XML, insert ones not yet present in Supabase.

    Returns:
        {
            "new_count":    int,     # how many newly inserted
            "new_trades":   list,    # the inserted dicts
            "total_in_xml": int,     # how many parsed from XML total
            "ok":           bool,    # False if XML couldn't be parsed
        }
    """
    parsed = parse_trades_from_xml(xml_text)
    if not parsed:
        return {"new_count": 0, "new_trades": [], "total_in_xml": 0, "ok": False}

    # Fetch *all* existing trades (not just IDs) so we can compute open
    # campaigns and assign campaign_id to new rows.
    try:
        existing = repo.get_all_trades(sb)
    except Exception:
        existing = []

    existing_ids = {str(t.get("trade_id")) for t in existing if t.get("trade_id") is not None}
    new = [t for t in parsed if t["trade_id"] not in existing_ids]

    if new:
        _assign_campaign_ids(new, existing)
        try:
            repo.insert_trades(sb, new)
        except Exception:
            # Partial-failure handling kept simple: report the attempt;
            # caller should still notify user so the issue is visible.
            return {"new_count": 0, "new_trades": new, "total_in_xml": len(parsed), "ok": False}

    return {
        "new_count":    len(new),
        "new_trades":   new,
        "total_in_xml": len(parsed),
        "ok":           True,
    }
