import os, json, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "post_entry_intake_state.json"
PUSH_STATE_FILE = BASE_DIR / "post_entry_intake_push_state.json"
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
        if Path(path).exists():
            return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def _write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _env(*names):
    for name in names:
        v = os.getenv(name)
        if v:
            return v
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

def _send_telegram(text, keyboard=None):
    token = _bot_token()
    chat_id = _chat_id()
    if not token or not chat_id:
        raise RuntimeError("Missing telegram token/chat_id")

    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard, ensure_ascii=False)

    data = urllib.parse.urlencode(payload).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    with urllib.request.urlopen(url, data=data, timeout=20) as r:
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

def _pct(v):
    x = _num(v)
    return "" if x is None else f"{x:.0f}%"

def _state():
    return _read_json(STATE_FILE, {"campaigns": {}})

def _push_state():
    return _read_json(PUSH_STATE_FILE, {"pushed": {}})

def _task_open(task, local):
    if local.get("status") in ("approved", "skipped"):
        return False
    st = str(task.get("task_status") or task.get("status") or "pending").lower()
    return st not in ("done", "completed", "approved", "closed", "cancelled")

def _summarize_plan(task, plan):
    cid = task.get("campaign_id") or plan.get("campaign_id")
    symbol = plan.get("symbol") or task.get("symbol") or "UNKNOWN"
    setup = plan.get("setup_type") or task.get("setup_type") or "לא מסווג"
    stop = plan.get("initial_stop_price") or plan.get("stop_price") or plan.get("current_stop")
    actual = plan.get("actual_initial_risk_usd")
    target = plan.get("target_risk_usd")
    conf = _pct(plan.get("confidence_score") or plan.get("confidence"))
    sample = plan.get("strategy_sample_size") or plan.get("sample_size")
    scope = plan.get("metric_scope") or plan.get("strategy_scope") or "YTD verified"

    lines = [
        f"{RTL}🧾 זוהה קמפיין פתוח - {symbol}",
        f"{RTL}{SEP}",
        f"{RTL}המערכת בנתה תוכנית ניהול ראשונית.",
        f"{RTL}• Setup: {setup}",
        f"{RTL}• סטופ: {_money(stop)}",
        f"{RTL}• סיכון בפועל: {_money(actual)} מול יעד {_money(target)}",
    ]
    if conf:
        lines.append(f"{RTL}• ביטחון תוכנית: {conf}")
    if sample:
        lines.append(f"{RTL}• בסיס: {sample} קמפיינים מאומתים | {scope}")

    lines += [
        "",
        f"{RTL}מה לעשות עכשיו:",
        f"{RTL}אשרי, ערכי סטופ/Setup, או הוסיפי קטליסט.",
        f"{RTL}תמונה תיאסף בסגירת הקמפיין, לא בפתיחה.",
    ]
    return "\n".join(lines), cid

def _keyboard(cid):
    return {
        "inline_keyboard": [
            [
                {"text": "🧾 פתח תוכנית", "callback_data": f"intake:view:{cid}"},
                {"text": "✅ אשר", "callback_data": f"intake:approve:{cid}"},
            ],
            [
                {"text": "✏️ סטופ", "callback_data": f"intake:edit_stop:{cid}"},
                {"text": "🏷️ Setup", "callback_data": f"intake:edit_setup:{cid}"},
            ],
            [
                {"text": "🧠 קטליסט", "callback_data": f"intake:catalyst:{cid}"},
                {"text": "⏭️ דלג", "callback_data": f"intake:snooze:{cid}"},
            ],
        ]
    }

def _fetch_pending(supabase):
    tasks = supabase.table("campaign_intake_tasks").select("*").limit(200).execute().data or []
    plans = supabase.table("campaign_plans").select("*").limit(200).execute().data or []
    by_cid = {p.get("campaign_id"): p for p in plans if p.get("campaign_id")}
    local_state = _state().get("campaigns", {})

    out = []
    for task in tasks:
        cid = task.get("campaign_id")
        if not cid:
            continue
        local = local_state.get(cid, {})
        if not _task_open(task, local):
            continue
        out.append((task, by_cid.get(cid, {})))
    return out

def rebuild_plans_if_possible():
    try:
        import campaign_plan_builder
        if hasattr(campaign_plan_builder, "run"):
            campaign_plan_builder.run(dry_run=False)
            return True
    except Exception as e:
        print(f"PostEntry Intake warning: plan rebuild skipped: {e}")
    return False

def push_pending_intake(supabase=None, dry_run=False, rebuild=True):
    if rebuild:
        rebuild_plans_if_possible()

    supabase = supabase or _supabase()
    pushed = _push_state()
    pushed.setdefault("pushed", {})

    pending = _fetch_pending(supabase)
    sent = 0

    for task, plan in pending:
        text, cid = _summarize_plan(task, plan)
        if not cid:
            continue

        signature = json.dumps({
            "cid": cid,
            "task_updated": task.get("updated_at") or task.get("created_at"),
            "plan_updated": plan.get("updated_at") or plan.get("calculated_at"),
        }, sort_keys=True, default=str)

        if pushed["pushed"].get(cid) == signature:
            continue

        if dry_run:
            print("would_push", cid)
            print(text)
        else:
            _send_telegram(text, _keyboard(cid))

        pushed["pushed"][cid] = signature
        pushed["updated_at"] = _now()
        sent += 1

    if not dry_run:
        _write_json(PUSH_STATE_FILE, pushed)

    if sent == 0:
        print("PostEntry Intake: no new pending plans")
    else:
        print(f"PostEntry Intake: pushed {sent} plan(s)")
    return sent

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-rebuild", action="store_true")
    args = ap.parse_args()
    push_pending_intake(dry_run=args.dry_run, rebuild=not args.no_rebuild)
