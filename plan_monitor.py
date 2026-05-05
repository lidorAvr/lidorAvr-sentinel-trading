import os, json, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "plan_monitor_state.json"
CONFIG_FILE = BASE_DIR / "sentinel_config.json"
ENV_FILE = BASE_DIR / ".env"

RTL = "\u200f"
SEP = "━━━━━━━━━━━━"

if load_dotenv:
    load_dotenv(ENV_FILE)
    load_dotenv("/app/.env")

def _now():
    return datetime.now(timezone.utc).isoformat()

def _read_json(path, default):
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def _write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _env(*names):
    for name in names:
        val = os.getenv(name)
        if val:
            return val
    return None

def _config_value(*names):
    cfg = _read_json(CONFIG_FILE, {})
    for name in names:
        if cfg.get(name):
            return cfg.get(name)
    tg = cfg.get("telegram") or {}
    for name in names:
        if tg.get(name):
            return tg.get(name)
    return None

def _supabase():
    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError("Missing Supabase env")
    return create_client(url, key)

def _bot_token():
    return _env("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN", "BOT_TOKEN") or _config_value("telegram_token", "bot_token")

def _chat_id():
    return _env("TELEGRAM_CHAT_ID", "CHAT_ID", "ADMIN_CHAT_ID") or _config_value("telegram_chat_id", "chat_id", "admin_chat_id")

def _send(text):
    token = _bot_token()
    chat_id = _chat_id()
    if not token or not chat_id:
        raise RuntimeError("Missing telegram token/chat_id")
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def _num(v, default=None):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default

def _money(v):
    x = _num(v)
    return "לא ידוע" if x is None else f"${x:,.2f}"

def _fmt_r(v):
    x = _num(v)
    if x is None:
        return "לא ידוע"
    sign = "+" if x > 0 else ""
    return f"{sign}{x:.1f}R"

def _fetch(table, limit=500):
    return table.select("*").limit(limit).execute().data or []

def _approved_plan_ids():
    local = _read_json(BASE_DIR / "post_entry_intake_state.json", {"campaigns": {}})
    approved = set()
    for cid, rec in (local.get("campaigns") or {}).items():
        if rec.get("status") == "approved":
            approved.add(cid)
    return approved

def _load_open_context(supabase):
    campaigns = _fetch(supabase.table("campaigns"), 300)
    risks = _fetch(supabase.table("campaign_risk_snapshots"), 500)
    plans = _fetch(supabase.table("campaign_plans"), 300)

    latest_risk = {}
    for r in risks:
        cid = r.get("campaign_id")
        if not cid:
            continue
        prev = latest_risk.get(cid)
        if not prev or str(r.get("snapshot_at") or r.get("created_at") or "") > str(prev.get("snapshot_at") or prev.get("created_at") or ""):
            latest_risk[cid] = r

    plans_by = {p.get("campaign_id"): p for p in plans if p.get("campaign_id")}
    approved_local = _approved_plan_ids()

    out = []
    for c in campaigns:
        cid = c.get("campaign_id")
        if not cid:
            continue
        status = str(c.get("campaign_status") or "")
        if status not in ("active_managed", "runner", "partially_realized"):
            continue

        p = plans_by.get(cid, {})
        plan_status = str(p.get("plan_status") or p.get("status") or "").lower()
        if cid not in approved_local and plan_status not in ("approved", "active"):
            continue

        out.append({
            "campaign": c,
            "risk": latest_risk.get(cid, {}),
            "plan": p,
        })
    return out

def _strategy_avg_win(supabase):
    try:
        rows = supabase.table("campaigns").select("*").eq("strategy_eligible", True).limit(200).execute().data or []
    except Exception:
        return None, 0

    wins = []
    for r in rows:
        val = _num(r.get("closed_target_r"))
        if val is not None and val > 0:
            wins.append(val)

    if not wins:
        return None, len(rows)
    return sum(wins) / len(wins), len(rows)

def _trigger_key(cid, trigger):
    return f"{cid}:{trigger}"

