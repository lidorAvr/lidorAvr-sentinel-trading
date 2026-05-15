"""
Pure helper functions for Sentinel Trading Telegram bot.

No bot/user_state/Telegram dependencies — safe to import and test anywhere.
"""
import os, json, random
from datetime import datetime
import engine_core as ec
import state_io

_BOT_LOG_FILE      = "/app/logs/sentinel_bot.log"
_BOT_LOG_MAX_LINES = 2000
_RM_STATE_FILE     = "risk_monitor_state.json"

_DEV_LOG_FILES = {
    "sentinel-main": "/app/logs/sentinel_main.log",
    "sentinel-bot":  "/app/logs/sentinel_bot.log",
    "risk-monitor":  "/app/logs/sentinel_risk.log",
}


def _bot_log(msg: str) -> None:
    """Append a timestamped line to the bot log file."""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        os.makedirs(os.path.dirname(_BOT_LOG_FILE), exist_ok=True)
        with open(_BOT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
        if random.random() < 0.05:
            lines = open(_BOT_LOG_FILE, encoding="utf-8").readlines()
            if len(lines) > _BOT_LOG_MAX_LINES:
                with open(_BOT_LOG_FILE, "w", encoding="utf-8") as f:
                    f.writelines(lines[-_BOT_LOG_MAX_LINES:])
    except Exception:
        pass


def _read_last_log_lines(path: str, n: int = 50) -> str:
    try:
        if not os.path.exists(path):
            return f"_(קובץ לא קיים: {path})_"
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        tail = "".join(lines[-n:]) if lines else "(ריק)"
        return tail.strip()
    except Exception as e:
        return f"_(שגיאה בקריאת לוג: {e})_"


def _write_runner_decision(campaign_id: str, decision: str) -> None:
    """Write runner_decision + runner_decision_ts into risk_monitor_state.json."""
    try:
        # Whole read-modify-write under one lock so it cannot interleave
        # with risk_monitor.save_state (shared state file, different
        # container). Atomic write so a concurrent reader never sees a
        # partial file. See state_io / SYSTEM_AUDIT §5.7 (Issue N3).
        with state_io.file_lock(_RM_STATE_FILE):
            rm_state = state_io.read_json(_RM_STATE_FILE,
                                          {"positions": {}, "cluster": {}})
            pos_entry = rm_state.setdefault("positions", {}).get(campaign_id)
            if pos_entry is None:
                rm_state["positions"][campaign_id] = {}
                pos_entry = rm_state["positions"][campaign_id]
            pos_entry["runner_decision"] = decision
            pos_entry["runner_decision_ts"] = datetime.now().timestamp()
            state_io.atomic_write_json(_RM_STATE_FILE, rm_state)
    except Exception:
        pass


def get_account_settings() -> dict:
    try:
        with open("sentinel_config.json", "r") as f:
            return json.load(f)
    except Exception:
        return {"total_deposited": 7500.0, "risk_pct_input": 0.5}


def get_nav_and_risk(account_settings=None):
    """Single source of truth for NAV + target risk.
    Returns (acc_size, target_risk_usd, nav_freshness_label).
    """
    if account_settings is None:
        account_settings = get_account_settings()
    nav_info = ec.get_nav_with_freshness()
    acc_size = nav_info["nav"] if nav_info["ok"] else float(account_settings.get("total_deposited", 7500.0))
    risk_pct = float(account_settings.get("risk_pct_input", 0.5))
    target_risk_usd = acc_size * (risk_pct / 100)
    stale_label = nav_info["freshness_label"] if nav_info["is_stale"] else None
    return acc_size, target_risk_usd, stale_label
