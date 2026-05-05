import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

try:
    import action_queue_state as aqs
except Exception:
    aqs = None

BASE_DIR = Path(__file__).resolve().parent
PUSH_STATE_FILE = BASE_DIR / "action_queue_push_state.json"
CONFIG_FILE = BASE_DIR / "sentinel_config.json"
ENV_FILE = BASE_DIR / ".env"

RTL = "\u200f"
SEP = "━━━━━━━━━━━━"

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

def _load_env_file(path):
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

_load_env_file(ENV_FILE)
_load_env_file("/app/.env")

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

def _bot_token():
    return _env("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN", "BOT_TOKEN") or _config_value("telegram_token", "bot_token")

def _chat_id():
    return _env("TELEGRAM_CHAT_ID", "CHAT_ID", "ADMIN_CHAT_ID") or _config_value("telegram_chat_id", "chat_id", "admin_chat_id")

def _send_telegram(text):
    token = _bot_token()
    chat_id = _chat_id()
    if not token or not chat_id:
        raise RuntimeError("Missing telegram token/chat_id")
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def _action_key(action):
    if aqs and hasattr(aqs, "action_key"):
        try:
            return aqs.action_key(action)
        except Exception:
            pass
    return str(action.get("campaign_id") or action.get("symbol") or "unknown")

def _fingerprint(action):
    if aqs and hasattr(aqs, "compute_fingerprint"):
        try:
            return aqs.compute_fingerprint(action)
        except Exception:
            pass
    return json.dumps(action, ensure_ascii=False, sort_keys=True, default=str)

def _hidden(action, fp):
    if aqs and hasattr(aqs, "should_hide_action"):
        try:
            return aqs.should_hide_action(action, fp)
        except Exception:
            return False
    return False

def _format_action(action):
    symbol = action.get("symbol") or "UNKNOWN"
    priority = action.get("priority") or action.get("urgency") or "לא ידוע"
    decision = action.get("decision_bias") or action.get("decision") or action.get("action_type") or "פעולה"
    primary = action.get("primary_action") or action.get("action") or action.get("message") or ""
    status = action.get("status") or action.get("position_status") or ""
    return "\n".join([
        f"{RTL}🎯 פעולה חדשה - {symbol}",
        f"{RTL}{SEP}",
        f"{RTL}• עדיפות: {priority}",
        f"{RTL}• מצב: {status}",
        f"{RTL}• החלטה: {decision}",
        f"{RTL}• פעולה: {primary}",
    ])

def push_actions(actions=None, dry_run=False, **kwargs):
    actions = actions or kwargs.get("open_actions") or []
    if not actions:
        print("ActionQueue Live: no open actions")
        return 0

    state = _read_json(PUSH_STATE_FILE, {"pushed": {}})
    state.setdefault("pushed", {})
    sent = 0

    for action in actions:
        if not isinstance(action, dict):
            continue
        key = _action_key(action)
        fp = _fingerprint(action)
        if _hidden(action, fp):
            continue
        if state["pushed"].get(key) == fp:
            continue

        text = _format_action(action)
        if dry_run:
            print("would_push", key, text)
        else:
            _send_telegram(text)

        state["pushed"][key] = fp
        state["updated_at"] = _now()
        sent += 1

    if not dry_run:
        _write_json(PUSH_STATE_FILE, state)

    if sent == 0:
        print("ActionQueue Live: no new actions")
    else:
        print(f"ActionQueue Live: pushed {sent} action(s)")
    return sent

def push_live_actions(*args, **kwargs):
    return push_actions(*args, **kwargs)

def push_action_queue(*args, **kwargs):
    return push_actions(*args, **kwargs)

def run(*args, **kwargs):
    return push_actions(*args, **kwargs)

if __name__ == "__main__":
    push_actions(dry_run=True)


# Compatibility aliases expected by risk_monitor.
def push_live_action_queue(*args, **kwargs):
    return push_actions(*args, **kwargs)

def push_action_queue_live(*args, **kwargs):
    return push_actions(*args, **kwargs)


# --- Argument compatibility for risk_monitor action queue calls ---

def _extract_action_args(args, kwargs):
    kw = dict(kwargs)
    actions = kw.pop("actions", None)
    if actions is None:
        actions = kw.pop("open_actions", None)
    if actions is None:
        actions = kw.pop("queue", None)

    rest = list(args)

    # Some callers pass Supabase client as the first positional argument.
    if rest and hasattr(rest[0], "table"):
        rest.pop(0)

    if actions is None and rest:
        candidate = rest.pop(0)
        if isinstance(candidate, list):
            actions = candidate
        elif isinstance(candidate, tuple):
            actions = list(candidate)
        elif isinstance(candidate, dict):
            actions = [candidate]
        else:
            actions = []

    return actions or [], kw

def push_live_action_queue(*args, **kwargs):
    actions, kw = _extract_action_args(args, kwargs)
    return push_actions(actions=actions, **kw)

def push_action_queue_live(*args, **kwargs):
    actions, kw = _extract_action_args(args, kwargs)
    return push_actions(actions=actions, **kw)