def _already_sent(state, cid, trigger, signature):
    rec = state.setdefault("sent", {}).get(_trigger_key(cid, trigger))
    return rec and rec.get("signature") == signature

def _mark_sent(state, cid, trigger, signature):
    state.setdefault("sent", {})[_trigger_key(cid, trigger)] = {
        "signature": signature,
        "sent_at": _now(),
    }

def _build_alert(symbol, cid, trigger, title, action, context):
    lines = [
        f"{RTL}📌 Plan Monitor - {symbol}",
        f"{RTL}{SEP}",
        f"{RTL}• קמפיין: {cid}",
        f"{RTL}• טריגר: {title}",
        f"{RTL}• פעולה: {action}",
    ]

    for label, value in context:
        if value not in (None, "", []):
            lines.append(f"{RTL}• {label}: {value}")

    lines += [
        "",
        f"{RTL}זו התראה לפי תוכנית ניהול שאושרה, לא רשימת פוזיציות.",
    ]
    return "\n".join(lines)

def _evaluate(item, avg_win_r=None, sample_size=0):
    c = item["campaign"]
    r = item["risk"]
    p = item["plan"]

    cid = c.get("campaign_id")
    symbol = c.get("symbol") or "UNKNOWN"

    open_r = _num(r.get("open_target_r"))
    if open_r is None:
        open_r = _num(c.get("open_target_r"))
    if open_r is None:
        open_r = _num(c.get("open_r"))
    if open_r is None:
        closed = _num(r.get("closed_target_r"), 0.0) or 0.0
        total = _num(r.get("total_live_target_r"))
        if total is not None:
            open_r = total - closed

    current_risk = _num(r.get("current_risk_to_stop_usd"), 0.0)
    giveback = _num(r.get("giveback_to_stop_usd"), 0.0)
    target = _num(r.get("target_risk_usd") or p.get("target_risk_usd"))
    stop = _num(p.get("initial_stop_price") or p.get("stop_price") or c.get("current_stop"))

    alerts = []

    base_ctx = [
        ("Open R", _fmt_r(open_r)),
        ("סטופ", _money(stop)),
        ("סיכון לסטופ", _money(current_risk)),
        ("ויתור רווח אפשרי", _money(giveback)),
        ("Scope", p.get("metric_scope") or c.get("strategy_scope") or "YTD_VERIFIED_CAMPAIGNS_ONLY"),
    ]

    if current_risk and current_risk > 0:
        alerts.append((
            "risk_to_stop",
            "יש סיכון פתוח עד הסטופ",
            "לוודא שהסטופ בברוקר מעודכן ומתאים לתוכנית.",
            base_ctx,
        ))

    if open_r is not None and open_r >= 2.0:
        alerts.append((
            "protect_2r",
            "רווח סביב 2R ומעלה",
            "להגן על הטרייד. לא לתת לרווח טוב להפוך לבינוני.",
            base_ctx,
        ))

    if open_r is not None and open_r >= 3.0:
        alerts.append((
            "sell_or_trail_3r",
            "רווח סביב 3R ומעלה",
            "לשקול מימוש 25%-50% או סטופ נגרר לפי חוזק המניה.",
            base_ctx,
        ))

    if avg_win_r is not None and open_r is not None and open_r >= avg_win_r:
        alerts.append((
            "above_avg_win",
            f"מעל Avg Win מאומת ({_fmt_r(avg_win_r)})",
            "להגן על חלק משמעותי מהרווח. לא להחזיר טרייד איכותי לבינוניות.",
            base_ctx + [("מדגם", f"{sample_size} קמפיינים מאומתים")],
        ))

    if giveback is not None and target and giveback >= target:
        alerts.append((
            "giveback_gt_target_risk",
            "ויתור רווח גדול מ־1R יעד",
            "לבדוק אם ה־Runner עדיין מצדיק את הויתור עד הסטופ.",
            base_ctx,
        ))

    return symbol, cid, alerts

