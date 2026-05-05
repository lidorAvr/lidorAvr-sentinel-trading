import os
import json
import argparse
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone
from uuid import uuid4

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

UNKNOWN_SETUPS = {"", "UNKNOWN", "SKIPPED", "NONE", "NULL", "N/A"}

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

def _clean_setup(v):
    s = (_s(v) or "").strip()
    if s.upper() in UNKNOWN_SETUPS:
        return None
    return s

def _derive_setup(campaign, executions):
    existing = _clean_setup(campaign.get("setup_type"))
    if existing:
        return existing, "campaigns.setup_type"

    buy_setups = []
    all_setups = []

    for e in executions:
        raw = _raw(e)
        setup = _clean_setup(raw.get("setup_type"))
        if not setup:
            continue

        all_setups.append(setup)
        if (_s(e.get("side")) or "").upper() == "BUY":
            buy_setups.append(setup)

    if buy_setups:
        return Counter(buy_setups).most_common(1)[0][0], "executions.raw_payload.buy.setup_type"

    if all_setups:
        return Counter(all_setups).most_common(1)[0][0], "executions.raw_payload.setup_type"

    return None, None

def _derive_decision_source(setup_type, executions):
    values = []
    for e in executions:
        raw = _raw(e)
        tag = (_s(raw.get("strategy_tag")) or "").lower()
        if tag:
            values.append(tag)

    blob = " ".join(values + [setup_type or ""]).lower()

    if "algo" in blob:
        return "algo"
    if "hybrid" in blob:
        return "hybrid"
    return "manual"

def _derive_sample_bucket(decision_source, setup_type):
    if decision_source == "algo":
        return f"ALGO:{setup_type or 'Unknown'}"
    if decision_source == "hybrid":
        return f"HYBRID:{setup_type or 'Unknown'}"
    return f"MANUAL:{setup_type or 'Unknown'}"

def _eligible_closed_strategy(campaign, setup_type):
    has_open = bool(campaign.get("has_open_position"))
    missing_stop_lots = int(_f(campaign.get("missing_stop_lots"), 0))
    legacy_lots = int(_f(campaign.get("legacy_lots"), 0))
    lots_count = int(_f(campaign.get("lots_count"), 0))
    closures_count = int(_f(campaign.get("closures_count"), 0))
    quantity_remaining = _f(campaign.get("quantity_remaining"), 0)
    campaign_status = _s(campaign.get("campaign_status"))

    if has_open or quantity_remaining > 0:
        if missing_stop_lots > 0:
            return "live_management_only", False, "Open campaign has missing initial stop; manage live, exclude from official stats."
        if not setup_type:
            return "live_management_only", False, "Open campaign has no setup classification yet."
        return "live_management_only", False, "Open campaign is managed live; official strategy stats wait for full closure."

    if campaign_status not in ["closed_pending_review", "closed_reviewed"]:
        return "excluded_from_strategy_stats", False, f"Campaign status {campaign_status} is not a closed strategy sample."

    if legacy_lots > 0:
        return "accounting_only", False, "Legacy/carry-in lots exist; accounting valid but strategy lifecycle is incomplete."

    if lots_count <= 0 or closures_count <= 0:
        return "excluded_from_strategy_stats", False, "Missing lots or closures."

    if missing_stop_lots > 0:
        return "accounting_only", False, f"{missing_stop_lots} lot(s) missing verified initial stop; actual R is not verified."

    if not setup_type:
        return "unclassified", False, "Setup is missing; cannot include in setup-level strategy statistics."

    return "strategy_verified", True, "Closed campaign has setup, lots, closures and verified initial stop."

