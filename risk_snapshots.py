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
    return x[:10]

def _today():
    return datetime.now(timezone.utc).date().isoformat()

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

def _fetch_optional(table):
    try:
        return _fetch_all(table)
    except Exception as e:
        print(f"optional table skipped: {table}: {e}")
        return []

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

def _sort_time(row):
    return (
        _s(row.get("execution_time"))
        or _s(row.get("snapshot_at"))
        or _s(row.get("date"))
        or _s(row.get("created_at"))
        or ""
    )

def _latest_by_campaign_or_symbol(rows):
    out = {}
    sorted_rows = sorted(rows, key=_sort_time)
    for row in sorted_rows:
        cid = _s(row.get("campaign_id"))
        sym = _s(row.get("symbol"))
        if cid:
            out[("campaign", cid)] = row
        if sym:
            out[("symbol", sym)] = row
    return out

def _target_risk_from_executions(executions):
    buys = [e for e in executions if (_s(e.get("side")) or "").upper() == "BUY"]
    for e in sorted(buys, key=_sort_time):
        raw = _raw(e)
        for key in ["target_risk_usd", "planned_risk_usd", "risk_usd"]:
            val = _f(raw.get(key))
            if val is not None and val > 0:
                return val, f"execution.raw_payload.{key}"

    for e in sorted(executions, key=_sort_time):
        raw = _raw(e)
        for key in ["target_risk_usd", "planned_risk_usd", "risk_usd"]:
            val = _f(raw.get(key))
            if val is not None and val > 0:
                return val, f"execution.raw_payload.{key}"

    return None, None

def _actual_initial_risk_from_lots(lots):
    vals = []
    missing = 0
    for lot in lots:
        val = _f(lot.get("risk_usd_at_lot_open"))
        if val is not None and val > 0:
            vals.append(val)
        else:
            missing += 1

    if not vals:
        return None, "missing"
    return sum(vals), "position_lots.risk_usd_at_lot_open"

def _peak_campaign_risk(lots, closures):
    lot_by_key = {_s(l.get("lot_key")): l for l in lots}
    events = []

    for lot in lots:
        risk = _f(lot.get("risk_usd_at_lot_open"))
        if risk is None:
            continue
        events.append((_s(lot.get("entry_time")) or "", risk))

    for cl in closures:
        lot = lot_by_key.get(_s(cl.get("lot_key")))
        if not lot:
            continue

        lot_risk = _f(lot.get("risk_usd_at_lot_open"))
        opened = _f(lot.get("quantity_opened"), 0)
        closed = _f(cl.get("quantity_closed"), 0)

        if lot_risk is None or opened <= 0 or closed <= 0:
            continue

        released = lot_risk * (closed / opened)
        events.append((_s(cl.get("close_time")) or "", -released))

    running = 0.0
    peak = 0.0

    for _, delta in sorted(events, key=lambda x: x[0]):
        running += delta
        if running > peak:
            peak = running

    return peak if peak > 0 else None

def _open_weighted_avg_entry(open_lots):
    qty_total = 0.0
    value_total = 0.0
    for lot in open_lots:
        qty = _f(lot.get("quantity_remaining"), 0) or 0
        price = _f(lot.get("entry_price"))
        if qty > 0 and price is not None:
            qty_total += qty
            value_total += qty * price
    if qty_total <= 0:
        return None
    return value_total / qty_total

def _latest_current_stop(campaign, lots, executions, latest_snapshot):
    if latest_snapshot:
        for key in ["current_stop", "suggested_stop", "stop_loss", "initial_stop"]:
            val = _f(latest_snapshot.get(key))
            if val is not None and val > 0:
                return val, f"position_snapshots.{key}"

    for e in sorted(executions, key=_sort_time, reverse=True):
        raw = _raw(e)
        for key in ["current_stop", "stop_loss", "initial_stop"]:
            val = _f(raw.get(key))
            if val is not None and val > 0:
                return val, f"execution.raw_payload.{key}"

    open_lots = [l for l in lots if (_f(l.get("quantity_remaining"), 0) or 0) > 0]
    stops = [_f(l.get("initial_stop")) for l in open_lots if _f(l.get("initial_stop")) is not None]
    stops = [s for s in stops if s and s > 0]
    if stops:
        return max(stops), "position_lots.initial_stop"

    return None, None

def _latest_current_price(campaign, latest_snapshot):
    if latest_snapshot:
        for key in ["current_price", "price", "last_price"]:
            val = _f(latest_snapshot.get(key))
            if val is not None and val > 0:
                return val, f"position_snapshots.{key}"

    return None, None

