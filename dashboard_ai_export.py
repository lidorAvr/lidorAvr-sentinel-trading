import os
import json
import math
from pathlib import Path
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

try:
    from supabase import create_client
except Exception:
    create_client = None

import dashboard_truth_center as truth

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

if load_dotenv:
    load_dotenv(ENV_FILE)
    load_dotenv("/app/.env")

def _load_env(path):
    try:
        p = Path(path)
        if not p.exists():
            return
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass

_load_env(ENV_FILE)
_load_env("/app/.env")

HE = {
    None: "לא ידוע",
    "": "לא ידוע",
    "passed": "תקין",
    "failed": "נכשל",
    "verified": "מאומת",
    "estimated": "מוערך",
    "uncertain": "לא ודאי",
    "runner": "ראנר",
    "active_managed": "פתוח ומנוהל",
    "closed_pending_review": "נסגר - ממתין סקירה",
    "strategy_verified": "מאומת לסטטיסטיקה",
    "accounting_only": "חשבונאי בלבד",
    "live_management_only": "ניהול חי בלבד",
    "approved": "מאושר",
    "pending_review": "ממתין אישור",
}

def he(v):
    return HE.get(v, HE.get(str(v), str(v) if v not in (None, "") else "לא ידוע"))

def _env(*names):
    for name in names:
        val = os.getenv(name)
        if val:
            return val
    return None

def _num(v):
    try:
        if v in (None, ""):
            return None
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None

def money(v):
    x = _num(v)
    return "לא ידוע" if x is None else f"${x:,.2f}"

def rfmt(v):
    x = _num(v)
    if x is None:
        return "לא ידוע"
    return f"{x:+.2f}R" if x else "0.00R"

def pct(v):
    x = _num(v)
    return "לא ידוע" if x is None else f"{x:.0%}"

def short_date(v):
    s = str(v or "")
    if "T" in s:
        return s.split("T", 1)[0]
    return s[:10] if len(s) >= 10 else s