def run(supabase=None, dry_run=False):
    supabase = supabase or _supabase()
    state = _read_json(STATE_FILE, {"version": "plan_monitor_v1", "sent": {}})

    avg_win_r, sample_size = _strategy_avg_win(supabase)
    items = _load_open_context(supabase)

    sent = 0
    for item in items:
        symbol, cid, alerts = _evaluate(item, avg_win_r=avg_win_r, sample_size=sample_size)
        for trigger, title, action, ctx in alerts:
            # Signature ignores tiny price changes. It changes only when trigger class changes.
            sig = json.dumps({
                "trigger": trigger,
                "cid": cid,
                "title": title,
                "action": action,
            }, ensure_ascii=False, sort_keys=True)

            if _already_sent(state, cid, trigger, sig):
                continue

            text = _build_alert(symbol, cid, trigger, title, action, ctx)

            if dry_run:
                print("would_send", cid, trigger)
                print(text)
            else:
                _send(text)

            _mark_sent(state, cid, trigger, sig)
            sent += 1

    if not dry_run:
        state["updated_at"] = _now()
        _write_json(STATE_FILE, state)

    if sent == 0:
        print("PlanMonitor: no new plan alerts")
    else:
        print(f"PlanMonitor: sent {sent} alert(s)")
    return sent



# --- Sprint 10B: robust Telegram discovery + grouped campaign alerts ---

def _manual_env_load(path):
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

_manual_env_load(ENV_FILE)
_manual_env_load("/app/.env")

def _deep_find(obj, names):
    targets = {str(n).lower() for n in names}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in targets and v not in (None, "", []):
                return v
        for v in obj.values():
            found = _deep_find(v, names)
            if found not in (None, "", []):
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _deep_find(v, names)
            if found not in (None, "", []):
                return found
    return None

def _config_value(*names):
    cfg = _read_json(CONFIG_FILE, {})
    return _deep_find(cfg, names)

def _module_guess(kind):
    try:
        import sys
        needles = ["TOKEN", "BOT"] if kind == "token" else ["CHAT", "USER", "ADMIN"]
        for mod_name in ["risk_monitor", "telegram_bot", "main"]:
            mod = sys.modules.get(mod_name)
            if not mod:
                continue
            for k, v in vars(mod).items():
                ku = str(k).upper()
                if all(n in ku for n in needles[:1]) and v not in (None, "", []):
                    if kind == "token" and ("TOKEN" in ku or "BOT_TOKEN" in ku):
                        return v
                    if kind == "chat" and ("CHAT" in ku or "USER_ID" in ku or "ADMIN" in ku):
                        return v
    except Exception:
        pass
    return None

def _first_chat(v):
    if isinstance(v, (list, tuple)):
        return str(v[0]) if v else None
    s = str(v or "").strip()
    if "," in s:
        return s.split(",", 1)[0].strip()
    return s or None

def _bot_token():
    val = (
        _env("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN", "BOT_TOKEN", "TG_TOKEN", "BOT_API_TOKEN", "API_TOKEN")
        or _config_value("telegram_bot_token", "telegram_token", "bot_token", "tg_token", "token", "api_token")
        or _module_guess("token")
    )
    return str(val).strip() if val else None

def _chat_id():
    val = (
        _env("TELEGRAM_CHAT_ID", "TELEGRAM_USER_ID", "CHAT_ID", "ADMIN_CHAT_ID", "TG_CHAT_ID", "USER_ID", "OWNER_CHAT_ID")
        or _config_value("telegram_chat_id", "chat_id", "admin_chat_id", "tg_chat_id", "user_id", "owner_chat_id")
        or _module_guess("chat")
    )
    return _first_chat(val)

def _context_lines(ctx):
    out = []
    seen = set()
    for label, value in ctx:
        if value in (None, "", []):
            continue
        label = "Target R חי" if label == "Open R" else label
        key = (label, str(value))
        if key in seen:
            continue
        seen.add(key)
        out.append(f"{RTL}• {label}: {value}")
    return out

