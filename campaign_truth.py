import os
import json
import argparse
from pathlib import Path
from collections import defaultdict
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

def _f(v, default=0.0):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default

def _dt(v):
    x = _s(v)
    if not x:
        return None
    return x

def _date(v):
    x = _s(v)
    if not x:
        return None
    return x[:10]

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

def _audit(event_type, severity, message, payload=None, symbol=None, campaign_id=None, account_id=None):
    try:
        supabase.table("campaign_audit_events").insert({
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "symbol": symbol,
            "campaign_id": campaign_id,
            "account_id": account_id,
            "payload": payload or {},
        }).execute()
    except Exception as e:
        print(f"audit write skipped: {e}")

def _weighted_avg(items, price_key, qty_key):
    total_qty = 0.0
    total_val = 0.0
    for item in items:
        qty = abs(_f(item.get(qty_key), 0.0))
        price = _f(item.get(price_key), None)
        if price is None or qty <= 0:
            continue
        total_qty += qty
        total_val += qty * price
    if total_qty <= 0:
        return None
    return total_val / total_qty

def _min_dt(vals):
    clean = [v for v in vals if v]
    return min(clean) if clean else None

def _max_dt(vals):
    clean = [v for v in vals if v]
    return max(clean) if clean else None

def _campaign_setup_from_lots(lots):
    # Current trades table still carries setup_type; lots do not.
    # Campaign truth v1 keeps setup as Unknown; Sprint 6/Intake will improve this.
    return None

def _decision_source_from_lots(lots):
    tags = []
    for lot in lots:
        notes = _s(lot.get("notes")) or ""
        if "algo" in notes.lower():
            tags.append("algo")
    return "algo" if tags else "manual"

def _derive_campaign_status(has_open, total_closed, total_opened, is_runner):
    if has_open and total_closed > 0:
        return "runner" if is_runner else "partially_realized"
    if has_open:
        return "active_managed"
    if total_closed >= total_opened and total_opened > 0:
        return "closed_pending_review"
    return "detected"

def _derive_strategy_status(has_open, has_initial_stop, legacy_lots, missing_stop_lots, setup_type):
    if legacy_lots > 0:
        return "accounting_only"
    if has_open and not has_initial_stop:
        return "live_management_only"
    if missing_stop_lots > 0:
        return "accounting_only"
    if not setup_type:
        return "unclassified"
    return "strategy_verified"

def _derive_quality(strategy_status, missing_stop_lots, legacy_lots):
    if strategy_status == "strategy_verified":
        return "verified"
    if legacy_lots > 0:
        return "estimated"
    if missing_stop_lots > 0:
        return "estimated"
    if strategy_status in ["unclassified", "live_management_only"]:
        return "uncertain"
    return "uncertain"

def _eligibility_reason(strategy_status, missing_stop_lots, legacy_lots, setup_type):
    if strategy_status == "strategy_verified":
        return "Full lifecycle has required strategy fields."
    if legacy_lots > 0:
        return "Campaign has legacy carry-in lots; accounting only until manual backfill."
    if missing_stop_lots > 0:
        return f"{missing_stop_lots} lot(s) missing verified initial stop."
    if not setup_type:
        return "Setup is missing; excluded from setup-level strategy statistics."
    return "Insufficient data for verified strategy statistics."

