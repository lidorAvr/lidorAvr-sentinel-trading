import os
import json
import uuid
import argparse
from pathlib import Path
from collections import Counter, defaultdict
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

def _break(breaks, severity, break_type, message, **payload):
    breaks.append({
        "severity": severity,
        "break_type": break_type,
        "symbol": payload.get("symbol"),
        "campaign_id": payload.get("campaign_id"),
        "execution_key": payload.get("execution_key"),
        "lot_key": payload.get("lot_key"),
        "message": message,
        "payload": payload,
    })

def _latest_reconciliation():
    try:
        rows = supabase.table("broker_reconciliation_runs").select("*").order("created_at", desc=True).limit(10).execute().data or []
    except Exception:
        return None

    # Prefer the trades table baseline because XML may be stale.
    for r in rows:
        if r.get("reconciliation_type") == "trades_table_baseline":
            return r

    return rows[0] if rows else None

def run_audit(dry_run=False):
    executions = _fetch_all("executions")
    lots = _fetch_all("position_lots")
    closures = _fetch_all("lot_closures")
    campaigns = _fetch_all("campaigns")

    breaks = []

    execution_keys = [_s(e.get("execution_key")) for e in executions if _s(e.get("execution_key"))]
    duplicate_execution_keys = len(execution_keys) - len(set(execution_keys))

    if duplicate_execution_keys:
        _break(
            breaks,
            "critical",
            "duplicate_execution_keys",
            "Duplicate execution keys found",
            duplicate_count=duplicate_execution_keys,
        )

    required_execution_fields = ["execution_key", "symbol", "side", "quantity", "price", "trade_date"]
    executions_missing_required = 0

    for e in executions:
        missing = [field for field in required_execution_fields if e.get(field) in [None, ""]]
        if missing:
            executions_missing_required += 1
            _break(
                breaks,
                "critical",
                "execution_missing_required_fields",
                "Execution is missing required fields",
                execution_key=e.get("execution_key"),
                symbol=e.get("symbol"),
                campaign_id=e.get("campaign_id"),
                missing=missing,
            )

    campaign_ids = set(_s(c.get("campaign_id")) for c in campaigns if _s(c.get("campaign_id")))
    lot_ids = set(_s(l.get("lot_id")) for l in lots if _s(l.get("lot_id")))
    lot_keys = set(_s(l.get("lot_key")) for l in lots if _s(l.get("lot_key")))

    lots_without_campaign = 0
    lots_quantity_negative = 0

    for lot in lots:
        cid = _s(lot.get("campaign_id"))
        if not cid or cid not in campaign_ids:
            lots_without_campaign += 1
            _break(
                breaks,
                "critical",
                "lot_without_campaign",
                "Lot is not linked to a valid campaign",
                symbol=lot.get("symbol"),
                campaign_id=cid,
                lot_key=lot.get("lot_key"),
            )

        if _f(lot.get("quantity_remaining"), 0) < -0.000001:
            lots_quantity_negative += 1
            _break(
                breaks,
                "critical",
                "lot_negative_quantity",
                "Lot has negative remaining quantity",
                symbol=lot.get("symbol"),
                campaign_id=cid,
                lot_key=lot.get("lot_key"),
                quantity_remaining=lot.get("quantity_remaining"),
            )

    closures_without_lot = 0
    closures_without_campaign = 0

    for cl in closures:
        cid = _s(cl.get("campaign_id"))
        lk = _s(cl.get("lot_key"))

        if not lk or lk not in lot_keys:
            closures_without_lot += 1
            _break(
                breaks,
                "critical",
                "closure_without_lot",
                "Lot closure is not linked to a valid lot",
                symbol=cl.get("symbol"),
                campaign_id=cid,
                lot_key=lk,
                execution_key=cl.get("close_execution_key"),
            )

        if not cid or cid not in campaign_ids:
            closures_without_campaign += 1
            _break(
                breaks,
                "critical",
                "closure_without_campaign",
                "Lot closure is not linked to a valid campaign",
                symbol=cl.get("symbol"),
                campaign_id=cid,
                lot_key=lk,
                execution_key=cl.get("close_execution_key"),
            )

    # Compare campaign aggregate quantities to lots/closures.
    lots_by_campaign = defaultdict(list)
    closures_by_campaign = defaultdict(list)

    for lot in lots:
        lots_by_campaign[_s(lot.get("campaign_id"))].append(lot)

    for cl in closures:
        closures_by_campaign[_s(cl.get("campaign_id"))].append(cl)

    for c in campaigns:
        cid = _s(c.get("campaign_id"))
        clots = lots_by_campaign.get(cid, [])
        cclosures = closures_by_campaign.get(cid, [])

        lot_opened = sum(abs(_f(l.get("quantity_opened"), 0)) for l in clots)
        lot_remaining = sum(abs(_f(l.get("quantity_remaining"), 0)) for l in clots)
        closure_qty = sum(abs(_f(cl.get("quantity_closed"), 0)) for cl in cclosures)
        closure_pnl = sum(_f(cl.get("fifo_pnl_realized_allocated"), 0) for cl in cclosures)

        if abs(lot_opened - _f(c.get("total_quantity_opened"), 0)) > 0.0001:
            _break(
                breaks,
                "critical",
                "campaign_opened_quantity_mismatch",
                "Campaign total opened quantity does not match lots",
                symbol=c.get("symbol"),
                campaign_id=cid,
                campaign_value=c.get("total_quantity_opened"),
                computed_value=lot_opened,
            )

        if abs(lot_remaining - _f(c.get("quantity_remaining"), 0)) > 0.0001:
            _break(
                breaks,
                "critical",
                "campaign_remaining_quantity_mismatch",
                "Campaign remaining quantity does not match lots",
                symbol=c.get("symbol"),
                campaign_id=cid,
                campaign_value=c.get("quantity_remaining"),
                computed_value=lot_remaining,
            )

        if abs(closure_qty - _f(c.get("total_quantity_closed"), 0)) > 0.0001:
            _break(
                breaks,
                "critical",
                "campaign_closed_quantity_mismatch",
                "Campaign closed quantity does not match closures",
                symbol=c.get("symbol"),
                campaign_id=cid,
                campaign_value=c.get("total_quantity_closed"),
                computed_value=closure_qty,
            )

        if abs(closure_pnl - _f(c.get("realized_pnl_usd"), 0)) > 0.01:
            _break(
                breaks,
                "critical",
                "campaign_realized_pnl_mismatch",
                "Campaign realized PnL does not match allocated closures",
                symbol=c.get("symbol"),
                campaign_id=cid,
                campaign_value=c.get("realized_pnl_usd"),
                computed_value=closure_pnl,
            )

    # Strategy eligibility sanity.
    strategy_verified = [c for c in campaigns if c.get("strategy_status") == "strategy_verified"]
    for c in strategy_verified:
        if not c.get("strategy_eligible"):
            _break(
                breaks,
                "critical",
                "strategy_verified_not_eligible",
                "Campaign is strategy_verified but strategy_eligible is false",
                symbol=c.get("symbol"),
                campaign_id=c.get("campaign_id"),
            )

        if c.get("has_open_position"):
            _break(
                breaks,
                "critical",
                "open_strategy_verified_campaign",
                "Open campaign cannot be strategy_verified for official closed stats",
                symbol=c.get("symbol"),
                campaign_id=c.get("campaign_id"),
            )

    open_campaigns = [c for c in campaigns if c.get("has_open_position")]
    for c in open_campaigns:
        if c.get("strategy_eligible"):
            _break(
                breaks,
                "critical",
                "open_campaign_strategy_eligible",
                "Open campaign cannot be eligible for official strategy stats",
                symbol=c.get("symbol"),
                campaign_id=c.get("campaign_id"),
            )

    # Warnings: expected but important.
    accounting_only = [c for c in campaigns if c.get("strategy_status") == "accounting_only"]
    live_management_only = [c for c in campaigns if c.get("strategy_status") == "live_management_only"]
    unclassified = [c for c in campaigns if c.get("strategy_status") == "unclassified"]

    for c in accounting_only:
        _break(
            breaks,
            "warning",
            "campaign_accounting_only",
            "Campaign is valid for accounting but excluded from official strategy stats",
            symbol=c.get("symbol"),
            campaign_id=c.get("campaign_id"),
            reason=c.get("strategy_exclusion_reason") or c.get("eligibility_reason"),
        )

    for c in live_management_only:
        _break(
            breaks,
            "warning",
            "campaign_live_management_only",
            "Open campaign is managed live but excluded from official closed strategy stats",
            symbol=c.get("symbol"),
            campaign_id=c.get("campaign_id"),
            reason=c.get("strategy_exclusion_reason") or c.get("eligibility_reason"),
        )

    for c in unclassified:
        _break(
            breaks,
            "warning",
            "campaign_unclassified",
            "Campaign is missing classification for strategy stats",
            symbol=c.get("symbol"),
            campaign_id=c.get("campaign_id"),
            reason=c.get("strategy_exclusion_reason") or c.get("eligibility_reason"),
        )

    rec = _latest_reconciliation()
    rec_status = rec.get("status") if rec else None
    rec_quality = rec.get("data_quality_status") if rec else None

    if not rec:
        _break(
            breaks,
            "warning",
            "missing_reconciliation_baseline",
            "No broker reconciliation baseline found",
        )
    elif rec_status != "passed":
        _break(
            breaks,
            "critical",
            "reconciliation_not_passed",
            "Latest trades baseline reconciliation did not pass",
            run_id=rec.get("run_id"),
            status=rec_status,
            quality=rec_quality,
        )

    critical_breaks = len([b for b in breaks if b["severity"] == "critical"])
    warning_breaks = len([b for b in breaks if b["severity"] != "critical"])

    acceptance_passed = critical_breaks == 0
    data_quality = "verified" if acceptance_passed else "broken"
    status = "passed" if acceptance_passed else "breaks_found"

    by_campaign_status = Counter(c.get("campaign_status") for c in campaigns)
    by_strategy_status = Counter(c.get("strategy_status") for c in campaigns)
    by_quality = Counter(c.get("data_quality_status") for c in campaigns)

    run = {
        "audit_run_id": str(uuid.uuid4()),
        "audit_version": "data_accuracy_audit_v1",
        "status": status,
        "data_quality_status": data_quality,
        "executions_count": len(executions),
        "duplicate_execution_keys": duplicate_execution_keys,
        "executions_missing_required": executions_missing_required,
        "lots_count": len(lots),
        "lots_without_campaign": lots_without_campaign,
        "lots_quantity_negative": lots_quantity_negative,
        "closures_count": len(closures),
        "closures_without_lot": closures_without_lot,
        "closures_without_campaign": closures_without_campaign,
        "campaigns_count": len(campaigns),
        "strategy_verified_count": len(strategy_verified),
        "accounting_only_count": len(accounting_only),
        "live_management_only_count": len(live_management_only),
        "open_campaigns_count": len(open_campaigns),
        "broker_reconciliation_status": rec_status,
        "broker_reconciliation_quality": rec_quality,
        "critical_breaks": critical_breaks,
        "warning_breaks": warning_breaks,
        "acceptance_passed": acceptance_passed,
        "payload": {
            "by_campaign_status": dict(by_campaign_status),
            "by_strategy_status": dict(by_strategy_status),
            "by_campaign_data_quality": dict(by_quality),
            "acceptance_criteria": [
                "No duplicate executions",
                "All executions have required fields",
                "All lots linked to campaigns",
                "All closures linked to lots and campaigns",
                "Campaign aggregates match lots/closures",
                "Open campaigns are excluded from official strategy stats",
                "Trades baseline reconciliation passed",
            ],
        },
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }

    if dry_run:
        print(json.dumps(run, ensure_ascii=False, indent=2))
        print("breaks_preview=")
        for b in breaks[:20]:
            print(json.dumps({
                "severity": b["severity"],
                "type": b["break_type"],
                "symbol": b.get("symbol"),
                "campaign_id": b.get("campaign_id"),
                "message": b["message"],
            }, ensure_ascii=False))
        return run, breaks

    supabase.table("data_accuracy_audit_runs").insert(run).execute()

    rows = []
    for b in breaks:
        row = dict(b)
        row["audit_run_id"] = run["audit_run_id"]
        rows.append(row)

    for i in range(0, len(rows), 100):
        supabase.table("data_accuracy_audit_breaks").insert(rows[i:i+100]).execute()

    print("audit_run_id=", run["audit_run_id"])
    print("status=", run["status"])
    print("data_quality_status=", run["data_quality_status"])
    print("acceptance_passed=", run["acceptance_passed"])
    print("critical_breaks=", run["critical_breaks"])
    print("warning_breaks=", run["warning_breaks"])
    print("executions_count=", run["executions_count"])
    print("lots_count=", run["lots_count"])
    print("closures_count=", run["closures_count"])
    print("campaigns_count=", run["campaigns_count"])
    print("strategy_verified_count=", run["strategy_verified_count"])
    print("accounting_only_count=", run["accounting_only_count"])
    print("live_management_only_count=", run["live_management_only_count"])
    print("broker_reconciliation_status=", run["broker_reconciliation_status"])