def _build_grouped_alert(symbol, cid, alert_items):
    titles = []
    actions = []
    ctx = []

    for trigger, title, action, item_ctx in alert_items:
        titles.append(title)
        actions.append(action)
        if not ctx and item_ctx:
            ctx = item_ctx

    # Keep the phone card short: show max 4 triggers, max 3 unique actions.
    uniq_titles = []
    for t in titles:
        if t not in uniq_titles:
            uniq_titles.append(t)

    uniq_actions = []
    for a in actions:
        if a not in uniq_actions:
            uniq_actions.append(a)

    lines = [
        f"{RTL}📌 Plan Monitor - {symbol}",
        f"{RTL}{SEP}",
        f"{RTL}• קמפיין: {cid}",
        f"{RTL}• טריגרים: " + " | ".join(uniq_titles[:4]),
    ]

    lines += _context_lines(ctx)

    lines += [
        "",
        f"{RTL}פעולה מומלצת:",
    ]
    for a in uniq_actions[:3]:
        lines.append(f"{RTL}• {a}")

    lines += [
        "",
        f"{RTL}זו התראה לפי תוכנית שאושרה. היא לא תחזור שוב בלי שינוי מהותי.",
    ]
    return "\n".join(lines)

def run(supabase=None, dry_run=False):
    supabase = supabase or _supabase()
    state = _read_json(STATE_FILE, {"version": "plan_monitor_v1", "sent": {}})

    avg_win_r, sample_size = _strategy_avg_win(supabase)
    items = _load_open_context(supabase)

    grouped = []

    for item in items:
        symbol, cid, alerts = _evaluate(item, avg_win_r=avg_win_r, sample_size=sample_size)
        new_alerts = []

        for trigger, title, action, ctx in alerts:
            sig = json.dumps({
                "trigger": trigger,
                "cid": cid,
                "title": title,
                "action": action,
            }, ensure_ascii=False, sort_keys=True)

            if _already_sent(state, cid, trigger, sig):
                continue

            new_alerts.append((trigger, title, action, ctx, sig))

        if new_alerts:
            grouped.append((symbol, cid, new_alerts))

    sent = 0

    for symbol, cid, alert_items in grouped:
        text = _build_grouped_alert(
            symbol,
            cid,
            [(trigger, title, action, ctx) for trigger, title, action, ctx, sig in alert_items],
        )

        if dry_run:
            print("would_send_grouped", cid, len(alert_items))
            print(text)
        else:
            _send(text)

        for trigger, title, action, ctx, sig in alert_items:
            _mark_sent(state, cid, trigger, sig)

        sent += 1

    if not dry_run:
        state["updated_at"] = _now()
        _write_json(STATE_FILE, state)

    if sent == 0:
        print("PlanMonitor: no new plan alerts")
    else:
        print(f"PlanMonitor: sent {sent} grouped alert(s)")
    return sent



# --- Sprint 10C: broader chat_id discovery ---

import re as _pm_re

def _chat_candidate(v):
    if v in (None, "", []):
        return None
    if isinstance(v, (list, tuple)):
        for item in v:
            found = _chat_candidate(item)
            if found:
                return found
        return None
    if isinstance(v, dict):
        for item in v.values():
            found = _chat_candidate(item)
            if found:
                return found
        return None

    s = str(v).strip().strip('"').strip("'")
    if "," in s:
        for part in s.split(","):
            found = _chat_candidate(part)
            if found:
                return found

    if _pm_re.fullmatch(r"-?\d{5,16}", s):
        return s
    return None

def _deep_find_chat(obj):
    if isinstance(obj, dict):
        preferred = []
        fallback = []
        for k, v in obj.items():
            ku = str(k).lower()
            if any(x in ku for x in ["chat", "telegram_chat", "tg_chat"]):
                preferred.append(v)
            elif any(x in ku for x in ["admin", "owner", "user", "allowed", "authorized", "lidor"]):
                fallback.append(v)

        for v in preferred + fallback:
            found = _chat_candidate(v)
            if found:
                return found

        for v in obj.values():
            found = _deep_find_chat(v)
            if found:
                return found

    if isinstance(obj, list):
        for v in obj:
            found = _deep_find_chat(v)
            if found:
                return found

    return None

