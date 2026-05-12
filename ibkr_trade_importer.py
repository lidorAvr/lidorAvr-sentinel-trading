"""
IBKR XML → Supabase trade importer.

Parses <Trade> elements from a Flex Query XML and inserts trades that
don't yet exist in Supabase, identified by IBKR's `tradeID` (mapped to
the `trade_id` column).

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
            "quantity":   abs(qty_signed),
            "price":      price,
            "trade_date": trade_date,
            "pnl_usd":    pnl_usd,
        })
    return parsed


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

    try:
        existing_ids = repo.get_existing_trade_ids(sb)
    except Exception:
        existing_ids = set()

    new = [t for t in parsed if t["trade_id"] not in existing_ids]

    if new:
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