def _quality_and_flags(campaign, target_risk, actual_risk, peak_risk, current_price, current_stop, qty_remaining, missing_stop_lots):
    flags = []

    if target_risk is None:
        flags.append("missing_target_risk_usd")

    if actual_risk is None:
        flags.append("missing_actual_initial_risk_usd")

    if peak_risk is None:
        flags.append("missing_peak_campaign_risk_usd")

    if missing_stop_lots > 0:
        flags.append("missing_initial_stop_lots")

    if qty_remaining and qty_remaining > 0:
        if current_price is None:
            flags.append("missing_current_price")
        if current_stop is None:
            flags.append("missing_current_stop")

    if actual_risk is not None and actual_risk > 0 and missing_stop_lots == 0:
        if target_risk is not None and target_risk > 0:
            quality = "verified"
        else:
            quality = "estimated"
    elif actual_risk is not None and actual_risk > 0:
        quality = "estimated"
    else:
        quality = "uncertain"

    return quality, flags

def build_snapshots(dry_run=False):
    campaigns = _fetch_all("campaigns")
    lots = _fetch_all("position_lots")
    closures = _fetch_all("lot_closures")
    executions = _fetch_all("executions")
    position_snapshots = _fetch_optional("position_snapshots")

    lots_by_campaign = defaultdict(list)
    closures_by_campaign = defaultdict(list)
    executions_by_campaign = defaultdict(list)

    for lot in lots:
        lots_by_campaign[_s(lot.get("campaign_id"))].append(lot)

    for cl in closures:
        closures_by_campaign[_s(cl.get("campaign_id"))].append(cl)

    for e in executions:
        executions_by_campaign[_s(e.get("campaign_id"))].append(e)

    latest_map = _latest_by_campaign_or_symbol(position_snapshots)

    rows = []
    today = _today()
    now = datetime.now(timezone.utc).isoformat()

    for c in campaigns:
        cid = _s(c.get("campaign_id"))
        symbol = _s(c.get("symbol"))
        account_id = _s(c.get("account_id"))

        clots = lots_by_campaign.get(cid, [])
        cclosures = closures_by_campaign.get(cid, [])
        cexecs = executions_by_campaign.get(cid, [])

        open_lots = [l for l in clots if (_f(l.get("quantity_remaining"), 0) or 0) > 0]
        qty_remaining = sum(_f(l.get("quantity_remaining"), 0) or 0 for l in open_lots)

        avg_entry = _f(c.get("avg_entry_price"))
        if qty_remaining > 0:
            avg_entry = _open_weighted_avg_entry(open_lots) or avg_entry

        realized_pnl = _f(c.get("realized_pnl_usd"), 0) or 0

        target_risk, target_source = _target_risk_from_executions(cexecs)
        actual_risk, actual_source = _actual_initial_risk_from_lots(clots)
        peak_risk = _peak_campaign_risk(clots, cclosures)

        latest_snapshot = latest_map.get(("campaign", cid)) or latest_map.get(("symbol", symbol))
        current_price, price_source = _latest_current_price(c, latest_snapshot)
        current_stop, stop_source = _latest_current_stop(c, clots, cexecs, latest_snapshot)

        open_pnl = None
        current_risk_to_stop = None
        giveback_to_stop = None
        locked_profit = None

        if qty_remaining > 0 and avg_entry is not None and current_price is not None:
            open_pnl = (current_price - avg_entry) * qty_remaining

        if qty_remaining > 0 and avg_entry is not None and current_stop is not None:
            current_risk_to_stop = max((avg_entry - current_stop) * qty_remaining, 0)
            locked_profit = max((current_stop - avg_entry) * qty_remaining, 0)

        if qty_remaining > 0 and avg_entry is not None and current_price is not None and current_stop is not None:
            open_profit = max((current_price - avg_entry) * qty_remaining, 0)
            locked_profit = max((current_stop - avg_entry) * qty_remaining, 0)
            giveback_to_stop = max(open_profit - locked_profit, 0)

        total_live_pnl = realized_pnl + (open_pnl or 0)

        closed_target_r = realized_pnl / target_risk if target_risk and target_risk > 0 else None
        closed_actual_r = realized_pnl / actual_risk if actual_risk and actual_risk > 0 else None
        open_target_r = open_pnl / target_risk if open_pnl is not None and target_risk and target_risk > 0 else None
        open_actual_r = open_pnl / actual_risk if open_pnl is not None and actual_risk and actual_risk > 0 else None

        missing_stop_lots = int(_f(c.get("missing_stop_lots"), 0) or 0)
        quality, flags = _quality_and_flags(
            c, target_risk, actual_risk, peak_risk, current_price, current_stop, qty_remaining, missing_stop_lots
        )

        row = {
            "risk_snapshot_key": f"{cid}:{today}",
            "campaign_id": cid,
            "account_id": account_id,
            "symbol": symbol,
            "snapshot_date": today,
            "snapshot_at": now,
            "target_risk_usd": target_risk,
            "actual_initial_risk_usd": actual_risk,
            "peak_campaign_risk_usd": peak_risk,
            "current_risk_to_stop_usd": current_risk_to_stop,
            "giveback_to_stop_usd": giveback_to_stop,
            "locked_profit_usd": locked_profit,
            "closed_target_r": closed_target_r,
            "closed_actual_r": closed_actual_r,
            "open_target_r": open_target_r,
            "open_actual_r": open_actual_r,
            "avg_entry_price": avg_entry,
            "current_price": current_price,
            "current_stop": current_stop,
            "quantity_remaining": qty_remaining,
            "realized_pnl_usd": realized_pnl,
            "open_pnl_usd": open_pnl,
            "total_live_pnl_usd": total_live_pnl,
            "target_risk_source": target_source,
            "actual_risk_source": actual_source,
            "live_price_source": price_source,
            "current_stop_source": stop_source,
            "data_quality_status": quality,
            "risk_flags": flags,
            "calculation_version": "risk_snapshots_v1",
            "updated_at": now,
        }

        rows.append(row)

    if dry_run:
        print("dry_run_risk_snapshots=", len(rows))
        for row in rows[:12]:
            print(json.dumps({
                "campaign_id": row["campaign_id"],
                "symbol": row["symbol"],
                "target": row["target_risk_usd"],
                "actual": row["actual_initial_risk_usd"],
                "peak": row["peak_campaign_risk_usd"],
                "closed_target_r": row["closed_target_r"],
                "closed_actual_r": row["closed_actual_r"],
                "quality": row["data_quality_status"],
                "flags": row["risk_flags"],
            }, ensure_ascii=False))
        return rows

    for i in range(0, len(rows), 100):
        supabase.table("campaign_risk_snapshots").upsert(rows[i:i+100], on_conflict="risk_snapshot_key").execute()

    for row in rows:
        payload = {
            "target_risk_usd": row["target_risk_usd"],
            "actual_initial_risk_usd": row["actual_initial_risk_usd"],
            "peak_campaign_risk_usd": row["peak_campaign_risk_usd"],
            "current_risk_to_stop_usd": row["current_risk_to_stop_usd"],
            "giveback_to_stop_usd": row["giveback_to_stop_usd"],
            "locked_profit_usd": row["locked_profit_usd"],
            "closed_target_r": row["closed_target_r"],
            "closed_actual_r": row["closed_actual_r"],
            "risk_data_quality_status": row["data_quality_status"],
            "risk_flags": row["risk_flags"],
            "updated_at": row["updated_at"],
        }
        supabase.table("campaigns").update(payload).eq("campaign_id", row["campaign_id"]).execute()

        if row["risk_flags"]:
            _audit(
                "campaign_risk_snapshot_flags",
                "warning" if row["data_quality_status"] != "uncertain" else "critical",
                "Campaign risk snapshot has missing or estimated fields",
                {
                    "risk_flags": row["risk_flags"],
                    "data_quality_status": row["data_quality_status"],
                    "target_risk_source": row["target_risk_source"],
                    "actual_risk_source": row["actual_risk_source"],
                    "live_price_source": row["live_price_source"],
                    "current_stop_source": row["current_stop_source"],
                },
                symbol=row["symbol"],
                campaign_id=row["campaign_id"],
                account_id=row["account_id"],
            )

    print("risk_snapshots_upserted=", len(rows))