def _source_chat_candidate():
    files = [
        BASE_DIR / ".env",
        Path("/app/.env"),
        CONFIG_FILE,
        BASE_DIR / "telegram_bot.py",
        BASE_DIR / "main.py",
        BASE_DIR / "risk_monitor.py",
        BASE_DIR / "sentinel_config.json",
    ]

    key_words = r"(CHAT|ADMIN|OWNER|USER|ALLOWED|AUTHORIZED|LIDOR|TG|TELEGRAM)"
    assign_re = _pm_re.compile(rf"(?im)^\s*([A-Z0-9_]*{key_words}[A-Z0-9_]*)\s*=\s*(.+)$")

    for path in files:
        try:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")

            if path.suffix == ".json":
                try:
                    found = _deep_find_chat(json.loads(text))
                    if found:
                        return found
                except Exception:
                    pass

            for m in assign_re.finditer(text):
                rhs = m.group(3)
                for num in _pm_re.findall(r"-?\d{5,16}", rhs):
                    return num
        except Exception:
            continue

    return None

def _chat_id():
    env_val = (
        _env(
            "TELEGRAM_CHAT_ID",
            "TELEGRAM_USER_ID",
            "TELEGRAM_ADMIN_ID",
            "TELEGRAM_OWNER_ID",
            "AUTHORIZED_USER_ID",
            "AUTHORIZED_USERS",
            "ALLOWED_USER_ID",
            "ALLOWED_USERS",
            "CHAT_ID",
            "ADMIN_CHAT_ID",
            "ADMIN_ID",
            "TG_CHAT_ID",
            "TG_USER_ID",
            "USER_ID",
            "OWNER_CHAT_ID",
            "LIDOR_CHAT_ID",
        )
    )
    found = _chat_candidate(env_val)
    if found:
        return found

    cfg = _read_json(CONFIG_FILE, {})
    found = _deep_find_chat(cfg)
    if found:
        return found

    found = _module_guess("chat")
    if found:
        found = _chat_candidate(found)
        if found:
            return found

    return _source_chat_candidate()




# --- Sprint 10D: better stop fallback + clearer R labels ---

def _approved_local_campaign(cid):
    data = _read_json(BASE_DIR / "post_entry_intake_state.json", {"campaigns": {}})
    return (data.get("campaigns") or {}).get(cid, {}) or {}

def _first_num_from(*objs, keys=None):
    keys = keys or []
    for obj in objs:
        if not isinstance(obj, dict):
            continue
        for key in keys:
            val = _num(obj.get(key))
            if val is not None:
                return val
    return None

def _find_stop_value(cid, campaign, risk, plan):
    local = _approved_local_campaign(cid)

    val = _first_num_from(
        local, plan, campaign, risk,
        keys=[
            "stop_override",
            "user_initial_stop_price",
            "initial_stop_price",
            "initial_stop",
            "stop_price",
            "current_stop",
            "proposed_stop",
            "planned_stop",
            "trail_stop",
        ],
    )
    if val is not None:
        return val

    # Last-resort scan: find any numeric field whose key contains stop.
    for obj in [local, plan, campaign, risk]:
        if not isinstance(obj, dict):
            continue
        for k, v in obj.items():
            if "stop" in str(k).lower():
                val = _num(v)
                if val is not None and val > 0:
                    return val
    return None

def _find_open_actual_r(campaign, risk):
    val = _first_num_from(
        risk, campaign,
        keys=["open_actual_r", "actual_open_r", "open_r_actual", "open_r"],
    )
    if val is not None:
        return val

    total = _first_num_from(risk, campaign, keys=["total_live_actual_r", "actual_total_live_r"])
    closed = _first_num_from(risk, campaign, keys=["closed_actual_r"])
    if total is not None and closed is not None:
        return total - closed
    return None

