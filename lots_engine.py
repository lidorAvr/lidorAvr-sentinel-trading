import os
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent

if load_dotenv:
    load_dotenv(BASE_DIR / ".env")
    load_dotenv("/app/.env")

def _env(*names):
    for name in names:
        val = os.getenv(name)
        if val:
            return val
    return None

SUPABASE_URL = _env("SUPABASE_URL")
SUPABASE_KEY = _env("SUPABASE_SERVICE_KEY", "SUPABASE_KEY", "SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("Missing SUPABASE_URL / SUPABASE_KEY in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def _s(v):
    if v is None:
        return None
    x = str(v).strip()
    return x if x else None

def _f(v, default=None):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default

def _date(v):
    x = _s(v)
    if not x:
        return None
    try:
        return x[:10]
    except Exception:
        return None

def _raw(row):
    rp = row.get("raw_payload")
    if isinstance(rp, dict):
        return rp
    try:
        return json.loads(rp or "{}")
    except Exception:
        return {}

def _fetch_all(table, select="*"):
    rows = []
    start = 0
    page = 1000
    while True:
        res = supabase.table(table).select(select).range(start, start + page - 1).execute()
        chunk = res.data or []
        rows.extend(chunk)
        if len(chunk) < page:
            break
        start += page
    return rows

def _audit(event_type, severity, message, payload=None, symbol=None, campaign_id=None, execution_key=None, account_id=None):
    try:
        supabase.table("campaign_audit_events").insert({
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "symbol": symbol,
            "campaign_id": campaign_id,
            "execution_key": execution_key,
            "account_id": account_id,
            "payload": payload or {},
        }).execute()
    except Exception as e:
        print(f"audit write skipped: {e}")

def _initial_stop_from_execution(exe):
    raw = _raw(exe)
    for key in ["initial_stop", "stop_loss"]:
        val = _f(raw.get(key))
        if val is not None and val > 0:
            return val
    return None

def _risk_for_lot(qty, entry_price, stop, commission):
    if qty is None or entry_price is None or stop is None:
        return None
    if stop >= entry_price:
        return None
    risk = abs(qty) * (entry_price - stop)
    if commission:
        risk += abs(commission)
    return risk

def _sort_key(exe):
    return (
        exe.get("execution_time") or "",
        exe.get("trade_date") or "",
        exe.get("source_trade_id") or "",
        exe.get("execution_key") or "",
    )

def _clear_generated_tables():
    try:
        supabase.table("lot_closures").delete().neq("closure_key", "__never__").execute()
    except Exception as e:
        print("lot_closures clear skipped:", e)

    try:
        supabase.table("position_lots").delete().neq("lot_key", "__never__").execute()
    except Exception as e:
        print("position_lots clear skipped:", e)

def _insert_batches(table, rows, batch_size=100):
    for i in range(0, len(rows), batch_size):
        supabase.table(table).insert(rows[i:i+batch_size]).execute()

def build_lots(dry_run=False):
    executions = _fetch_all("executions")
    executions.sort(key=_sort_key)

    open_lots = {}
    lots = []
    closures = []
    legacy_count = 0
    missing_stop_count = 0
    unmatched_sell_count = 0

    lot_seq = 0
    legacy_seq = 0

    for exe in executions:
        side = (_s(exe.get("side")) or "").upper()
        symbol = _s(exe.get("symbol"))
        account_id = _s(exe.get("account_id"))
        campaign_id = _s(exe.get("campaign_id")) or f"UNCLASSIFIED_{symbol}"
        execution_key = _s(exe.get("execution_key"))
        qty_signed = _f(exe.get("quantity"), 0.0)
        qty = abs(qty_signed or 0.0)
        price = _f(exe.get("price"))
        commission = _f(exe.get("commission"), 0.0) or 0.0
        exec_time = exe.get("execution_time")
        trade_date = exe.get("trade_date")
        fifo_pnl = _f(exe.get("fifo_pnl_realized"), 0.0) or 0.0

        if not symbol or side not in ["BUY", "SELL"] or qty <= 0:
            continue

        group_key = (account_id, symbol, campaign_id)

        if side == "BUY":
            lot_seq += 1
            initial_stop = _initial_stop_from_execution(exe)
            risk_usd = _risk_for_lot(qty, price, initial_stop, commission)
            quality = "verified" if initial_stop is not None else "estimated"
            eligibility = "strategy_candidate" if initial_stop is not None else "live_management_only"

            if initial_stop is None:
                missing_stop_count += 1
                _audit(
                    "lot_missing_initial_stop",
                    "warning",
                    "BUY execution opened a lot without a verified initial stop",
                    {"execution_key": execution_key, "quantity": qty, "price": price},
                    symbol=symbol,
                    campaign_id=campaign_id,
                    execution_key=execution_key,
                    account_id=account_id,
                )

            lot_key = f"lot:{execution_key}"
            lot = {
                "lot_key": lot_key,
                "account_id": account_id,
                "symbol": symbol,
                "campaign_id": campaign_id,
                "position_side": "long",
                "lot_source": "execution",
                "entry_execution_id": exe.get("execution_id"),
                "entry_execution_key": execution_key,
                "entry_time": exec_time,
                "entry_date": _date(trade_date),
                "entry_price": price,
                "quantity_opened": qty,
                "quantity_remaining": qty,
                "allocated_commission": commission,
                "initial_stop": initial_stop,
                "risk_usd_at_lot_open": risk_usd,
                "status": "open",
                "strategy_eligibility": eligibility,
                "data_quality_status": quality,
                "notes": None,
            }

            lots.append(lot)
            open_lots.setdefault(group_key, []).append(lot)
            continue

        if side == "SELL":
            remaining_to_close = qty
            sell_qty = qty
            close_commission_remaining = commission
            pnl_remaining = fifo_pnl

            queue = open_lots.setdefault(group_key, [])

            if not queue:
                legacy_seq += 1
                legacy_count += 1
                unmatched_sell_count += 1

                legacy_lot_key = f"legacy_carry_in:{account_id}:{symbol}:{campaign_id}:{execution_key}"
                legacy_lot = {
                    "lot_key": legacy_lot_key,
                    "account_id": account_id,
                    "symbol": symbol,
                    "campaign_id": campaign_id,
                    "position_side": "long",
                    "lot_source": "legacy_carry_in",
                    "entry_execution_id": None,
                    "entry_execution_key": None,
                    "entry_time": None,
                    "entry_date": None,
                    "entry_price": None,
                    "quantity_opened": qty,
                    "quantity_remaining": 0,
                    "allocated_commission": None,
                    "initial_stop": None,
                    "risk_usd_at_lot_open": None,
                    "status": "closed",
                    "strategy_eligibility": "accounting_only",
                    "data_quality_status": "estimated",
                    "notes": "Synthetic carry-in lot created because a SELL appeared without an opening BUY inside current data scope.",
                }

                lots.append(legacy_lot)
                queue.append(legacy_lot)

                _audit(
                    "legacy_carry_in_lot_created",
                    "warning",
                    "SELL execution had no matching open lot in current data scope; synthetic accounting-only lot created",
                    {"execution_key": execution_key, "quantity": qty, "price": price},
                    symbol=symbol,
                    campaign_id=campaign_id,
                    execution_key=execution_key,
                    account_id=account_id,
                )

            while remaining_to_close > 0 and queue:
                lot = queue[0]
                available = _f(lot.get("quantity_remaining"), 0.0) or 0.0

                if available <= 0:
                    queue.pop(0)
                    continue

                close_qty = min(available, remaining_to_close)
                ratio = close_qty / sell_qty if sell_qty else 0
                allocated_close_comm = close_commission_remaining * ratio if close_commission_remaining is not None else None
                allocated_pnl = pnl_remaining * ratio if pnl_remaining is not None else None

                closure_key = f"closure:{lot['lot_key']}:{execution_key}:{close_qty}"

                closures.append({
                    "closure_key": closure_key,
                    "lot_key": lot["lot_key"],
                    "close_execution_id": exe.get("execution_id"),
                    "close_execution_key": execution_key,
                    "account_id": account_id,
                    "symbol": symbol,
                    "campaign_id": campaign_id,
                    "close_time": exec_time,
                    "close_date": _date(trade_date),
                    "quantity_closed": close_qty,
                    "entry_price": lot.get("entry_price"),
                    "close_price": price,
                    "allocated_entry_commission": lot.get("allocated_commission"),
                    "allocated_close_commission": allocated_close_comm,
                    "fifo_pnl_realized_allocated": allocated_pnl,
                    "closure_source": "fifo" if lot.get("lot_source") != "legacy_carry_in" else "legacy_carry_in",
                    "data_quality_status": "verified" if lot.get("lot_source") != "legacy_carry_in" else "estimated",
                })

                lot["quantity_remaining"] = round(available - close_qty, 10)
                remaining_to_close = round(remaining_to_close - close_qty, 10)

                if lot["quantity_remaining"] <= 0:
                    lot["quantity_remaining"] = 0
                    lot["status"] = "closed"
                    if queue:
                        queue.pop(0)
                else:
                    lot["status"] = "open"

            if remaining_to_close > 0:
                _audit(
                    "sell_quantity_exceeds_open_lots",
                    "critical",
                    "SELL quantity exceeded available open lots even after legacy handling",
                    {"execution_key": execution_key, "remaining_to_close": remaining_to_close, "quantity": qty},
                    symbol=symbol,
                    campaign_id=campaign_id,
                    execution_key=execution_key,
                    account_id=account_id,
                )

    for lot in lots:
        if (lot.get("quantity_remaining") or 0) <= 0:
            lot["status"] = "closed"
        elif lot.get("quantity_remaining") < lot.get("quantity_opened"):
            lot["status"] = "partial"
        else:
            lot["status"] = "open"

    if dry_run:
        print("dry_run_lots=", len(lots))
        print("dry_run_closures=", len(closures))
        print("legacy_carry_in_lots=", legacy_count)
        print("missing_stop_lots=", missing_stop_count)
        print("unmatched_sell_count=", unmatched_sell_count)
        for lot in lots[:5]:
            print(json.dumps({
                "lot_key": lot["lot_key"],
                "symbol": lot["symbol"],
                "campaign_id": lot["campaign_id"],
                "source": lot["lot_source"],
                "opened": lot["quantity_opened"],
                "remaining": lot["quantity_remaining"],
                "status": lot["status"],
                "quality": lot["data_quality_status"],
            }, ensure_ascii=False))
        return

    _clear_generated_tables()
    _insert_batches("position_lots", lots)
    _insert_batches("lot_closures", closures)

    print("lots_inserted=", len(lots))
    print("closures_inserted=", len(closures))
    print("legacy_carry_in_lots=", legacy_count)
    print("missing_stop_lots=", missing_stop_count)
    print("unmatched_sell_count=", unmatched_sell_count)

def status():
    lots = _fetch_all("position_lots")
    closures = _fetch_all("lot_closures")

    open_lots = [l for l in lots if l.get("status") in ["open", "partial"]]
    legacy = [l for l in lots if l.get("lot_source") == "legacy_carry_in"]
    missing_stop = [l for l in lots if l.get("lot_source") == "execution" and not l.get("initial_stop")]

    print("position_lots=", len(lots))
    print("lot_closures=", len(closures))
    print("open_or_partial_lots=", len(open_lots))
    print("legacy_carry_in_lots=", len(legacy))
    print("missing_stop_execution_lots=", len(missing_stop))

    by_symbol = {}
    for l in open_lots:
        sym = l.get("symbol")
        by_symbol.setdefault(sym, 0.0)
        by_symbol[sym] += _f(l.get("quantity_remaining"), 0.0) or 0.0

    print("open_quantity_by_symbol=")
    for sym, qty in sorted(by_symbol.items()):
        print(f"  {sym}: {qty}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["dry-run", "build", "status"])
    args = parser.parse_args()

    if args.command == "dry-run":
        build_lots(dry_run=True)
    elif args.command == "build":
        build_lots(dry_run=False)
    elif args.command == "status":
        status()

if __name__ == "__main__":
    main()