def _client():
    if create_client is None:
        return None
    url = _env("SUPABASE_URL", "SUPABASE_PROJECT_URL")
    key = _env("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY", "SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    return create_client(url, key)

def _fetch(sb, table, limit=1000):
    if sb is None:
        return []
    try:
        res = sb.table(table).select("*").limit(limit).execute()
        return res.data or []
    except Exception:
        return []

def get_truth():
    try:
        return truth.get_truth_center()
    except Exception as exc:
        return {"errors": {"truth_center": str(exc)}, "counts": {}, "open_campaigns": []}

def _date_key(row):
    for key in ("closed_at", "closed_date", "finished_at", "opened_at", "opened_date", "executed_at", "trade_date", "created_at"):
        val = row.get(key)
        if val:
            return str(val)
    return ""

def _cid(row):
    return row.get("campaign_id") or row.get("campaign") or row.get("trade_campaign_id") or ""

def _symbol(row):
    return row.get("symbol") or row.get("ticker") or "?"

def _side(row):
    raw = str(row.get("side") or row.get("action") or row.get("type") or "").upper()
    if "BUY" in raw or raw in ("B", "BOT"):
        return "קנייה"
    if "SELL" in raw or raw in ("S", "SLD"):
        return "מכירה"
    return raw or "פעולה"

def _qty(row):
    for key in ("quantity", "qty", "shares", "filled_quantity"):
        x = _num(row.get(key))
        if x is not None:
            return f"{x:g}"
    return "?"

def _price(row):
    for key in ("price", "execution_price", "fill_price", "avg_price"):
        x = _num(row.get(key))
        if x is not None:
            return money(x)
    return "לא ידוע"

def load_export_data():
    sb = _client()
    data = {
        "truth": get_truth(),
        "campaigns": _fetch(sb, "campaigns", 1000),
        "executions": _fetch(sb, "executions", 2000),
        "plans": _fetch(sb, "campaign_plans", 500),
        "risk_snapshots": _fetch(sb, "risk_snapshots", 1000),
    }
    if not data["plans"]:
        data["plans"] = data["truth"].get("plans") or []
    return data

def recent_campaigns(limit=25):
    data = load_export_data()
    campaigns = data["campaigns"] or data["truth"].get("open_campaigns") or []
    executions = data["executions"] or []

    ex_by_cid = {}
    for e in executions:
        cid = _cid(e)
        if cid:
            ex_by_cid.setdefault(cid, []).append(e)

    campaigns = sorted(campaigns, key=_date_key, reverse=True)
    out = []
    for c in campaigns[:limit]:
        cid = _cid(c)
        ex = sorted(ex_by_cid.get(cid, []), key=_date_key)
        out.append({"campaign": c, "executions": ex})
    return out

def build_master_context_report():
    data = load_export_data()
    t = data["truth"]
    counts = t.get("counts") or {}
    nav = t.get("nav") or {}
    audit = t.get("latest_audit") or {}
    recon = t.get("latest_trades_reconciliation") or {}
    open_campaigns = t.get("open_campaigns") or []
    campaigns = sorted(data["campaigns"] or [], key=_date_key, reverse=True)
    executions = sorted(data["executions"] or [], key=_date_key, reverse=True)
    plans = data["plans"] or []

    lines = []
    lines.append("# Sentinel AI - דוח הקשר מלא")
    lines.append("")
    lines.append(f"נוצר: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append("## 1. תמונת מצב מהירה")
    lines.append(f"- שווי תיק IBKR: {money(nav.get('current_nav'))} | מקור: {he(nav.get('status'))}")
    lines.append(f"- טווח נתונים: YTD בלבד, החל מ־2026-01-01")
    lines.append(f"- סטטיסטיקה רשמית: קמפיינים מאומתים בלבד, לא All-Time")
    lines.append(f"- ביקורת נתונים: {he(audit.get('status'))} | איכות: {he(audit.get('data_quality_status'))} | כשלים קריטיים: {audit.get('critical_breaks', 0)} | אזהרות: {audit.get('warning_breaks', 0)}")
    lines.append(f"- התאמת Trades: {he(recon.get('status'))} | איכות: {he(recon.get('data_quality_status'))}")
    lines.append(f"- Executions: {counts.get('executions', 0)} | Lots: {counts.get('lots', 0)} | Campaigns: {counts.get('campaigns', 0)} | Open: {counts.get('open_campaigns', 0)}")
    lines.append("")

    lines.append("## 2. קמפיינים פתוחים")
    if not open_campaigns:
        lines.append("- אין קמפיינים פתוחים.")
    for c in open_campaigns:
        lines.append(
            f"- {_symbol(c)} [{c.get('setup_type') or 'לא ידוע'}]: "
            f"{he(c.get('campaign_status'))} | כמות: {c.get('quantity_remaining', 'לא ידוע')} | "
            f"סיכון איכות: {he(c.get('risk_data_quality_status'))} | "
            f"רווח ממומש: {money(c.get('realized_pnl_usd'))} | "
            f"Closed Target R: {rfmt(c.get('closed_target_r'))} | "
            f"Closed Actual R: {rfmt(c.get('closed_actual_r'))} | "
            f"Locked Profit: {money(c.get('locked_profit_usd'))} | "
            f"Giveback to Stop: {money(c.get('giveback_to_stop_usd'))}"
        )
    lines.append("")

    lines.append("## 3. תוכניות ניהול מאושרות")
    approved = [p for p in plans if str(p.get("plan_status")) == "approved"]
    if not approved:
        lines.append("- אין תוכניות מאושרות.")
    for p in approved:
        lines.append(
            f"- {_symbol(p)} | קמפיין: {_cid(p)} | Setup: {p.get('setup_type') or 'לא ידוע'} | "
            f"סטופ: {money(p.get('current_stop') or p.get('initial_stop'))} | "
            f"סיכון בפועל: {money(p.get('actual_initial_risk_usd'))} מול יעד {money(p.get('target_risk_usd'))} | "
            f"ביטחון תוכנית: {p.get('confidence_score', 'לא ידוע')}%"
        )
    lines.append("")

    lines.append("## 4. יומן קמפיינים אחרונים")
    ex_by_cid = {}
    for e in executions:
        cid = _cid(e)
        if cid:
            ex_by_cid.setdefault(cid, []).append(e)

    for c in campaigns[:35]:
        cid = _cid(c)
        pnl = c.get("realized_pnl_usd") or c.get("net_pnl") or c.get("pnl")
        r = c.get("closed_actual_r")
        if r in (None, ""):
            r = c.get("closed_target_r") or c.get("total_campaign_r")
        lines.append("")
        lines.append(f"### {_symbol(c)} | {he(c.get('campaign_status') or c.get('status'))} | {money(pnl)} | {rfmt(r)}")
        lines.append(f"- קמפיין: {cid}")
        lines.append(f"- Setup: {c.get('setup_type') or c.get('strategy') or 'לא ידוע'}")
        lines.append(f"- איכות נתונים: {he(c.get('data_quality_status'))} | סטטוס אסטרטגי: {he(c.get('strategy_status'))}")
        notes = c.get("management_notes") or c.get("notes") or c.get("review_notes") or c.get("post_trade_notes")
        if notes:
            lines.append(f"- הערות ניהול: {str(notes).strip()}")
        evs = sorted(ex_by_cid.get(cid, []), key=_date_key)
        if evs:
            lines.append("- פעולות:")
            for e in evs[:12]:
                pnl_e = e.get("realized_pnl") or e.get("realized_pnl_usd") or e.get("pnl")
                tail = f" | PnL: {money(pnl_e)}" if _num(pnl_e) is not None else ""
                lines.append(f"  * {short_date(_date_key(e))}: {_side(e)} {_qty(e)} @ {_price(e)}{tail}")

    lines.append("")
    lines.append("## 5. גבולות שימוש")
    lines.append("- נתוני YTD מספיקים לניהול יומי, בקרת סיכון ולמידה, אבל לא לקביעה מלאה על איכות הסוחר לאורך כל השנים.")
    lines.append("- קמפיינים פתוחים אינם נכנסים לסטטיסטיקת שיטה רשמית עד סגירה מלאה.")
    lines.append("- יש להפריד בין Target R להשפעת תיק לבין Actual R לאיכות הטרייד.")
    lines.append("")

    appendix = {
        "truth_summary": {
            "counts": counts,
            "campaign_status": t.get("campaign_status"),
            "strategy_status": t.get("strategy_status"),
            "campaign_quality": t.get("campaign_quality"),
            "risk_quality": t.get("risk_quality"),
            "audit": audit,
            "trades_reconciliation": recon,
        },
        "open_campaigns": open_campaigns,
        "approved_plans": approved,
        "recent_campaigns": campaigns[:80],
        "recent_executions": executions[:300],
    }
    lines.append("## 6. נספח נתונים מלא למודל")
    lines.append("```json")
    lines.append(json.dumps(appendix, ensure_ascii=False, default=str, indent=2))
    lines.append("```")
    return "\n".join(lines)
# --- Sprint Dashboard: resilient truth center fallback ---

# --- Sprint Dashboard: resilient truth center fallback ---

def _call_existing_truth_center():
    import inspect
    preferred = [
        "get_truth_center",
        "get_truth_center_data",
        "get_dashboard_truth_center",
        "build_truth_center",
        "build_truth_center_data",
        "collect_truth_center",
        "load_truth_center",
        "fetch_truth_center",
        "truth_center_data",
    ]
    for name in preferred:
        fn = getattr(truth, name, None)
        if callable(fn):
            try:
                data = fn()
                if isinstance(data, dict):
                    return data
            except TypeError:
                continue
            except Exception:
                continue

    for name, fn in inspect.getmembers(truth, inspect.isfunction):
        if name.startswith("_") or "render" in name or "route" in name:
            continue
        try:
            data = fn()
        except TypeError:
            continue
        except Exception:
            continue
        if isinstance(data, dict) and any(k in data for k in ("counts", "open_campaigns", "latest_audit", "nav")):
            return data
    return None

def _safe_table(sb, table, limit=1000):
    try:
        if sb is None:
            return []
        return sb.table(table).select("*").limit(limit).execute().data or []
    except Exception:
        return []

def _latest_row(rows, *date_keys):
    if not rows:
        return {}
    keys = date_keys or ("created_at", "updated_at", "finished_at", "calculated_at")
    def k(row):
        for key in keys:
            if row.get(key):
                return str(row.get(key))
        return ""
    return sorted(rows, key=k, reverse=True)[0]

def _fallback_nav():
    try:
        import ibkr_nav
        for name in ("get_nav_snapshot", "get_nav_status", "load_nav_snapshot", "get_nav"):
            fn = getattr(ibkr_nav, name, None)
            if callable(fn):
                try:
                    data = fn()
                    if isinstance(data, dict):
                        if "current_nav" not in data:
                            for key in ("nav", "net_liquidation", "net_liquidation_value"):
                                if key in data:
                                    data["current_nav"] = data.get(key)
                                    break
                        return data
                except Exception:
                    pass
    except Exception:
        pass

    try:
        cfg = _read_json(BASE_DIR / "sentinel_config.json", {})
        for key in ("live_ibkr_nav", "current_nav", "broker_nav", "nav"):
            if cfg.get(key) is not None:
                return {"current_nav": cfg.get(key), "status": "config_fallback", "source": "sentinel_config.json"}
    except Exception:
        pass

    return {"current_nav": None, "status": None, "source": None, "error": None}

def _fallback_truth_from_tables():
    sb = _client()

    executions = _safe_table(sb, "executions", 3000)
    lots = _safe_table(sb, "lots", 3000)
    closures = _safe_table(sb, "closures", 3000)
    campaigns = _safe_table(sb, "campaigns", 1500)
    risk_snapshots = _safe_table(sb, "risk_snapshots", 1500)
    plans = _safe_table(sb, "campaign_plans", 1000)
    tasks = _safe_table(sb, "campaign_intake_tasks", 1000)
    audits = _safe_table(sb, "data_accuracy_audit_runs", 50) or _safe_table(sb, "audit_runs", 50)
    recons = _safe_table(sb, "broker_reconciliation_runs", 50) or _safe_table(sb, "reconciliation_runs", 50)

    risk_by_cid = {}
    for r in risk_snapshots:
        cid = r.get("campaign_id")
        if cid:
            risk_by_cid[cid] = r

    open_campaigns = []
    for c in campaigns:
        status = c.get("campaign_status") or c.get("status")
        is_open = c.get("has_open_position") is True or status in ("runner", "active_managed", "open")
        qty = _num(c.get("quantity_remaining"))
        if qty is not None and qty > 0:
            is_open = True
        if not is_open:
            continue
        row = dict(c)
        r = risk_by_cid.get(c.get("campaign_id")) or {}
        for key in (
            "target_risk_usd",
            "actual_initial_risk_usd",
            "peak_campaign_risk_usd",
            "current_risk_to_stop_usd",
            "giveback_to_stop_usd",
            "locked_profit_usd",
            "closed_target_r",
            "closed_actual_r",
            "risk_data_quality_status",
            "risk_flags",
        ):
            if row.get(key) in (None, "") and r.get(key) not in (None, ""):
                row[key] = r.get(key)
        open_campaigns.append(row)

    def counts_by(rows, key, fallback="לא ידוע"):
        out = {}
        for row in rows:
            val = row.get(key) or fallback
            out[val] = out.get(val, 0) + 1
        return out

    approved_local = _read_json(BASE_DIR / "post_entry_intake_state.json", {"campaigns": {}}).get("campaigns") or {}
    sent = _read_json(BASE_DIR / "plan_monitor_state.json", {"sent": {}}).get("sent") or {}

    approved_db = [p for p in plans if str(p.get("plan_status")) == "approved"]
    pending_tasks = [t for t in tasks if str(t.get("status") or t.get("task_status") or "pending") not in ("done", "approved", "skipped", "closed")]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "nav": _fallback_nav(),
        "latest_audit": _latest_row(audits, "finished_at", "created_at"),
        "latest_trades_reconciliation": _latest_row(recons, "finished_at", "created_at"),
        "counts": {
            "executions": len(executions),
            "lots": len(lots),
            "closures": len(closures),
            "campaigns": len(campaigns),
            "risk_snapshots": len(risk_snapshots),
            "campaign_plans": len(plans),
            "intake_tasks": len(tasks),
            "open_campaigns": len(open_campaigns),
            "approved_local_plans": len([v for v in approved_local.values() if isinstance(v, dict) and v.get("status") == "approved"]),
            "approved_db_plans": len(approved_db),
            "pending_intake_tasks": len(pending_tasks),
            "plan_monitor_sent_triggers": len(sent),
            "live_alert_dedupe_keys": len((_read_json(BASE_DIR / "live_alert_dedupe_state.json", {"keys": {}}).get("keys") or {})),
        },
        "campaign_status": counts_by(campaigns, "campaign_status"),
        "strategy_status": counts_by(campaigns, "strategy_status"),
        "campaign_quality": counts_by(campaigns, "data_quality_status"),
        "risk_quality": counts_by(risk_snapshots, "risk_data_quality_status"),
        "open_campaigns": open_campaigns,
        "plans": plans,
        "pending_tasks": pending_tasks,
        "approved_local": [dict(v, campaign_id=k) for k, v in approved_local.items() if isinstance(v, dict)],
        "plan_monitor_sent": sent,
        "errors": {},
    }

def get_truth():
    data = _call_existing_truth_center()
    if not isinstance(data, dict) or not data.get("counts"):
        data = _fallback_truth_from_tables()

    if not isinstance(data, dict):
        data = {}

    data.setdefault("counts", {})
    data.setdefault("open_campaigns", [])
    data.setdefault("plans", [])
    data.setdefault("pending_tasks", [])
    data.setdefault("latest_audit", {})
    data.setdefault("latest_trades_reconciliation", {})
    data.setdefault("nav", _fallback_nav())
    data.setdefault("errors", {})
    return data

