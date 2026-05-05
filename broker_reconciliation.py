import os
import json
import uuid
import argparse
import xml.etree.ElementTree as ET
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

def _f(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None

def _sum(vals):
    return sum(v for v in vals if isinstance(v, (int, float)))

def _date(v):
    x = _s(v)
    if not x:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            raw = x[:10] if fmt == "%Y-%m-%d" else x[:8]
            return datetime.strptime(raw, fmt).date().isoformat()
        except Exception:
            pass
    return None

def _timestamp(v):
    x = _s(v)
    if not x:
        return None
    for fmt in ("%Y%m%d;%H%M%S", "%Y-%m-%d;%H:%M:%S", "%Y-%m-%d;%H%M%S"):
        try:
            return datetime.strptime(x, fmt).replace(tzinfo=timezone.utc).isoformat()
        except Exception:
            pass
    return None

def _near(a, b, tol=0.0001):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol

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

def _candidate_reports():
    paths = [
        BASE_DIR / "ibkr_raw_report.xml",
        BASE_DIR / "_archive_scripts" / "ibkr_raw_report.xml",
    ]

    arch = BASE_DIR / "_archive_scripts"
    if arch.exists():
        paths.extend(sorted(arch.glob("*ibkr*.xml"), reverse=True))
        paths.extend(sorted(arch.glob("*Flex*.xml"), reverse=True))
        paths.extend(sorted(arch.glob("*.xml"), reverse=True))

    out = []
    seen = set()
    for p in paths:
        if p.exists() and p not in seen:
            seen.add(p)
            out.append(p)
    return out

def _parse_xml_report(path):
    root = ET.parse(path).getroot()
    fs = root.find(".//FlexStatement")
    if fs is None:
        raise ValueError("FlexStatement not found")

    trades = []
    for t in fs.findall(".//Trade"):
        qty = _f(t.get("quantity"))
        side = (t.get("buySell") or "").upper() or ("SELL" if qty is not None and qty < 0 else "BUY")
        trades.append({
            "source_trade_id": _s(t.get("tradeID")),
            "symbol": _s(t.get("symbol")),
            "side": side,
            "quantity": qty,
            "price": _f(t.get("tradePrice")),
            "trade_date": _date(t.get("tradeDate")),
            "commission": _f(t.get("ibCommission")),
            "fifo_pnl_realized": _f(t.get("fifoPnlRealized")),
            "raw": dict(t.attrib),
        })

    change = fs.find(".//ChangeInNAV")

    return {
        "path": str(path),
        "account_id": fs.get("accountId"),
        "from_date": _date(fs.get("fromDate")),
        "to_date": _date(fs.get("toDate")),
        "generated_at": _timestamp(fs.get("whenGenerated")),
        "has_change_in_nav": change is not None,
        "trade_count": len(trades),
        "trades": trades,
    }

def _latest_xml_report():
    reports = []
    for path in _candidate_reports():
        try:
            r = _parse_xml_report(path)
            reports.append(r)
        except Exception as e:
            print(f"xml skipped {path}: {e}")

    if not reports:
        return None

    def score(r):
        return (
            r.get("to_date") or "",
            r.get("generated_at") or "",
            1 if r.get("has_change_in_nav") else 0,
            r.get("trade_count") or 0,
        )

    return sorted(reports, key=score, reverse=True)[0]

def _normalize_trade_table(row):
    qty = _f(row.get("quantity"))
    side = (_s(row.get("side")) or "").upper()
    if side not in ["BUY", "SELL"] and qty is not None:
        side = "SELL" if qty < 0 else "BUY"

    return {
        "source_trade_id": _s(row.get("trade_id")),
        "symbol": _s(row.get("symbol")),
        "side": side,
        "quantity": qty,
        "price": _f(row.get("price")),
        "trade_date": _date(row.get("trade_date")),
        "commission": _f(row.get("commission")),
        "fifo_pnl_realized": _f(row.get("pnl_usd")),
        "raw": row,
    }

def _normalize_execution(row):
    return {
        "execution_id": row.get("execution_id"),
        "execution_key": _s(row.get("execution_key")),
        "source_trade_id": _s(row.get("source_trade_id")),
        "account_id": _s(row.get("account_id")),
        "symbol": _s(row.get("symbol")),
        "side": (_s(row.get("side")) or "").upper(),
        "quantity": _f(row.get("quantity")),
        "price": _f(row.get("price")),
        "trade_date": _date(row.get("trade_date")),
        "commission": _f(row.get("commission")),
        "fifo_pnl_realized": _f(row.get("fifo_pnl_realized")),
        "raw": row,
    }

def _account_id_from_executions(executions):
    for e in executions:
        if e.get("account_id"):
            return e.get("account_id")
    return "unknown_account"

def _in_scope(row, from_date=None, to_date=None):
    d = row.get("trade_date")
    if from_date and d and d < from_date:
        return False
    if to_date and d and d > to_date:
        return False
    return True

def _add_break(breaks, severity, break_type, message, broker=None, sentinel=None, field=None):
    broker = broker or {}
    sentinel = sentinel or {}
    breaks.append({
        "severity": severity,
        "break_type": break_type,
        "symbol": broker.get("symbol") or sentinel.get("symbol"),
        "trade_date": broker.get("trade_date") or sentinel.get("trade_date"),
        "source_trade_id": broker.get("source_trade_id") or sentinel.get("source_trade_id"),
        "execution_key": sentinel.get("execution_key"),
        "message": message,
        "broker_value": None if broker.get(field) is None else str(broker.get(field)) if field else None,
        "sentinel_value": None if sentinel.get(field) is None else str(sentinel.get(field)) if field else None,
        "payload": {
            "field": field,
            "broker": broker,
            "sentinel": sentinel,
        },
    })

def _compare(source_rows, execution_rows, source_name, meta):
    source_by_id = {r.get("source_trade_id"): r for r in source_rows if r.get("source_trade_id")}
    exec_by_id = {r.get("source_trade_id"): r for r in execution_rows if r.get("source_trade_id")}

    breaks = []

    missing_ids = sorted(set(source_by_id) - set(exec_by_id))
    extra_ids = sorted(set(exec_by_id) - set(source_by_id))

    for sid in missing_ids:
        _add_break(
            breaks,
            "critical",
            "missing_in_sentinel",
            "Broker/source execution is missing in Sentinel executions",
            broker=source_by_id[sid],
        )

    for sid in extra_ids:
        _add_break(
            breaks,
            "critical",
            "extra_in_sentinel",
            "Sentinel execution does not exist in broker/source scope",
            sentinel=exec_by_id[sid],
        )

    comparable_ids = sorted(set(source_by_id) & set(exec_by_id))

    for sid in comparable_ids:
        b = source_by_id[sid]
        e = exec_by_id[sid]

        for field in ["symbol", "side", "trade_date"]:
            if (b.get(field) or "") != (e.get(field) or ""):
                _add_break(
                    breaks,
                    "critical",
                    f"{field}_mismatch",
                    f"{field} differs between broker/source and Sentinel",
                    broker=b,
                    sentinel=e,
                    field=field,
                )

        for field in ["quantity", "price"]:
            if not _near(b.get(field), e.get(field)):
                _add_break(
                    breaks,
                    "critical",
                    f"{field}_mismatch",
                    f"{field} differs between broker/source and Sentinel",
                    broker=b,
                    sentinel=e,
                    field=field,
                )

        if b.get("fifo_pnl_realized") is not None and e.get("fifo_pnl_realized") is not None:
            if not _near(b.get("fifo_pnl_realized"), e.get("fifo_pnl_realized")):
                _add_break(
                    breaks,
                    "critical",
                    "fifo_pnl_realized_mismatch",
                    "Realized PnL differs between broker/source and Sentinel",
                    broker=b,
                    sentinel=e,
                    field="fifo_pnl_realized",
                )

        if b.get("commission") is not None and e.get("commission") is None:
            _add_break(
                breaks,
                "warning",
                "commission_missing_in_sentinel",
                "Broker/source has commission but Sentinel execution commission is missing",
                broker=b,
                sentinel=e,
                field="commission",
            )
        elif b.get("commission") is not None and e.get("commission") is not None:
            if not _near(b.get("commission"), e.get("commission")):
                _add_break(
                    breaks,
                    "warning",
                    "commission_mismatch",
                    "Commission differs between broker/source and Sentinel",
                    broker=b,
                    sentinel=e,
                    field="commission",
                )

    critical = [b for b in breaks if b["severity"] == "critical"]
    warnings = [b for b in breaks if b["severity"] != "critical"]

    broker_pnl = _sum([r.get("fifo_pnl_realized") for r in source_rows])
    sent_pnl = _sum([r.get("fifo_pnl_realized") for r in execution_rows])
    broker_comm = _sum([r.get("commission") for r in source_rows])
    sent_comm = _sum([r.get("commission") for r in execution_rows])

    status = "passed" if not critical else "breaks_found"
    quality = "verified" if status == "passed" else "broken"

    return {
        "status": status,
        "data_quality_status": quality,
        "broker_count": len(source_rows),
        "sentinel_count": len(execution_rows),
        "missing_in_sentinel": len(missing_ids),
        "extra_in_sentinel": len(extra_ids),
        "field_breaks": len(critical),
        "warning_count": len(warnings),
        "broker_realized_pnl": broker_pnl,
        "sentinel_realized_pnl": sent_pnl,
        "realized_pnl_diff": sent_pnl - broker_pnl,
        "broker_commission": broker_comm,
        "sentinel_commission": sent_comm,
        "commission_diff": sent_comm - broker_comm,
        "breaks": breaks,
        "payload": {
            "source_name": source_name,
            "meta": meta,
            "critical_breaks": len(critical),
            "warnings": len(warnings),
        },
    }

def _insert_run(account_id, reconciliation_type, source_name, meta, result):
    run_id = str(uuid.uuid4())

    run = {
        "run_id": run_id,
        "account_id": account_id,
        "reconciliation_type": reconciliation_type,
        "source_name": source_name,
        "source_file": meta.get("source_file"),
        "source_from_date": meta.get("source_from_date"),
        "source_to_date": meta.get("source_to_date"),
        "source_generated_at": meta.get("source_generated_at"),
        "status": result["status"],
        "data_quality_status": result["data_quality_status"],
        "broker_count": result["broker_count"],
        "sentinel_count": result["sentinel_count"],
        "missing_in_sentinel": result["missing_in_sentinel"],
        "extra_in_sentinel": result["extra_in_sentinel"],
        "field_breaks": result["field_breaks"],
        "warning_count": result["warning_count"],
        "broker_realized_pnl": result["broker_realized_pnl"],
        "sentinel_realized_pnl": result["sentinel_realized_pnl"],
        "realized_pnl_diff": result["realized_pnl_diff"],
        "broker_commission": result["broker_commission"],
        "sentinel_commission": result["sentinel_commission"],
        "commission_diff": result["commission_diff"],
        "payload": result["payload"],
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }

    supabase.table("broker_reconciliation_runs").insert(run).execute()

    rows = []
    for b in result["breaks"]:
        b["run_id"] = run_id
        rows.append(b)

    for i in range(0, len(rows), 100):
        supabase.table("broker_reconciliation_breaks").insert(rows[i:i+100]).execute()

    return run_id

def run_trades_baseline():
    trades = [_normalize_trade_table(r) for r in _fetch_all("trades")]
    executions = [_normalize_execution(r) for r in _fetch_all("executions")]

    account_id = _account_id_from_executions(executions)

    meta = {
        "source_file": None,
        "source_from_date": min([r["trade_date"] for r in trades if r.get("trade_date")], default=None),
        "source_to_date": max([r["trade_date"] for r in trades if r.get("trade_date")], default=None),
        "source_generated_at": None,
    }

    result = _compare(trades, executions, "supabase_trades_table", meta)
    run_id = _insert_run(account_id, "trades_table_baseline", "supabase_trades_table", meta, result)

    print("trades_baseline_run_id=", run_id)
    print("status=", result["status"])
    print("data_quality_status=", result["data_quality_status"])
    print("broker_count=", result["broker_count"])
    print("sentinel_count=", result["sentinel_count"])
    print("missing_in_sentinel=", result["missing_in_sentinel"])
    print("extra_in_sentinel=", result["extra_in_sentinel"])
    print("field_breaks=", result["field_breaks"])
    print("warning_count=", result["warning_count"])
    print("realized_pnl_diff=", round(result["realized_pnl_diff"], 6))
    print("commission_diff=", round(result["commission_diff"], 6))

def run_xml_baseline():
    report = _latest_xml_report()
    if not report:
        print("xml_baseline_status= no_xml_report_found")
        return

    executions_all = [_normalize_execution(r) for r in _fetch_all("executions")]
    executions = [
        r for r in executions_all
        if _in_scope(r, report.get("from_date"), report.get("to_date"))
    ]

    meta = {
        "source_file": report.get("path"),
        "source_from_date": report.get("from_date"),
        "source_to_date": report.get("to_date"),
        "source_generated_at": report.get("generated_at"),
        "has_change_in_nav": report.get("has_change_in_nav"),
        "trade_count": report.get("trade_count"),
    }

    result = _compare(report["trades"], executions, "ibkr_xml_report", meta)

    sentinel_max_date = max([r["trade_date"] for r in executions_all if r.get("trade_date")], default=None)
    if report.get("to_date") and sentinel_max_date and report.get("to_date") < sentinel_max_date:
        result["warning_count"] += 1
        result["payload"]["source_scope_warning"] = (
            "IBKR XML source is older than Sentinel executions. "
            "XML reconciliation is valid only through source_to_date."
        )

    run_id = _insert_run(report.get("account_id"), "ibkr_xml_baseline", "ibkr_xml_report", meta, result)

    print("xml_baseline_run_id=", run_id)
    print("status=", result["status"])
    print("data_quality_status=", result["data_quality_status"])
    print("source_file=", report.get("path"))
    print("source_from_date=", report.get("from_date"))
    print("source_to_date=", report.get("to_date"))
    print("source_generated_at=", report.get("generated_at"))
    print("has_change_in_nav=", report.get("has_change_in_nav"))
    print("broker_count=", result["broker_count"])
    print("sentinel_count_in_xml_scope=", result["sentinel_count"])
    print("missing_in_sentinel=", result["missing_in_sentinel"])
    print("extra_in_sentinel=", result["extra_in_sentinel"])
    print("field_breaks=", result["field_breaks"])
    print("warning_count=", result["warning_count"])
    print("realized_pnl_diff=", round(result["realized_pnl_diff"], 6))
    print("commission_diff=", round(result["commission_diff"], 6))

def status():
    runs = supabase.table("broker_reconciliation_runs").select("*").order("created_at", desc=True).limit(5).execute().data or []
    print("recent_reconciliation_runs=", len(runs))
    for r in runs:
        print(json.dumps({
            "run_id": r.get("run_id"),
            "type": r.get("reconciliation_type"),
            "status": r.get("status"),
            "quality": r.get("data_quality_status"),
            "broker_count": r.get("broker_count"),
            "sentinel_count": r.get("sentinel_count"),
            "missing": r.get("missing_in_sentinel"),
            "extra": r.get("extra_in_sentinel"),
            "field_breaks": r.get("field_breaks"),
            "warnings": r.get("warning_count"),
            "source_to_date": r.get("source_to_date"),
        }, ensure_ascii=False))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["trades", "xml", "all", "status"])
    args = parser.parse_args()

    if args.command in ["trades", "all"]:
        run_trades_baseline()

    if args.command in ["xml", "all"]:
        run_xml_baseline()

    if args.command == "status":
        status()

if __name__ == "__main__":
    main()