def _evaluate(item, avg_win_r=None, sample_size=0):
    c = item["campaign"]
    r = item["risk"]
    p = item["plan"]

    cid = c.get("campaign_id")
    symbol = c.get("symbol") or "UNKNOWN"

    open_target_r = _num(r.get("open_target_r"))
    if open_target_r is None:
        open_target_r = _num(c.get("open_target_r"))
    if open_target_r is None:
        closed = _num(r.get("closed_target_r"), 0.0) or 0.0
        total = _num(r.get("total_live_target_r"))
        if total is not None:
            open_target_r = total - closed

    open_actual_r = _find_open_actual_r(c, r)

    current_risk = _num(r.get("current_risk_to_stop_usd"), 0.0)
    giveback = _num(r.get("giveback_to_stop_usd"), 0.0)
    target = _num(r.get("target_risk_usd") or p.get("target_risk_usd"))
    stop = _find_stop_value(cid, c, r, p)

    alerts = []

    base_ctx = [
        ("Target R חי", _fmt_r(open_target_r)),
        ("Actual R חי", _fmt_r(open_actual_r) if open_actual_r is not None else None),
        ("סטופ", _money(stop)),
        ("סיכון לסטופ", _money(current_risk)),
        ("ויתור רווח אפשרי", _money(giveback)),
        ("Scope", p.get("metric_scope") or c.get("strategy_scope") or "YTD_VERIFIED_CAMPAIGNS_ONLY"),
    ]

    if current_risk and current_risk > 0:
        alerts.append((
            "risk_to_stop",
            "יש סיכון פתוח עד הסטופ",
            "לוודא שהסטופ בברוקר מעודכן ומתאים לתוכנית.",
            base_ctx,
        ))

    if open_target_r is not None and open_target_r >= 2.0:
        alerts.append((
            "protect_2r",
            "רווח סביב 2R ומעלה",
            "להגן על הטרייד. לא לתת לרווח טוב להפוך לבינוני.",
            base_ctx,
        ))

    if open_target_r is not None and open_target_r >= 3.0:
        alerts.append((
            "sell_or_trail_3r",
            "רווח סביב 3R ומעלה",
            "לשקול מימוש 25%-50% או סטופ נגרר לפי חוזק המניה.",
            base_ctx,
        ))

    if avg_win_r is not None and open_target_r is not None and open_target_r >= avg_win_r:
        alerts.append((
            "above_avg_win",
            f"מעל Avg Win מאומת ({_fmt_r(avg_win_r)})",
            "להגן על חלק משמעותי מהרווח. לא להחזיר טרייד איכותי לבינוניות.",
            base_ctx + [("מדגם", f"{sample_size} קמפיינים מאומתים")],
        ))

    if giveback is not None and target and giveback >= target:
        alerts.append((
            "giveback_gt_target_risk",
            "ויתור רווח גדול מ־1R יעד",
            "לבדוק אם ה־Runner עדיין מצדיק את הויתור עד הסטופ.",
            base_ctx,
        ))

    return symbol, cid, alerts

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(dry_run=args.dry_run)

# --- BEGIN Sentinel plan monitor concrete actions inline patch 2026-05-04 ---
def _sentinel_plan_qty(v):
    x = _num(v, 0.0) or 0.0
    return str(int(round(x))) if abs(x - round(x)) < 0.0001 else "{:.2f}".format(x).rstrip("0").rstrip(".")

def _sentinel_plan_partial(qty, pct=25):
    q = _num(qty, 0.0) or 0.0
    if q <= 0:
        return "חסרה כמות פתוחה; לא שולח הוראת מימוש חלקי."
    if q < 2:
        return "כמות 1: לא לממש חלקית; לנהל דרך סטופ."
    sell_qty = max(1.0, round(q * (float(pct) / 100.0)))
    if sell_qty >= q:
        sell_qty = max(1.0, q - 1.0)
    actual_pct = (sell_qty / q) * 100.0 if q else 0.0
    return "לממש {} מתוך {} מניות (~{:.0f}% בפועל).".format(_sentinel_plan_qty(sell_qty), _sentinel_plan_qty(q), actual_pct)

