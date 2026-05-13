import os
import json
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from ibkr_sync_runner import run_ibkr_sync, IBKR_ERROR_CLASSES, MANUAL_RESULT_FILE

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

SYNC_STATE_FILE   = "/app/ibkr_sync_state.json"
MANUAL_TRIGGER_FILE = "/app/ibkr_manual_trigger"   # written by telegram_bot developer menu
LOG_FILE           = "/app/logs/sentinel_main.log"
LOG_MAX_LINES      = 2000
_HEARTBEAT_DIR     = "/app/state"


def _touch_heartbeat(name: str) -> None:
    """Write current timestamp to /app/state/{name}_last_cycle so healthchecks can verify liveness."""
    try:
        os.makedirs(_HEARTBEAT_DIR, exist_ok=True)
        path = os.path.join(_HEARTBEAT_DIR, f"{name}_last_cycle")
        with open(path, "w") as fh:
            fh.write(str(time.time()))
    except Exception:
        pass

SYNC_START_HOUR       = 7
SYNC_END_HOUR         = 11
MAX_ATTEMPTS_PER_DAY  = 5     # raised from 3 — one attempt per hour 07-11
LOOP_INTERVAL_SEC     = 900
_TRIGGER_CHECK_SEC    = 30    # check for manual trigger this often during the sleep


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        # Rotate: keep only the last LOG_MAX_LINES lines (check ~5% of the time)
        import random
        if random.random() < 0.05:
            lines = open(LOG_FILE, encoding="utf-8").readlines()
            if len(lines) > LOG_MAX_LINES:
                with open(LOG_FILE, "w", encoding="utf-8") as f:
                    f.writelines(lines[-LOG_MAX_LINES:])
    except Exception:
        pass


def send_telegram(token, chat_id, text, reply_markup=None):
    try:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
            timeout=10,
        )
    except Exception as e:
        log(f"Telegram send error: {e}")


def import_trades_and_notify(t_token, c_id):
    """Auto-import new trades from the latest IBKR XML report into Supabase.
    Sends a Telegram alert with an inline 'Open backlog' button if any new."""
    try:
        from supabase import create_client
        import glob as _glob
        import ibkr_trade_importer as _importer
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
        reports = sorted(_glob.glob("/app/ibkr_reports/ibkr_*.xml"))
        if not reports:
            log("Trade import skipped: no report files")
            return
        with open(reports[-1], "r", encoding="utf-8") as f:
            xml_text = f.read()
        result = _importer.import_new_trades(sb, xml_text)
        n_new = result.get("new_count", 0)
        log(f"Trade import: {n_new}/{result.get('total_in_xml', 0)} new trades inserted")
        if n_new > 0 and t_token and c_id:
            kb = {"inline_keyboard": [[{
                "text": f"📚 פתח סריקת יומן ({n_new} חדשים)",
                "callback_data": "open_backlog",
            }]]}
            send_telegram(
                t_token, c_id,
                f"🆕 נמצאו {n_new} טריידים חדשים בדוח.\n"
                f"לחץ למטה כדי להשלים פרטים (Setup, Quality, Stop):",
                reply_markup=kb,
            )
    except Exception as e:
        log(f"Trade importer error: {e}")