def status():
    rows = supabase.table("data_accuracy_audit_runs").select("*").order("created_at", desc=True).limit(5).execute().data or []
    print("recent_audit_runs=", len(rows))
    for r in rows:
        print(json.dumps({
            "audit_run_id": r.get("audit_run_id"),
            "status": r.get("status"),
            "quality": r.get("data_quality_status"),
            "acceptance_passed": r.get("acceptance_passed"),
            "critical": r.get("critical_breaks"),
            "warnings": r.get("warning_breaks"),
            "executions": r.get("executions_count"),
            "lots": r.get("lots_count"),
            "closures": r.get("closures_count"),
            "campaigns": r.get("campaigns_count"),
            "strategy_verified": r.get("strategy_verified_count"),
        }, ensure_ascii=False))

    if rows:
        run_id = rows[0].get("audit_run_id")
        breaks = supabase.table("data_accuracy_audit_breaks").select("*").eq("audit_run_id", run_id).order("created_at", desc=False).limit(20).execute().data or []
        print("latest_breaks_preview=", len(breaks))
        for b in breaks:
            print(json.dumps({
                "severity": b.get("severity"),
                "type": b.get("break_type"),
                "symbol": b.get("symbol"),
                "campaign_id": b.get("campaign_id"),
                "message": b.get("message"),
            }, ensure_ascii=False))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["dry-run", "run", "status"])
    args = parser.parse_args()

    if args.command == "dry-run":
        run_audit(dry_run=True)
    elif args.command == "run":
        run_audit(dry_run=False)
    elif args.command == "status":
        status()

if __name__ == "__main__":
    main()