def _sentinel_plan_protect(stop, entry):
    s = _num(stop)
    e = _num(entry)
    if e is None:
        return "לעדכן סטופ הגנה ידנית לפני החלטה נוספת."
    if s is not None and s >= e:
        return "סטופ כבר בסיכון אפס/מעל כניסה: להשאיר {}.".format(_money(s))
    return "לקדם סטופ לכניסה / סיכון אפס: {}.".format(_money(e))

def _sentinel_plan_open_r(c, r):
    val = _num(r.get("open_target_r"))
    if val is not None:
        return val
    val = _num(c.get("open_target_r"))
    if val is not None:
        return val
    closed = _num(r.get("closed_target_r"), 0.0) or 0.0
    total = _num(r.get("total_live_target_r"))
    return total - closed if total is not None else None

def _evaluate(item, avg_win_r=None, sample_size=0):
    c, r, p = item["campaign"], item["risk"], item["plan"]
    cid = c.get("campaign_id")
    symbol = c.get("symbol") or "UNKNOWN"
    open_target_r = _sentinel_plan_open_r(c, r)
    open_actual_r = _num(r.get("open_actual_r") or c.get("open_actual_r"))
    current_risk = _num(r.get("current_risk_to_stop_usd"), 0.0)
    giveback = _num(r.get("giveback_to_stop_usd"), 0.0)
    target = _num(r.get("target_risk_usd") or p.get("target_risk_usd"))
    stop = _num(r.get("current_stop") or p.get("current_stop") or p.get("initial_stop_price") or p.get("stop_price") or c.get("current_stop"))
    qty = _num(r.get("quantity_remaining") or c.get("quantity_remaining"), 0.0)
    avg_entry = _num(r.get("avg_entry_price") or c.get("avg_entry_price") or p.get("entry_price"))

    base_ctx = [
        ("Target R חי", _fmt_r(open_target_r)),
        ("Actual R חי", _fmt_r(open_actual_r) if open_actual_r is not None else None),
        ("כמות פתוחה", _sentinel_plan_qty(qty)),
        ("סטופ", _money(stop)),
        ("סיכון לסטופ", _money(current_risk)),
        ("ויתור רווח אפשרי", _money(giveback)),
        ("Scope", p.get("metric_scope") or c.get("strategy_scope") or "YTD_VERIFIED_CAMPAIGNS_ONLY"),
    ]

    alerts = []
    if current_risk and current_risk > 0:
        alerts.append(("risk_to_stop", "יש סיכון פתוח עד הסטופ", "לעדכן בברוקר סטופ פעיל ל-{} או להקטין חשיפה עד שהסיכון לסטופ מתאים לתוכנית.".format(_money(stop)), base_ctx))
    if open_target_r is not None and open_target_r >= 2.0:
        alerts.append(("protect_2r", "רווח סביב 2R ומעלה", _sentinel_plan_protect(stop, avg_entry), base_ctx))
    if open_target_r is not None and open_target_r >= 3.0:
        alerts.append(("sell_or_trail_3r", "רווח סביב 3R ומעלה", "{} לאחר המימוש, {}".format(_sentinel_plan_partial(qty, 25), _sentinel_plan_protect(stop, avg_entry)), base_ctx))
    if avg_win_r is not None and open_target_r is not None and open_target_r >= avg_win_r:
        alerts.append(("above_avg_win", f"מעל Avg Win מאומת ({_fmt_r(avg_win_r)})", "{} {}".format(_sentinel_plan_partial(qty, 25), _sentinel_plan_protect(stop, avg_entry)), base_ctx + [("מדגם", f"{sample_size} קמפיינים מאומתים")]))
    if giveback is not None and target and giveback >= target:
        alerts.append(("giveback_gt_target_risk", "ויתור רווח גדול מ־1R יעד", "להקטין ויתור: לקדם סטופ או לממש 25% כך שהויתור לא יעלה על 1R יעד.", base_ctx))
    return symbol, cid, alerts
# --- END Sentinel plan monitor concrete actions inline patch 2026-05-04 ---