def run(dry_run=False):
    campaigns = _fetch_all("campaigns")
    executions = _fetch_all("executions")

    execs_by_campaign = defaultdict(list)
    for e in executions:
        cid = _s(e.get("campaign_id")) or f"UNCLASSIFIED_{e.get('symbol')}"
        execs_by_campaign[cid].append(e)

    updates = []
    counts = Counter()
    warnings = 0

    for c in campaigns:
        cid = c.get("campaign_id")
        exs = execs_by_campaign.get(cid, [])

        setup_type, setup_source = _derive_setup(c, exs)
        decision_source = _derive_decision_source(setup_type, exs)
        strategy_status, eligible, reason = _eligible_closed_strategy(c, setup_type)

        if strategy_status != "strategy_verified":
            warnings += 1

        data_quality = "verified" if strategy_status == "strategy_verified" else (
            "estimated" if strategy_status in ["accounting_only", "live_management_only"] else "uncertain"
        )

        verified_scope = "YTD_VERIFIED_CAMPAIGNS_ONLY" if eligible else None
        sample_bucket = _derive_sample_bucket(decision_source, setup_type)

        audit_flags = c.get("audit_flags") or []
        if isinstance(audit_flags, str):
            try:
                audit_flags = json.loads(audit_flags)
            except Exception:
                audit_flags = []

        if strategy_status not in audit_flags:
            audit_flags.append(strategy_status)

        update = {
            "campaign_id": cid,
            "setup_type": setup_type,
            "setup_source": setup_source,
            "decision_source": decision_source,
            "strategy_status": strategy_status,
            "strategy_eligible": eligible,
            "strategy_exclusion_reason": reason if not eligible else None,
            "data_quality_status": data_quality,
            "verified_scope": verified_scope,
            "sample_bucket": sample_bucket,
            "audit_flags": audit_flags,
            "eligibility_reason": reason,
            "eligibility_version": "strategy_eligibility_v1",
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        updates.append(update)
        counts[strategy_status] += 1

    if dry_run:
        print("dry_run_campaigns_seen=", len(campaigns))
        for u in updates[:12]:
            print(json.dumps({
                "campaign_id": u["campaign_id"],
                "setup": u["setup_type"],
                "source": u["setup_source"],
                "decision_source": u["decision_source"],
                "strategy_status": u["strategy_status"],
                "eligible": u["strategy_eligible"],
                "reason": u["eligibility_reason"],
            }, ensure_ascii=False))
        print("dry_run_counts=", dict(counts))
        return

    for update in updates:
        cid = update.get("campaign_id")
        payload = dict(update)
        payload.pop("campaign_id", None)

        supabase.table("campaigns").update(payload).eq("campaign_id", cid).execute()

    run_id = str(uuid4())
    supabase.table("strategy_eligibility_runs").insert({
        "run_id": run_id,
        "run_version": "strategy_eligibility_v1",
        "campaigns_seen": len(campaigns),
        "strategy_verified": counts.get("strategy_verified", 0),
        "accounting_only": counts.get("accounting_only", 0),
        "live_management_only": counts.get("live_management_only", 0),
        "unclassified": counts.get("unclassified", 0),
        "excluded_from_strategy_stats": counts.get("excluded_from_strategy_stats", 0),
        "data_quality_warnings": warnings,
        "payload": {"counts": dict(counts)},
    }).execute()

    for u in updates:
        if not u["strategy_eligible"]:
            _audit(
                "strategy_eligibility_exclusion",
                "info",
                u["eligibility_reason"],
                {
                    "strategy_status": u["strategy_status"],
                    "setup_type": u["setup_type"],
                    "decision_source": u["decision_source"],
                    "sample_bucket": u["sample_bucket"],
                },
                campaign_id=u["campaign_id"],
            )

    print("strategy_eligibility_run_id=", run_id)
    print("campaigns_seen=", len(campaigns))
    print("counts=", dict(counts))

def status():
    rows = _fetch_all("campaigns")
    print("campaigns=", len(rows))

    by_strategy = Counter(r.get("strategy_status") for r in rows)
    by_bucket = Counter(r.get("sample_bucket") for r in rows)
    eligible = [r for r in rows if r.get("strategy_eligible")]
    open_rows = [r for r in rows if r.get("has_open_position")]

    print("by_strategy_status=")
    for k, v in sorted(by_strategy.items(), key=lambda x: str(x[0])):
        print(f"  {k}: {v}")

    print("strategy_eligible=", len(eligible))

    print("by_sample_bucket=")
    for k, v in sorted(by_bucket.items(), key=lambda x: str(x[0])):
        print(f"  {k}: {v}")

    print("open_campaigns=")
    for r in sorted(open_rows, key=lambda x: x.get("symbol") or ""):
        print(
            f"  {r.get('symbol')} | {r.get('campaign_id')} | "
            f"setup={r.get('setup_type')} | strategy={r.get('strategy_status')} | "
            f"eligible={r.get('strategy_eligible')} | reason={r.get('strategy_exclusion_reason')}"
        )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["dry-run", "run", "status"])
    args = parser.parse_args()

    if args.command == "dry-run":
        run(dry_run=True)
    elif args.command == "run":
        run(dry_run=False)
    elif args.command == "status":
        status()

if __name__ == "__main__":
    main()
