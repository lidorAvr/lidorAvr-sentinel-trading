import os
import json
import html
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

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

if load_dotenv:
    load_dotenv(ENV_FILE)
    load_dotenv("/app/.env")

def _env(*names):
    for name in names:
        val = os.getenv(name)
        if val:
            return val
    return None

def _supabase():
    if create_client is None:
        return None
    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    return create_client(url, key)

def _read_json(path, default):
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def _safe(v, default=""):
    if v is None:
        return default
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)

def _money(v):
    try:
        if v is None or v == "":
            return "לא ידוע"
        return f"${float(v):,.2f}"
    except Exception:
        return "לא ידוע"

def _r(v):
    try:
        if v is None or v == "":
            return "לא ידוע"
        x = float(v)
        sign = "+" if x > 0 else ""
        return f"{sign}{x:.2f}R"
    except Exception:
        return "לא ידוע"

def _pct(v):
    try:
        if v is None or v == "":
            return "לא ידוע"
        return f"{float(v):.0f}%"
    except Exception:
        return "לא ידוע"

def _html(v):
    return html.escape(_safe(v))

def _rows(table, limit=1000, order=None, desc=True):
    sb = _supabase()
    if sb is None:
        return [], "Supabase client unavailable"
    try:
        q = sb.table(table).select("*")
        if order:
            q = q.order(order, desc=desc)
        res = q.limit(limit).execute()
        return res.data or [], None
    except Exception as e:
        return [], str(e)

def _latest(table, order_candidates):
    for order in order_candidates:
        rows, err = _rows(table, limit=1, order=order, desc=True)
        if rows:
            return rows[0], None
    rows, err = _rows(table, limit=1)
    return (rows[0] if rows else None), err

def _count_by(rows, key):
    out = {}
    for r in rows:
        val = r.get(key)
        val = "לא ידוע" if val in (None, "") else str(val)
        out[val] = out.get(val, 0) + 1
    return out

def _nav_status():
    try:
        import ibkr_nav
        return ibkr_nav.nav_status()
    except Exception as e:
        return {"error": str(e)}

def collect_truth_center():
    scope_rows, scope_err = _rows("data_scope_policy", limit=5)
    opening_rows, opening_err = _rows("account_opening_snapshot", limit=5)

    audit, audit_err = _latest("data_accuracy_audit_runs", ["finished_at", "created_at", "updated_at"])
    reconciliation_rows, rec_err = _rows("broker_reconciliation_runs", limit=10, order="created_at", desc=True)
    trades_recon = None
    for r in reconciliation_rows:
        if r.get("reconciliation_type") == "trades_table_baseline" or r.get("type") == "trades_table_baseline":
            trades_recon = r
            break
    trades_recon = trades_recon or (reconciliation_rows[0] if reconciliation_rows else None)

    executions, exec_err = _rows("executions", limit=2000)
    lots, lots_err = _rows("position_lots", limit=2000)
    closures, closures_err = _rows("lot_closures", limit=2000)
    campaigns, campaigns_err = _rows("campaigns", limit=2000)
    risks, risks_err = _rows("campaign_risk_snapshots", limit=2000)
    plans, plans_err = _rows("campaign_plans", limit=500)
    tasks, tasks_err = _rows("campaign_intake_tasks", limit=500)

    plan_state = _read_json(BASE_DIR / "plan_monitor_state.json", {"sent": {}})
    intake_state = _read_json(BASE_DIR / "post_entry_intake_state.json", {"campaigns": {}})
    alert_state = _read_json(BASE_DIR / "live_alert_dedupe_state.json", {"alerts": {}})

    open_campaigns = [
        c for c in campaigns
        if str(c.get("campaign_status") or "") in ("active_managed", "runner", "partially_realized")
    ]

    approved_local = [
        {"campaign_id": cid, **rec}
        for cid, rec in (intake_state.get("campaigns") or {}).items()
        if rec.get("status") == "approved"
    ]

    approved_plans = [
        p for p in plans
        if str(p.get("plan_status") or p.get("status") or "").lower() in ("approved", "active")
    ]

    pending_tasks = [
        t for t in tasks
        if str(t.get("task_status") or t.get("status") or "pending").lower() not in ("completed", "done", "approved", "closed", "cancelled")
    ]

    errors = {
        "scope": scope_err,
        "opening": opening_err,
        "audit": audit_err,
        "reconciliation": rec_err,
        "executions": exec_err,
        "lots": lots_err,
        "closures": closures_err,
        "campaigns": campaigns_err,
        "risks": risks_err,
        "plans": plans_err,
        "tasks": tasks_err,
    }
    errors = {k: v for k, v in errors.items() if v}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "nav": _nav_status(),
        "scope": scope_rows,
        "opening": opening_rows,
        "latest_audit": audit or {},
        "latest_trades_reconciliation": trades_recon or {},
        "counts": {
            "executions": len(executions),
            "lots": len(lots),
            "closures": len(closures),
            "campaigns": len(campaigns),
            "risk_snapshots": len(risks),
            "campaign_plans": len(plans),
            "intake_tasks": len(tasks),
            "open_campaigns": len(open_campaigns),
            "approved_local_plans": len(approved_local),
            "approved_db_plans": len(approved_plans),
            "pending_intake_tasks": len(pending_tasks),
            "plan_monitor_sent_triggers": len(plan_state.get("sent", {})),
            "live_alert_dedupe_keys": len(alert_state.get("alerts", {})),
        },
        "campaign_status": _count_by(campaigns, "campaign_status"),
        "strategy_status": _count_by(campaigns, "strategy_status"),
        "campaign_quality": _count_by(campaigns, "data_quality_status"),
        "risk_quality": _count_by(risks, "risk_data_quality_status"),
        "open_campaigns": open_campaigns,
        "plans": plans,
        "pending_tasks": pending_tasks,
        "approved_local": approved_local,
        "plan_monitor_sent": plan_state.get("sent", {}),
        "errors": errors,
    }