def load_sync_state():
    try:
        if os.path.exists(SYNC_STATE_FILE):
            with open(SYNC_STATE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_sync_state(state):
    try:
        with open(SYNC_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        log(f"State save error: {e}")


def _sleep_with_trigger_check(total_sec: int, check_sec: int = _TRIGGER_CHECK_SEC) -> bool:
    """
    Sleep for total_sec, waking every check_sec to check for a manual trigger file.
    Returns True if a manual trigger was detected (and should be processed immediately).
    """
    elapsed = 0
    while elapsed < total_sec:
        time.sleep(min(check_sec, total_sec - elapsed))
        elapsed += check_sec
        if os.path.exists(MANUAL_TRIGGER_FILE):
            return True
    return False


def _handle_manual_trigger(t_token, c_id):
    """Process a manual sync trigger written by the developer menu."""
    try:
        os.remove(MANUAL_TRIGGER_FILE)
    except Exception:
        pass
    log("Manual IBKR sync triggered via developer menu")
    result = run_ibkr_sync(log_fn=log)
    result["triggered_at"] = datetime.now().isoformat()
    try:
        with open(MANUAL_RESULT_FILE, "w") as f:
            json.dump(result, f)
    except Exception as e:
        log(f"Could not write manual result: {e}")
    if t_token and c_id:
        emoji = "✅" if result["status"] == "success" else (
            "🚨" if result["status"] == "fatal" else "⚠️"
        )
        send_telegram(t_token, c_id,
                      f"{emoji} IBKR Manual Sync: {result['message']}")
    # Auto-import new trades from the XML to Supabase (manual-trigger path)
    if result.get("status") == "success":
        import_trades_and_notify(t_token, c_id)


if __name__ == "__main__":
    log("Sentinel v18.0 Active")

    t_token = os.getenv("TELEGRAM_BOT_TOKEN")
    c_id    = os.getenv("TELEGRAM_ADMIN_ID")

    if t_token and c_id:
        send_telegram(t_token, c_id, "✅ Sentinel Bot מחובר\nסנכרון IBKR מתוזמן לחלון 07:00–11:00")
        log("Startup notification sent.")
    else:
        log("Telegram credentials not found in environment!")

    while True:
        _touch_heartbeat("sentinel_bot")
        # ── Manual trigger (developer menu) ────────────────────────────────────
        if os.path.exists(MANUAL_TRIGGER_FILE):
            _handle_manual_trigger(t_token, c_id)

        # ── Scheduled sync window ──────────────────────────────────────────────
        now   = datetime.now(ISRAEL_TZ)
        today = now.strftime("%Y-%m-%d")
        state = load_sync_state()

        already_synced     = state.get("sync_date") == today
        fail_date_match    = state.get("fail_date") == today
        fail_count_today   = state.get("fail_count", 0) if fail_date_match else 0
        notified_today     = state.get("notified_date") == today
        last_attempt_hour  = state.get("last_attempt_hour", -1) if fail_date_match else -1
        in_sync_window     = SYNC_START_HOUR <= now.hour < SYNC_END_HOUR
        tried_this_hour    = now.hour == last_attempt_hour

        if already_synced:
            log(f"Already synced today ({today}). Sleeping until next cycle.")

        elif not in_sync_window:
            log(f"Outside sync window ({SYNC_START_HOUR}:00–{SYNC_END_HOUR}:00). "
                f"Current hour: {now.hour}:xx. Waiting.")

        elif fail_count_today >= MAX_ATTEMPTS_PER_DAY:
            if not notified_today:
                log("Max attempts reached. Sending Telegram alert.")
                if t_token and c_id:
                    send_telegram(
                        t_token, c_id,
                        f"⚠️ Sentinel: לא התקבל דוח IBKR היום ({today})\n"
                        f"בוצעו {MAX_ATTEMPTS_PER_DAY} ניסיונות כושלים.\n"
                        "בדוק את ה-token ואת חיבור ה-API.",
                    )
                state["notified_date"] = today
                save_sync_state(state)
            else:
                log("Max attempts reached and user already notified. No further attempts today.")

        elif tried_this_hour:
            log(f"Already attempted sync at hour {now.hour}. Waiting for next hour.")

        else:
            attempt_num = fail_count_today + 1
            log(f"Attempting IBKR sync (attempt {attempt_num}/{MAX_ATTEMPTS_PER_DAY})…")
            result = run_ibkr_sync(log_fn=log)
            state["last_attempt_hour"] = now.hour

            status  = result["status"]
            code    = result["code"]
            message = result["message"]
            code_str = f" (קוד שגיאה: {code})" if code and code > 0 else ""

            if status == "success":
                state["sync_date"]  = today
                state["fail_count"] = 0
                save_sync_state(state)
                log("Sync successful!")
                if t_token and c_id:
                    send_telegram(t_token, c_id,
                                  f"✅ דוח IBKR התקבל בהצלחה ({today})\n{message}")
                # Auto-import new trades from the XML to Supabase
                import_trades_and_notify(t_token, c_id)

            elif status == "fatal":
                state["fail_date"]      = today
                state["fail_count"]     = MAX_ATTEMPTS_PER_DAY
                state["notified_date"]  = today
                save_sync_state(state)
                log(f"Fatal sync error — no further retries today. {message}")
                if t_token and c_id:
                    send_telegram(
                        t_token, c_id,
                        f"🚨 Sentinel: שגיאה חמורה בסנכרון IBKR ({today})\n"
                        f"סוג: קונפיגורציה/הרשאה{code_str}\n"
                        f"פרטים: {message}\n"
                        "אין ניסיונות נוספים היום. בדוק token, Query ID והרשאות IP.",
                    )

            elif status == "rate_limit":
                log(f"Rate limit hit{code_str}. Not counting as failed attempt.")
                save_sync_state(state)

            else:  # temporary
                state["fail_date"]  = today
                state["fail_count"] = fail_count_today + 1
                save_sync_state(state)
                log(f"Sync failed (temporary). Attempt {state['fail_count']}/{MAX_ATTEMPTS_PER_DAY}. {message}")
                if t_token and c_id:
                    send_telegram(
                        t_token, c_id,
                        f"⚠️ ניסיון סנכרון {state['fail_count']}/{MAX_ATTEMPTS_PER_DAY} נכשל "
                        f"({today} {now.hour:02d}:xx)\n"
                        f"סוג: זמני{code_str}\n"
                        f"סיבה: {message}\n"
                        "אנסה שוב בשעה הבאה.",
                    )

        # ── Sleep — wake early if developer menu writes a trigger ──────────────
        triggered = _sleep_with_trigger_check(LOOP_INTERVAL_SEC)
        if triggered:
            _handle_manual_trigger(t_token, c_id)
