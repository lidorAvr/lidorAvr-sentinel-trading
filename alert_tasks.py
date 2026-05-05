import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

STATE_FILE = Path(__file__).resolve().parent / "alert_tasks_state.json"
RTL = "\u200f"

def _now():
    return datetime.now(timezone.utc).isoformat()

def _id(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

def load_state():
    if not STATE_FILE.exists():
        return {"version": "alert_tasks_v1", "tasks": {}}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": "alert_tasks_v1", "tasks": {}}
        data.setdefault("version", "alert_tasks_v1")
        data.setdefault("tasks", {})
        return data
    except Exception:
        return {"version": "alert_tasks_v1", "tasks": {}}

def save_state(state):
    state.setdefault("version", "alert_tasks_v1")
    state.setdefault("tasks", {})
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state

def add_task(title=None, symbol=None, body=None, priority="normal", source="manual", **kwargs):
    payload = {
        "title": title or kwargs.get("text") or kwargs.get("message") or "משימה",
        "symbol": symbol or kwargs.get("ticker"),
        "body": body or kwargs.get("note") or "",
        "priority": priority,
        "source": source,
    }
    task_id = kwargs.get("task_id") or _id(payload)
    state = load_state()
    task = state.setdefault("tasks", {}).setdefault(task_id, {})
    task.update(payload)
    task.setdefault("status", "open")
    task.setdefault("created_at", _now())
    task["updated_at"] = _now()
    save_state(state)
    return task

def upsert_task(*args, **kwargs):
    return add_task(*args, **kwargs)

def create_task(*args, **kwargs):
    return add_task(*args, **kwargs)

def get_tasks(status=None):
    tasks = list(load_state().get("tasks", {}).values())
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    return tasks

def open_tasks():
    return get_tasks("open")

def get_open_tasks():
    return open_tasks()

def list_tasks(status="open"):
    return get_tasks(status)

def complete_task(task_id, **kwargs):
    state = load_state()
    task = state.setdefault("tasks", {}).setdefault(str(task_id), {})
    task["status"] = "done"
    task["completed_at"] = _now()
    task["updated_at"] = _now()
    save_state(state)
    return task

def close_task(task_id, **kwargs):
    return complete_task(task_id, **kwargs)

def mark_done(task_id, **kwargs):
    return complete_task(task_id, **kwargs)

def snooze_task(task_id, hours=24, **kwargs):
    state = load_state()
    task = state.setdefault("tasks", {}).setdefault(str(task_id), {})
    task["status"] = "snoozed"
    task["snooze_until"] = (datetime.now(timezone.utc) + timedelta(hours=float(hours))).isoformat()
    task["updated_at"] = _now()
    save_state(state)
    return task

def render_tasks(tasks=None, limit=20):
    tasks = tasks if tasks is not None else open_tasks()
    if not tasks:
        return f"{RTL}אין כרגע משימות פתוחות."
    lines = [f"{RTL}🔍 סריקת יומן / Backlog", f"{RTL}━━━━━━━━━━━━"]
    for i, t in enumerate(tasks[:limit], 1):
        sym = t.get("symbol") or ""
        title = t.get("title") or t.get("body") or "משימה"
        pr = t.get("priority") or "normal"
        lines.append(f"{RTL}{i}. {sym} {title} | {pr}")
    return "\n".join(lines)

def format_tasks_message(*args, **kwargs):
    return render_tasks(*args, **kwargs)

def backlog_message(*args, **kwargs):
    return render_tasks(*args, **kwargs)

def get_backlog_message(*args, **kwargs):
    return render_tasks(*args, **kwargs)