def status():
    rows = _fetch_all("campaign_risk_snapshots")
    print("risk_snapshots=", len(rows))

    by_quality = defaultdict(int)
    flag_counts = defaultdict(int)

    for row in rows:
        by_quality[row.get("data_quality_status")] += 1
        flags = row.get("risk_flags") or []
        if isinstance(flags, str):
            try:
                flags = json.loads(flags)
            except Exception:
                flags = []
        for flag in flags:
            flag_counts[flag] += 1

    print("by_risk_quality=")
    for k, v in sorted(by_quality.items(), key=lambda x: str(x[0])):
        print(f"  {k}: {v}")

    print("risk_flags=")
    for k, v in sorted(flag_counts.items(), key=lambda x: str(x[0])):
        print(f"  {k}: {v}")

    open_rows = [r for r in rows if (_f(r.get("quantity_remaining"), 0) or 0) > 0]
    print("open_risk_snapshots=")
    for r in sorted(open_rows, key=lambda x: x.get("symbol") or ""):
        print(
            f"  {r.get('symbol')} | {r.get('campaign_id')} | "
            f"qty={r.get('quantity_remaining')} | target={r.get('target_risk_usd')} | "
            f"actual={r.get('actual_initial_risk_usd')} | current_risk={r.get('current_risk_to_stop_usd')} | "
            f"giveback={r.get('giveback_to_stop_usd')} | quality={r.get('data_quality_status')} | flags={r.get('risk_flags')}"
        )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["dry-run", "build", "status"])
    args = parser.parse_args()

    if args.command == "dry-run":
        build_snapshots(dry_run=True)
    elif args.command == "build":
        build_snapshots(dry_run=False)
    elif args.command == "status":
        status()

if __name__ == "__main__":
    main()
