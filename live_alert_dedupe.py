import json
import re
import time
import urllib.parse
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "live_alert_dedupe_state.json"

RTL = "\u200f"

_INSTALLED = False

def _now_ts():
    return time.time()

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _load():
    if not STATE_FILE.exists():
        return {"version": "live_alert_dedupe_v1", "alerts": {}}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": "live_alert_dedupe_v1", "alerts": {}}
        data.setdefault("version", "live_alert_dedupe_v1")
        data.setdefault("alerts", {})
        return data
    except Exception:
        return {"version": "live_alert_dedupe_v1", "alerts": {}}

def _save(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def _clean_text(text):
    return str(text or "").replace(RTL, "").strip()

def _extract(pattern, text, default=""):
    m = re.search(pattern, text, re.MULTILINE)
    return (m.group(1).strip() if m else default)

def _is_live_alert(text):
    t = _clean_text(text)
    return "Sentinel Live Alert" in t or "סימול:" in t and "כרטיס החלטה:" in t

def _is_critical(text):
    t = _clean_text(text)
    critical_words = ["קריטי", "סטופ נחצה", "יציאה מיידית", "stop hit", "emergency"]
    return any(w.lower() in t.lower() for w in critical_words)

def _semantic_key(text):
    t = _clean_text(text)

    symbol = _extract(r"סימול:\s*([^|\n]+)", t, "UNKNOWN")
    campaign = _extract(r"קמפיין:\s*([^\n]+)", t, "")
    management = _extract(r"מצב ניהולי:\s*([^\n|]+)", t, "")
    decision = _extract(r"כרטיס החלטה:\s*([^\n|]+)", t, "")
    decision_action = _extract(r"כרטיס החלטה:[^\n|]*\|\s*([^\n]+)", t, "")
    status = _extract(r"סטטוס:\s*([^\n]+)", t, "")
    action = _extract(r"פעולה:\s*([^\n]+)", t, "")
    trigger = _extract(r"טריגר:\s*([^\n]+)", t, "")
    violations = _extract(r"הפרות:\s*([0-9]+)", t, "")

    # Deliberately excludes current price / exposure / Open R.
    # Small price changes must not create a new Telegram alert.
    parts = [
        symbol,
        campaign,
        management,
        decision,
        decision_action,
        status,
        action,
        trigger,
        violations,
    ]
    return "|".join(str(x or "").strip() for x in parts)

def should_send(text):
    if not _is_live_alert(text):
        return True, "not_live_alert"

    key = _semantic_key(text)
    critical = _is_critical(text)
    cooldown = 30 * 60 if critical else 4 * 60 * 60

    state = _load()
    alerts = state.setdefault("alerts", {})
    rec = alerts.get(key)

    now = _now_ts()

    if rec:
        age = now - float(rec.get("last_sent_ts", 0) or 0)
        if age < cooldown:
            rec["last_suppressed_at"] = _now_iso()
            rec["suppressed_count"] = int(rec.get("suppressed_count", 0) or 0) + 1
            alerts[key] = rec
            _save(state)
            return False, f"duplicate_cooldown_{int(age)}s"

    # Bootstrap behavior: on the very first time we see an existing non-critical
    # live state after deployment/restart, record it but do not send. This avoids
    # one more MRVL-style alert immediately after installing the guard.
    if not rec and not critical:
        alerts[key] = {
            "first_seen_at": _now_iso(),
            "last_sent_ts": now,
            "last_sent_at": _now_iso(),
            "bootstrap_suppressed": True,
            "suppressed_count": 1,
        }
        _save(state)
        return False, "bootstrap_noncritical_suppressed"

    alerts[key] = {
        "first_seen_at": rec.get("first_seen_at") if rec else _now_iso(),
        "last_sent_ts": now,
        "last_sent_at": _now_iso(),
        "critical": critical,
        "suppressed_count": int((rec or {}).get("suppressed_count", 0) or 0),
    }
    _save(state)
    return True, "send"

def _extract_text_from_kwargs(args, kwargs):
    if kwargs:
        if isinstance(kwargs.get("json"), dict) and kwargs["json"].get("text"):
            return kwargs["json"].get("text")
        if isinstance(kwargs.get("data"), dict) and kwargs["data"].get("text"):
            return kwargs["data"].get("text")

    if args:
        for arg in args:
            if isinstance(arg, dict) and arg.get("text"):
                return arg.get("text")

    return None

class _DummyHTTPResponse:
    status = 200
    code = 200

    def read(self):
        return b'{"ok": true, "description": "suppressed duplicate live alert"}'

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    # Patch requests.post if requests is used.
    try:
        import requests
        _orig_post = requests.post

        def _post(url, *args, **kwargs):
            text = _extract_text_from_kwargs(args, kwargs)
            if text and "api.telegram.org" in str(url):
                ok, reason = should_send(text)
                if not ok:
                    print(f"LiveAlertDedupe: suppressed telegram live alert ({reason})")
                    return SimpleNamespace(
                        status_code=200,
                        text='{"ok": true, "description": "suppressed duplicate live alert"}',
                        json=lambda: {"ok": True, "description": "suppressed duplicate live alert"},
                    )
            return _orig_post(url, *args, **kwargs)

        requests.post = _post
    except Exception:
        pass

    # Patch urllib.request.urlopen if urllib is used.
    try:
        import urllib.request
        _orig_urlopen = urllib.request.urlopen

        def _urlopen(url, data=None, *args, **kwargs):
            url_s = str(url)
            text = None

            try:
                if data and "api.telegram.org" in url_s:
                    decoded = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
                    parsed = urllib.parse.parse_qs(decoded)
                    text = (parsed.get("text") or [None])[0]
            except Exception:
                text = None

            if text:
                ok, reason = should_send(text)
                if not ok:
                    print(f"LiveAlertDedupe: suppressed telegram live alert ({reason})")
                    return _DummyHTTPResponse()

            return _orig_urlopen(url, data=data, *args, **kwargs)

        urllib.request.urlopen = _urlopen
    except Exception:
        pass

    # Patch TeleBot.send_message if pyTelegramBotAPI is used.
    try:
        import telebot
        _orig_send_message = telebot.TeleBot.send_message

        def _send_message(self, chat_id, text, *args, **kwargs):
            ok, reason = should_send(text)
            if not ok:
                print(f"LiveAlertDedupe: suppressed telebot live alert ({reason})")
                return SimpleNamespace(message_id=0, chat=SimpleNamespace(id=chat_id), text=text)
            return _orig_send_message(self, chat_id, text, *args, **kwargs)

        telebot.TeleBot.send_message = _send_message
    except Exception:
        pass

    print("LiveAlertDedupe: installed")
