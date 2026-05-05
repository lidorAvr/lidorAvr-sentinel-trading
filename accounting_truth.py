import os
import json
import uuid
import hashlib
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

def _safe_float(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None

def _safe_str(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None

def _account_id():
    for key in ["IBKR_ACCOUNT_ID", "ACCOUNT_ID", "account_id"]:
        val = os.getenv(key)
        if val:
            return val

    cfg_path = BASE_DIR / "sentinel_config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            val = cfg.get("account_id") or cfg.get("ibkr_account_id")
            if val:
                return val
        except Exception:
            pass

    try:
        import xml.etree.ElementTree as ET
        candidates = [
            BASE_DIR / "ibkr_raw_report.xml",
            BASE_DIR / "_archive_scripts" / "ibkr_raw_report.xml",
        ]

        arch = BASE_DIR / "_archive_scripts"
        if arch.exists():
            candidates.extend(sorted(arch.glob("*ibkr*.xml"), reverse=True))
            candidates.extend(sorted(arch.glob("*Flex*.xml"), reverse=True))
            candidates.extend(sorted(arch.glob("*.xml"), reverse=True))

        seen = set()
        for path in candidates:
            if not path.exists() or path in seen:
                continue
            seen.add(path)
            try:
                root = ET.parse(path).getroot()
                fs = root.find(".//FlexStatement")
                if fs is not None and fs.get("accountId"):
                    return fs.get("accountId")
            except Exception:
                continue
    except Exception:
        pass

    return "unknown_account"


def _parse_trade_date(v):
    s = _safe_str(v)
    if not s:
        return None
    for fmt in ["%Y-%m-%d", "%Y%m%d"]:
        try:
            return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s[:8], fmt).date().isoformat()
        except Exception:
            pass
    return None

def _parse_execution_time(trade_date, order_time):
    td = _safe_str(trade_date)
    ot = _safe_str(order_time)

    candidates = []
    if ot and ";" in ot:
        candidates.append(ot)
    if td and ot and ";" not in ot:
        candidates.append(f"{td};{ot}")

    for c in candidates:
        for fmt in ["%Y%m%d;%H%M%S", "%Y-%m-%d;%H:%M:%S", "%Y-%m-%d;%H%M%S"]:
            try:
                return datetime.strptime(c, fmt).replace(tzinfo=timezone.utc).isoformat()
            except Exception:
                pass

    d = _parse_trade_date(trade_date)
    if d:
        return datetime.fromisoformat(d).replace(tzinfo=timezone.utc).isoformat()
    return None

def _normalize_side(row, qty):
    side = (_safe_str(row.get("side")) or "").upper()
    if side in ["BUY", "SELL"]:
        return side
    if qty is not None:
        return "SELL" if qty < 0 else "BUY"
    return None

def _execution_key(row, account_id, side, qty, price, execution_time):
    trade_id = _safe_str(row.get("trade_id"))
    if trade_id:
        return f"ibkr:{account_id}:{trade_id}"

    raw = "|".join([
        account_id or "",
        _safe_str(row.get("symbol")) or "",
        side or "",
        str(qty) if qty is not None else "",
        str(price) if price is not None else "",
        execution_time or "",
    ])
    return "hash:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _json_safe(row):
    out = {}
    for k, v in row.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        else:
            out[k] = str(v)
    return out

def _audit(event_type, severity, message, payload=None, symbol=None, campaign_id=None, execution_key=None):
    try:
        supabase.table("campaign_audit_events").insert({
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "symbol": symbol,
            "campaign_id": campaign_id,
            "execution_key": execution_key,
            "payload": payload or {},
        }).execute()
    except Exception as e:
        print(f"audit write skipped: {e}")

def normalize_trade_row(row, import_batch_id=None):
    account_id = _account_id()
    qty = _safe_float(row.get("quantity"))
    price = _safe_float(row.get("price"))
    commission = _safe_float(row.get("commission"))
    pnl = _safe_float(row.get("pnl_usd"))
    trade_date = _parse_trade_date(row.get("trade_date"))
    execution_time = _parse_execution_time(row.get("trade_date"), row.get("order_time"))
    side = _normalize_side(row, qty)
    symbol = _safe_str(row.get("symbol"))
    campaign_id = _safe_str(row.get("campaign_id"))
    execution_key = _execution_key(row, account_id, side, qty, price, execution_time)

    missing = []
    if not symbol:
        missing.append("symbol")
    if side not in ["BUY", "SELL"]:
        missing.append("side")
    if qty is None or qty == 0:
        missing.append("quantity")
    if price is None:
        missing.append("price")
    if not trade_date:
        missing.append("trade_date")

    data_quality = "verified" if not missing else "uncertain"
    commission_status = "reported" if commission is not None else "missing"

    payload = {
        "execution_key": execution_key,
        "source": "legacy_trades_backfill",
        "source_trade_id": _safe_str(row.get("trade_id")),
        "account_id": account_id,
        "symbol": symbol,
        "side": side,
        "quantity": qty,
        "abs_quantity": abs(qty) if qty is not None else None,
        "price": price,
        "execution_time": execution_time,
        "trade_date": trade_date,
        "commission": commission,
        "commission_status": commission_status,
        "fifo_pnl_realized": pnl,
        "currency": "USD",
        "asset_class": _safe_str(row.get("asset_class")),
        "campaign_id": campaign_id,
        "parent_trade_id": _safe_str(row.get("parent_trade_id")),
        "accounting_scope": "YTD",
        "strategy_scope": "unknown",
        "data_quality_status": data_quality,
        "raw_payload": _json_safe(row),
        "import_batch_id": import_batch_id,
    }

    return payload, missing

def fetch_all_trades():
    rows = []
    start = 0
    page = 1000
    while True:
        res = supabase.table("trades").select("*").range(start, start + page - 1).execute()
        chunk = res.data or []
        rows.extend(chunk)
        if len(chunk) < page:
            break
        start += page
    return rows

def count_executions():
    try:
        res = supabase.table("executions").select("execution_key", count="exact").limit(1).execute()
        return res.count
    except Exception:
        return None

def backfill_trades(dry_run=False):
    batch_id = str(uuid.uuid4())
    rows = fetch_all_trades()
    normalized = []
    keys = []
    duplicate_keys = 0

    seen = set()
    for row in rows:
        item, missing = normalize_trade_row(row, batch_id)
        key = item["execution_key"]
        if key in seen:
            duplicate_keys += 1
        seen.add(key)
        keys.append(key)
        normalized.append((item, missing))

    if dry_run:
        print(f"dry_run rows_seen={len(rows)} unique_keys={len(seen)} duplicate_keys={duplicate_keys}")
        for item, missing in normalized[:5]:
            print(json.dumps({
                "execution_key": item["execution_key"],
                "symbol": item["symbol"],
                "side": item["side"],
                "quantity": item["quantity"],
                "price": item["price"],
                "quality": item["data_quality_status"],
                "missing": missing,
            }, ensure_ascii=False))
        return

    supabase.table("execution_import_batches").insert({
        "import_batch_id": batch_id,
        "source": "legacy_trades_backfill",
        "status": "running",
        "rows_seen": len(rows),
        "duplicate_keys": duplicate_keys,
    }).execute()

    upserted = 0
    for i in range(0, len(normalized), 100):
        batch = [x[0] for x in normalized[i:i+100]]
        supabase.table("executions").upsert(batch, on_conflict="execution_key").execute()
        upserted += len(batch)

    for item, missing in normalized:
        if missing:
            _audit(
                "execution_missing_required_fields",
                "warning",
                "Execution has missing required fields",
                {"missing": missing, "source_trade_id": item.get("source_trade_id")},
                symbol=item.get("symbol"),
                campaign_id=item.get("campaign_id"),
                execution_key=item.get("execution_key"),
            )

    supabase.table("execution_import_batches").update({
        "status": "completed",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "rows_upserted": upserted,
    }).eq("import_batch_id", batch_id).execute()

    print(f"completed rows_seen={len(rows)} rows_upserted={upserted} duplicate_keys={duplicate_keys}")
    print(f"executions_count={count_executions()}")

def check():
    rows = fetch_all_trades()
    keys = []
    missing_total = 0
    for row in rows:
        item, missing = normalize_trade_row(row)
        keys.append(item["execution_key"])
        if missing:
            missing_total += 1

    print(f"trades_rows={len(rows)}")
    print(f"unique_execution_keys={len(set(keys))}")
    print(f"duplicate_generated_keys={len(keys) - len(set(keys))}")
    print(f"rows_with_missing_required_fields={missing_total}")
    print(f"executions_count={count_executions()}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["check", "backfill-trades", "dry-run"])
    args = parser.parse_args()

    if args.command == "check":
        check()
    elif args.command == "dry-run":
        backfill_trades(dry_run=True)
    elif args.command == "backfill-trades":
        backfill_trades(dry_run=False)

if __name__ == "__main__":
    main()