def build_campaigns(dry_run=False):
    lots = _fetch_all("position_lots")
    closures = _fetch_all("lot_closures")
    executions = _fetch_all("executions")

    lots_by_campaign = defaultdict(list)
    closures_by_campaign = defaultdict(list)
    executions_by_campaign = defaultdict(list)

    for lot in lots:
        cid = _s(lot.get("campaign_id")) or f"UNCLASSIFIED_{lot.get('symbol')}"
        lots_by_campaign[cid].append(lot)

    for c in closures:
        cid = _s(c.get("campaign_id")) or f"UNCLASSIFIED_{c.get('symbol')}"
        closures_by_campaign[cid].append(c)

    for e in executions:
        cid = _s(e.get("campaign_id")) or f"UNCLASSIFIED_{e.get('symbol')}"
        executions_by_campaign[cid].append(e)

    all_campaign_ids = sorted(set(lots_by_campaign) | set(closures_by_campaign) | set(executions_by_campaign))
    rows = []

    for cid in all_campaign_ids:
        clots = lots_by_campaign.get(cid, [])
        cclosures = closures_by_campaign.get(cid, [])
        cexecs = executions_by_campaign.get(cid, [])

        symbol = None
        account_id = None
        for source in [clots, cclosures, cexecs]:
            for row in source:
                symbol = symbol or _s(row.get("symbol"))
                account_id = account_id or _s(row.get("account_id"))

        total_opened = sum(abs(_f(l.get("quantity_opened"), 0.0)) for l in clots)
        total_remaining = sum(abs(_f(l.get("quantity_remaining"), 0.0)) for l in clots)
        total_closed = sum(abs(_f(c.get("quantity_closed"), 0.0)) for c in cclosures)

        has_open = total_remaining > 0
        has_partial = total_closed > 0 and total_remaining > 0
        is_runner = has_partial and total_remaining > 0

        buy_execs = [e for e in cexecs if (_s(e.get("side")) or "").upper() == "BUY"]
        sell_execs = [e for e in cexecs if (_s(e.get("side")) or "").upper() == "SELL"]

        avg_entry = _weighted_avg(clots, "entry_price", "quantity_opened")
        avg_exit = _weighted_avg(cclosures, "close_price", "quantity_closed")

        setup_type = _campaign_setup_from_lots(clots)
        decision_source = _decision_source_from_lots(clots)

        verified_lots = len([l for l in clots if l.get("data_quality_status") == "verified"])
        estimated_lots = len([l for l in clots if l.get("data_quality_status") == "estimated"])
        legacy_lots = len([l for l in clots if l.get("lot_source") == "legacy_carry_in"])
        missing_stop_lots = len([l for l in clots if l.get("lot_source") == "execution" and not l.get("initial_stop")])

        has_initial_stop = missing_stop_lots == 0 and len(clots) > 0

        realized_pnl = sum(_f(c.get("fifo_pnl_realized_allocated"), 0.0) for c in cclosures)
        reported_pnl = sum(_f(e.get("fifo_pnl_realized"), 0.0) for e in sell_execs)

        commission_total = 0.0
        for e in cexecs:
            commission_total += _f(e.get("commission"), 0.0)

        opened_at = _min_dt([l.get("entry_time") for l in clots] + [e.get("execution_time") for e in buy_execs])
        closed_at = None if has_open else _max_dt([c.get("close_time") for c in cclosures] + [e.get("execution_time") for e in sell_execs])

        campaign_status = _derive_campaign_status(has_open, total_closed, total_opened, is_runner)
        strategy_status = _derive_strategy_status(has_open, has_initial_stop, legacy_lots, missing_stop_lots, setup_type)
        quality = _derive_quality(strategy_status, missing_stop_lots, legacy_lots)

        flags = []
        if missing_stop_lots > 0:
            flags.append("missing_initial_stop")
        if legacy_lots > 0:
            flags.append("legacy_lots")
        if not setup_type:
            flags.append("missing_setup")
        if abs((reported_pnl or 0.0) - (realized_pnl or 0.0)) > 0.01:
            flags.append("reported_vs_allocated_pnl_diff")

        row = {
            "campaign_id": cid,
            "account_id": account_id,
            "symbol": symbol,
            "setup_type": setup_type,
            "decision_source": decision_source,
            "campaign_status": campaign_status,
            "strategy_status": strategy_status,
            "data_quality_status": quality,
            "accounting_scope": "YTD",
            "strategy_scope": "YTD_VERIFIED_CAMPAIGNS_ONLY",
            "opened_at": opened_at,
            "opened_date": _date(opened_at),
            "closed_at": closed_at,
            "closed_date": _date(closed_at),
            "total_quantity_opened": total_opened,
            "total_quantity_closed": total_closed,
            "quantity_remaining": total_remaining,
            "avg_entry_price": avg_entry,
            "avg_exit_price": avg_exit,
            "buy_executions_count": len(buy_execs),
            "sell_executions_count": len(sell_execs),
            "lots_count": len(clots),
            "closures_count": len(cclosures),
            "realized_pnl_usd": realized_pnl,
            "reported_realized_pnl_usd": reported_pnl,
            "commission_total": commission_total,
            "has_initial_stop": has_initial_stop,
            "missing_stop_lots": missing_stop_lots,
            "verified_lots": verified_lots,
            "estimated_lots": estimated_lots,
            "legacy_lots": legacy_lots,
            "has_partial_realization": has_partial,
            "is_runner": is_runner,
            "has_open_position": has_open,
            "eligibility_reason": _eligibility_reason(strategy_status, missing_stop_lots, legacy_lots, setup_type),
            "audit_flags": flags,
            "calculation_version": "campaign_truth_v1",
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        rows.append(row)

    if dry_run:
        print("dry_run_campaigns=", len(rows))
        for row in rows[:10]:
            print(json.dumps({
                "campaign_id": row["campaign_id"],
                "symbol": row["symbol"],
                "status": row["campaign_status"],
                "strategy": row["strategy_status"],
                "quality": row["data_quality_status"],
                "opened": row["total_quantity_opened"],
                "closed": row["total_quantity_closed"],
                "remaining": row["quantity_remaining"],
                "pnl": row["realized_pnl_usd"],
                "flags": row["audit_flags"],
            }, ensure_ascii=False))
        return rows

    for i in range(0, len(rows), 100):
        supabase.table("campaigns").upsert(rows[i:i+100], on_conflict="campaign_id").execute()

    for row in rows:
        flags = row.get("audit_flags") or []
        if flags:
            _audit(
                "campaign_truth_flags",
                "warning" if row["data_quality_status"] != "broken" else "critical",
                "Campaign truth engine flagged data quality issues",
                {
                    "flags": flags,
                    "strategy_status": row["strategy_status"],
                    "data_quality_status": row["data_quality_status"],
                    "eligibility_reason": row["eligibility_reason"],
                },
                symbol=row["symbol"],
                campaign_id=row["campaign_id"],
                account_id=row["account_id"],
            )

    print("campaigns_upserted=", len(rows))
    return rows

def status():
    rows = _fetch_all("campaigns")
    print("campaigns=", len(rows))

    by_status = defaultdict(int)
    by_strategy = defaultdict(int)
    by_quality = defaultdict(int)

    for r in rows:
        by_status[r.get("campaign_status")] += 1
        by_strategy[r.get("strategy_status")] += 1
        by_quality[r.get("data_quality_status")] += 1

    print("by_campaign_status=")
    for k, v in sorted(by_status.items()):
        print(f"  {k}: {v}")

    print("by_strategy_status=")
    for k, v in sorted(by_strategy.items()):
        print(f"  {k}: {v}")

    print("by_data_quality=")
    for k, v in sorted(by_quality.items()):
        print(f"  {k}: {v}")

    open_rows = [r for r in rows if r.get("has_open_position")]
    print("open_campaigns=")
    for r in sorted(open_rows, key=lambda x: x.get("symbol") or ""):
        print(
            f"  {r.get('symbol')} | {r.get('campaign_id')} | "
            f"{r.get('campaign_status')} | remaining={r.get('quantity_remaining')} | "
            f"strategy={r.get('strategy_status')} | quality={r.get('data_quality_status')}"
        )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["dry-run", "build", "status"])
    args = parser.parse_args()

    if args.command == "dry-run":
        build_campaigns(dry_run=True)
    elif args.command == "build":
        build_campaigns(dry_run=False)
    elif args.command == "status":
        status()

if __name__ == "__main__":
    main()