def _kv(label, value):
    return f"<div class='kv'><span>{_html(label)}</span><strong>{_html(value)}</strong></div>"

def _pill(label, value, cls=""):
    return f"<span class='pill {cls}'>{_html(label)}: {_html(value)}</span>"

def _dict_pills(d):
    if not d:
        return "<span class='muted'>אין נתונים</span>"
    parts = []
    for k, v in sorted(d.items(), key=lambda x: str(x[0])):
        cls = ""
        if str(k) in ("verified", "strategy_verified", "passed"):
            cls = "good"
        elif str(k) in ("accounting_only", "estimated", "uncertain", "live_management_only"):
            cls = "warn"
        elif str(k) in ("broken", "data_error"):
            cls = "bad"
        parts.append(_pill(k, v, cls))
    return " ".join(parts)

def render_truth_center_html(data=None):
    data = data or collect_truth_center()
    nav = data.get("nav") or {}
    audit = data.get("latest_audit") or {}
    rec = data.get("latest_trades_reconciliation") or {}
    scope = (data.get("scope") or [{}])[0] if data.get("scope") else {}

    counts = data.get("counts") or {}
    open_campaigns = data.get("open_campaigns") or []
    pending_tasks = data.get("pending_tasks") or []
    errors = data.get("errors") or {}

    open_rows = []
    for c in open_campaigns:
        open_rows.append(
            "<tr>"
            f"<td>{_html(c.get('symbol'))}</td>"
            f"<td>{_html(c.get('campaign_id'))}</td>"
            f"<td>{_html(c.get('campaign_status'))}</td>"
            f"<td>{_html(c.get('strategy_status'))}</td>"
            f"<td>{_html(c.get('data_quality_status'))}</td>"
            f"<td>{_money(c.get('realized_pnl_usd') or c.get('net_realized_pnl_usd'))}</td>"
            "</tr>"
        )

    task_rows = []
    for t in pending_tasks:
        task_rows.append(
            "<tr>"
            f"<td>{_html(t.get('symbol'))}</td>"
            f"<td>{_html(t.get('campaign_id'))}</td>"
            f"<td>{_html(t.get('task_step') or t.get('step'))}</td>"
            f"<td>{_html(t.get('task_status') or t.get('status'))}</td>"
            "</tr>"
        )

    alert_rows = []
    for key, rec_item in list((data.get("plan_monitor_sent") or {}).items())[:50]:
        alert_rows.append(
            "<tr>"
            f"<td>{_html(key)}</td>"
            f"<td>{_html(rec_item.get('sent_at'))}</td>"
            "</tr>"
        )

    error_html = ""
    if errors:
        error_html = "<section class='band danger'><h2>בעיות טעינה</h2>" + "".join(
            f"<p><b>{_html(k)}</b>: {_html(v)}</p>" for k, v in errors.items()
        ) + "</section>"

    html_doc = f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sentinel Truth Center</title>
