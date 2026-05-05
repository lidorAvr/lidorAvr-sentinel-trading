import os
import json
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

def _safe_float(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None

def _parse_ibkr_date(v):
    if not v:
        return None
    try:
        return datetime.strptime(str(v), "%Y%m%d").date().isoformat()
    except Exception:
        return None

def _parse_ibkr_timestamp(v):
    if not v:
        return None
    try:
        return datetime.strptime(str(v), "%Y%m%d;%H%M%S").replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        return None

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

def _read_config_account():
    for key in ["IBKR_ACCOUNT_ID", "ACCOUNT_ID"]:
        val = os.getenv(key)
        if val:
            return val

    cfg_path = BASE_DIR / "sentinel_config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            return cfg.get("account_id") or cfg.get("ibkr_account_id")
        except Exception:
            pass

    return None

def parse_scope_from_reports():
    best = {
        "account_id": _read_config_account(),
        "from_date": None,
        "to_date": None,
        "generated_at": None,
        "nav_start": None,
        "nav_end": None,
        "source_file": None,
        "has_change_in_nav": False,
    }

    for path in _candidate_reports():
        try:
            root = ET.parse(path).getroot()
            fs = root.find(".//FlexStatement")
            if fs is None:
                continue

            account_id = fs.get("accountId") or best["account_id"]
            from_date = _parse_ibkr_date(fs.get("fromDate"))
            to_date = _parse_ibkr_date(fs.get("toDate"))
            generated_at = _parse_ibkr_timestamp(fs.get("whenGenerated"))

            change = fs.find(".//ChangeInNAV")
            nav_start = None
            nav_end = None
            has_change = False

            if change is not None:
                has_change = True
                nav_start = _safe_float(change.get("startingValue"))
                nav_end = _safe_float(change.get("endingValue"))

            # Prefer reports that include ChangeInNAV; otherwise keep the first useful account/date report.
            if has_change or not best["source_file"]:
                best.update({
                    "account_id": account_id,
                    "from_date": from_date,
                    "to_date": to_date,
                    "generated_at": generated_at,
                    "nav_start": nav_start,
                    "nav_end": nav_end,
                    "source_file": str(path),
                    "has_change_in_nav": has_change,
                })

            if has_change and account_id:
                break

        except Exception as e:
            print(f"scope parse skipped {path}: {e}")

    return best

def _audit(event_type, severity, message, payload=None, account_id=None):
    try:
        supabase.table("campaign_audit_events").insert({
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "account_id": account_id,
            "payload": payload or {},
        }).execute()
    except Exception as e:
        print(f"audit write skipped: {e}")

def bootstrap_scope():
    scope = parse_scope_from_reports()
    account_id = scope.get("account_id") or "unknown_account"
    start_date = scope.get("from_date") or datetime.now(timezone.utc).date().replace(month=1, day=1).isoformat()

    quality = "verified" if scope.get("has_change_in_nav") and scope.get("nav_start") is not None else "estimated"

    policy = {
        "account_id": account_id,
        "data_scope_start_date": start_date,
        "data_scope_type": "YTD",
        "accounting_scope": "YTD",
        "strategy_scope": "YTD_VERIFIED_CAMPAIGNS_ONLY",
        "has_pre_scope_positions": False,
        "stats_confidence_level": "medium",
        "official_performance_scope": "YTD verified campaigns only",
        "lifetime_stats_available": False,
        "source_file": scope.get("source_file"),
        "source_generated_at": scope.get("generated_at"),
    }

    supabase.table("data_scope_policy").upsert(
        policy,
        on_conflict="account_id,data_scope_type,data_scope_start_date"
    ).execute()

    snapshot = {
        "account_id": account_id,
        "snapshot_date": start_date,
        "data_scope_type": "YTD",
        "nav_start": scope.get("nav_start"),
        "cash_start": None,
        "open_positions_start": [],
        "position_count": 0,
        "source_file": scope.get("source_file"),
        "source_generated_at": scope.get("generated_at"),
        "data_quality_status": quality,
        "notes": "Opening snapshot created from available IBKR Flex YTD scope. Cash/open positions require broker position snapshot if available.",
    }

    supabase.table("account_opening_snapshot").upsert(
        snapshot,
        on_conflict="account_id,snapshot_date,data_scope_type"
    ).execute()

    _audit(
        "data_scope_initialized",
        "info",
        "Data Scope Mode initialized",
        scope,
        account_id=account_id,
    )

    print("scope_account_id=", account_id)
    print("scope_start_date=", start_date)
    print("scope_source_file=", scope.get("source_file"))
    print("scope_has_change_in_nav=", scope.get("has_change_in_nav"))
    print("opening_nav_start=", scope.get("nav_start"))
    print("opening_snapshot_quality=", quality)

    return account_id

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

def fix_execution_account_id(account_id):
    if not account_id or account_id == "unknown_account":
        print("account_id unavailable; execution account migration skipped")
        return

    rows = _fetch_all("executions", "execution_id,execution_key,source_trade_id,account_id")
    changed = 0
    skipped = 0

    for row in rows:
        old_key = row.get("execution_key") or ""
        old_account = row.get("account_id")
        trade_id = row.get("source_trade_id")

        needs_update = old_account in [None, "", "unknown_account"] or ":unknown_account:" in old_key
        if not needs_update:
            skipped += 1
            continue

        if trade_id:
            new_key = f"ibkr:{account_id}:{trade_id}"
        else:
            new_key = old_key.replace(":unknown_account:", f":{account_id}:") if old_key else old_key

        try:
            supabase.table("executions").update({
                "account_id": account_id,
                "execution_key": new_key,
            }).eq("execution_id", row["execution_id"]).execute()
            changed += 1
        except Exception as e:
            _audit(
                "execution_account_id_migration_failed",
                "error",
                "Failed to migrate execution account id",
                {"error": str(e), "row": row, "new_key": new_key},
                account_id=account_id,
            )
            print(f"execution migration failed for {old_key}: {e}")

    print(f"execution_account_id_migrated={changed}")
    print(f"execution_account_id_skipped={skipped}")

def status():
    scope = parse_scope_from_reports()
    print(json.dumps(scope, ensure_ascii=False, indent=2))

    try:
        policies = supabase.table("data_scope_policy").select("*").order("created_at", desc=True).limit(5).execute().data or []
        print("data_scope_policy_rows=", len(policies))
        for row in policies:
            print(json.dumps({
                "account_id": row.get("account_id"),
                "data_scope_start_date": row.get("data_scope_start_date"),
                "data_scope_type": row.get("data_scope_type"),
                "strategy_scope": row.get("strategy_scope"),
                "lifetime_stats_available": row.get("lifetime_stats_available"),
            }, ensure_ascii=False))
    except Exception as e:
        print("policy status error:", e)

    try:
        snapshots = supabase.table("account_opening_snapshot").select("*").order("created_at", desc=True).limit(5).execute().data or []
        print("account_opening_snapshot_rows=", len(snapshots))
        for row in snapshots:
            print(json.dumps({
                "account_id": row.get("account_id"),
                "snapshot_date": row.get("snapshot_date"),
                "nav_start": row.get("nav_start"),
                "data_quality_status": row.get("data_quality_status"),
            }, ensure_ascii=False))
    except Exception as e:
        print("snapshot status error:", e)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["bootstrap", "status"])
    args = parser.parse_args()

    if args.command == "bootstrap":
        account_id = bootstrap_scope()
        fix_execution_account_id(account_id)
    elif args.command == "status":
        status()

if __name__ == "__main__":
    main()