<style>
:root {{
  --bg: #f7f8fa;
  --text: #17212b;
  --muted: #637083;
  --line: #dde3ea;
  --good: #0f766e;
  --warn: #a16207;
  --bad: #b91c1c;
  --surface: #ffffff;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.45;
}}
header {{
  padding: 22px 24px 12px;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
}}
h1 {{ margin: 0 0 6px; font-size: 26px; }}
h2 {{ margin: 0 0 12px; font-size: 18px; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 18px; }}
.band {{
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 16px;
  margin: 0 0 14px;
}}
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 10px;
}}
.kv {{
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
  min-height: 64px;
}}
.kv span {{ display: block; color: var(--muted); font-size: 13px; }}
.kv strong {{ display: block; margin-top: 4px; font-size: 18px; }}
.pills {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.pill {{
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 5px 9px;
  background: #f9fafb;
  font-size: 13px;
}}
.pill.good {{ color: var(--good); border-color: #99f6e4; background: #f0fdfa; }}
.pill.warn {{ color: var(--warn); border-color: #fde68a; background: #fffbeb; }}
.pill.bad {{ color: var(--bad); border-color: #fecaca; background: #fef2f2; }}
.muted {{ color: var(--muted); }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th, td {{ border-bottom: 1px solid var(--line); padding: 8px 6px; text-align: right; vertical-align: top; }}
th {{ color: var(--muted); font-weight: 650; }}
.danger {{ border-color: #fecaca; background: #fff7f7; }}
@media (max-width: 680px) {{
  header {{ padding: 16px; }}
  main {{ padding: 10px; }}
  h1 {{ font-size: 22px; }}
  .kv strong {{ font-size: 16px; }}
  table {{ font-size: 12px; }}
}}
</style>
</head>
<body>
<header>
  <h1>Sentinel Truth Center</h1>
  <div class="muted">מרכז אמת חשבונאית, סטטוס קמפיינים, תוכניות והתראות. נבנה לקריאה בלבד.</div>
</header>
<main>
  {error_html}

  <section class="band">
    <h2>Scope & NAV</h2>
    <div class="grid">
      {_kv("Data Scope", scope.get("data_scope_type") or "YTD")}
      {_kv("Strategy Scope", scope.get("strategy_scope") or scope.get("official_performance_scope") or "YTD_VERIFIED_CAMPAIGNS_ONLY")}
      {_kv("Lifetime Stats", "זמין" if scope.get("lifetime_stats_available") else "לא זמין")}
      {_kv("IBKR NAV", _money(nav.get("current_nav")))}
      {_kv("NAV Source", nav.get("status") or nav.get("source") or "לא ידוע")}
      {_kv("Generated", data.get("generated_at"))}
    </div>
  </section>

  <section class="band">
    <h2>Accounting Truth</h2>
    <div class="grid">
      {_kv("Executions", counts.get("executions"))}
      {_kv("Lots", counts.get("lots"))}
      {_kv("Closures", counts.get("closures"))}
      {_kv("Campaigns", counts.get("campaigns"))}
      {_kv("Open Campaigns", counts.get("open_campaigns"))}
      {_kv("Risk Snapshots", counts.get("risk_snapshots"))}
    </div>
  </section>

  <section class="band">
    <h2>Audit & Reconciliation</h2>
    <div class="grid">
      {_kv("Latest Audit", audit.get("status") or "לא ידוע")}
      {_kv("Audit Quality", audit.get("data_quality_status") or "לא ידוע")}
      {_kv("Critical Breaks", audit.get("critical_breaks") or 0)}
      {_kv("Warnings", audit.get("warning_breaks") or 0)}
      {_kv("Trades Reconciliation", rec.get("status") or "לא ידוע")}
      {_kv("Reconciliation Quality", rec.get("data_quality_status") or rec.get("quality") or "לא ידוע")}
    </div>
  </section>

  <section class="band">
    <h2>Campaign Classification</h2>
    <div class="pills">{_dict_pills(data.get("campaign_status"))}</div>
    <br>
    <div class="pills">{_dict_pills(data.get("strategy_status"))}</div>
    <br>
    <div class="pills">{_dict_pills(data.get("campaign_quality"))}</div>
  </section>

  <section class="band">
    <h2>Plans & Alerts</h2>
    <div class="grid">
      {_kv("Campaign Plans", counts.get("campaign_plans"))}
      {_kv("Approved Plans", counts.get("approved_local_plans") or counts.get("approved_db_plans"))}
      {_kv("Pending Intake", counts.get("pending_intake_tasks"))}
      {_kv("Plan Monitor Sent Triggers", counts.get("plan_monitor_sent_triggers"))}
      {_kv("Live Alert Dedupe Keys", counts.get("live_alert_dedupe_keys"))}
    </div>
  </section>

  <section class="band">
    <h2>Open Campaigns</h2>
    <table>
      <thead><tr><th>סימול</th><th>קמפיין</th><th>סטטוס</th><th>Strategy</th><th>Quality</th><th>Realized PnL</th></tr></thead>
      <tbody>{''.join(open_rows) if open_rows else '<tr><td colspan="6" class="muted">אין קמפיינים פתוחים</td></tr>'}</tbody>
    </table>
  </section>

  <section class="band">
    <h2>Pending Intake Tasks</h2>
    <table>
      <thead><tr><th>סימול</th><th>קמפיין</th><th>שלב</th><th>סטטוס</th></tr></thead>
      <tbody>{''.join(task_rows) if task_rows else '<tr><td colspan="4" class="muted">אין משימות Intake פתוחות</td></tr>'}</tbody>
    </table>
  </section>

  <section class="band">
    <h2>Plan Monitor Sent</h2>
    <table>
      <thead><tr><th>Trigger Key</th><th>Sent At</th></tr></thead>
      <tbody>{''.join(alert_rows) if alert_rows else '<tr><td colspan="2" class="muted">אין התראות שנשלחו</td></tr>'}</tbody>
    </table>
  </section>
</main>
</body>
</html>"""
    return html_doc

def as_json():
    return collect_truth_center()

def register_routes(app_like):
    try:
        target = getattr(app_like, "server", app_like)
        if not hasattr(target, "route"):
            print("TruthCenter: dashboard object has no route()")
            return False

        endpoint_names = set(getattr(target, "view_functions", {}).keys())
        if "sentinel_truth_center_page" in endpoint_names:
            return True

        @target.route("/truth", endpoint="sentinel_truth_center_page")
        def sentinel_truth_center_page():
            try:
                from flask import Response
                return Response(render_truth_center_html(), mimetype="text/html; charset=utf-8")
            except Exception:
                return render_truth_center_html()

        @target.route("/api/truth", endpoint="sentinel_truth_center_api")
        def sentinel_truth_center_api():
            try:
                from flask import jsonify
                return jsonify(as_json())
            except Exception:
                return json.dumps(as_json(), ensure_ascii=False, default=str)

        print("TruthCenter: registered /truth and /api/truth")
        return True
    except Exception as e:
        print(f"TruthCenter warning: register failed: {e}")
        return False

if __name__ == "__main__":
    data = collect_truth_center()
    print(json.dumps({
        "counts": data.get("counts"),
        "campaign_status": data.get("campaign_status"),
        "strategy_status": data.get("strategy_status"),
        "errors": data.get("errors"),
    }, ensure_ascii=False, indent=2, default=str))


# --- Fast dashboard compatibility enrichments ---

def _deep_find_number(obj, names):
    targets = {str(n).lower() for n in names}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in targets:
                try:
                    if v not in (None, "", []):
                        return float(v)
                except Exception:
                    pass
        for v in obj.values():
            found = _deep_find_number(v, names)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _deep_find_number(v, names)
            if found is not None:
                return found
    return None

def _nav_status_from_config():
    cfg = _read_json(BASE_DIR / "sentinel_config.json", {})
    status = cfg.get("ibkr_nav_status")
    if isinstance(status, dict) and status.get("current_nav") not in (None, ""):
        return status

    nav = _deep_find_number(cfg, [
        "current_nav",
        "live_ibkr_nav",
        "ibkr_nav",
        "broker_nav",
        "account_nav",
        "endingValue",
    ])

    if nav is not None:
        return {
            "current_nav": nav,
            "status": "config_fallback",
            "source": "sentinel_config.json",
            "error": None,
        }

    return {
        "current_nav": None,
        "status": None,
        "source": None,
        "error": None,
    }

def _nav_status():
    try:
        import ibkr_nav
        st = ibkr_nav.nav_status()
        if isinstance(st, dict) and st.get("current_nav") not in (None, ""):
            return st
    except Exception:
        pass
    return _nav_status_from_config()

def _count_by_any(rows, keys):
    out = {}
    for r in rows:
        val = None
        for key in keys:
            if r.get(key) not in (None, ""):
                val = r.get(key)
                break
        val = "לא ידוע" if val in (None, "") else str(val)
        out[val] = out.get(val, 0) + 1
    return out

_truth_center_collect_base = collect_truth_center

def collect_truth_center():
    data = _truth_center_collect_base()

    risks, _ = _rows("campaign_risk_snapshots", limit=2000)
    data["risk_quality"] = _count_by_any(risks, ["risk_data_quality_status", "data_quality_status", "quality"])

    nav = data.get("nav") or {}
    if nav.get("current_nav") in (None, ""):
        data["nav"] = _nav_status()

    return data
