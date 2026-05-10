import os
import json
import time
import glob as file_glob
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

REPORTS_DIR = "/app/ibkr_reports"
SYNC_STATE_FILE = "/app/ibkr_sync_state.json"

# סנכרון מתחיל ב-07:00 ומפסיק לנסות אחרי 11:00 (שעון ישראל, השרת ב-Asia/Jerusalem)
SYNC_START_HOUR = 7
SYNC_END_HOUR = 11
MAX_ATTEMPTS_PER_DAY = 3   # אחרי 3 כשלונות → התראת טלגרם
REPORTS_TO_KEEP = 3        # שומר 3 דוחות XML אחרונים
LOOP_INTERVAL_SEC = 900    # בדיקה כל 15 דקות


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


def send_telegram(token, chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        log(f"Telegram send error: {e}")


def update_nav_locally(val):
    try:
        path = "/app/sentinel_config.json"
        data = {"total_deposited": 7500.0, "risk_pct_input": 0.5}
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
        data["nav"] = float(val)
        with open(path, "w") as f:
            json.dump(data, f)
        log(f"NAV Updated: ${data['nav']}")
    except Exception as e:
        log(f"NAV Error: {e}")


def save_report_xml(xml_text):
    """שומר דוח XML גולמי. מחזיק רק REPORTS_TO_KEEP קבצים אחרונים."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filepath = os.path.join(REPORTS_DIR, f"ibkr_{ts}.xml")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(xml_text)
    log(f"Report saved: {filepath}")

    all_reports = sorted(file_glob.glob(os.path.join(REPORTS_DIR, "ibkr_*.xml")))
    while len(all_reports) > REPORTS_TO_KEEP:
        old = all_reports.pop(0)
        os.remove(old)
        log(f"Old report removed: {os.path.basename(old)}")


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


def run_ibkr_sync():
    log("Sync Cycle Started")
    token = os.getenv("IBKR_TOKEN")
    query_id = os.getenv("IBKR_QUERY_ID", "1501352")
    base_url = "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"

    try:
        res = requests.get(f"{base_url}?t={token}&q={query_id}&v=3", timeout=30)
        root = ET.fromstring(res.text)
        code_elem = root.find(".//code")
        if code_elem is None:
            log(f"IBKR Error Response: {res.text[:500]}")
            return False

        ref_code = code_elem.text
        log(f"Code: {ref_code}. Waiting 15s...")
        time.sleep(15)

        fetch_url = "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"
        report_res = requests.get(f"{fetch_url}?q={ref_code}&t={token}&v=3", timeout=60)

        # שומר את ה-XML לפני הפרסור — לצורך דיבאג ובדיקות
        save_report_xml(report_res.text)

        report_root = ET.fromstring(report_res.text)

        nav_node = report_root.find(".//ChangeInNAV")
        if nav_node is not None:
            v = nav_node.get("endingValue")
            if v:
                update_nav_locally(v)

        trades = report_root.findall(".//Trade")
        log(f"Found {len(trades)} trades.")
        return True

    except Exception as e:
        log(f"Sync Error: {e}")
        return False


if __name__ == "__main__":
    log("Sentinel v16.0 Active")

    t_token = os.getenv("TELEGRAM_BOT_TOKEN")
    c_id = os.getenv("TELEGRAM_ADMIN_ID")

    if t_token and c_id:
        send_telegram(t_token, c_id, "✅ Sentinel Bot מחובר\nסנכרון IBKR מתוזמן לחלון 07:00–11:00")
        log("Startup notification sent.")
    else:
        log("Telegram credentials not found in environment!")

    while True:
        now = datetime.now(ISRAEL_TZ)
        today = now.strftime("%Y-%m-%d")
        state = load_sync_state()

        already_synced = state.get("sync_date") == today
        fail_date_match = state.get("fail_date") == today
        fail_count_today = state.get("fail_count", 0) if fail_date_match else 0
        notified_today = state.get("notified_date") == today
        # last_attempt_hour מאפשר ניסיון אחד בלבד לכל שעה
        last_attempt_hour = state.get("last_attempt_hour", -1) if fail_date_match else -1
        in_sync_window = SYNC_START_HOUR <= now.hour < SYNC_END_HOUR
        tried_this_hour = now.hour == last_attempt_hour

        if already_synced:
            log(f"Already synced today ({today}). Sleeping until next cycle.")

        elif not in_sync_window:
            log(f"Outside sync window ({SYNC_START_HOUR}:00–{SYNC_END_HOUR}:00). Current hour: {now.hour}:xx. Waiting.")

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
            log(f"Attempting IBKR sync (attempt {attempt_num}/{MAX_ATTEMPTS_PER_DAY})...")
            success = run_ibkr_sync()
            state["last_attempt_hour"] = now.hour

            if success:
                state["sync_date"] = today
                state["fail_count"] = 0
                save_sync_state(state)
                log("Sync successful!")
                if t_token and c_id:
                    send_telegram(t_token, c_id, f"✅ דוח IBKR התקבל בהצלחה ({today})")
            else:
                state["fail_date"] = today
                state["fail_count"] = fail_count_today + 1
                save_sync_state(state)
                log(f"Sync failed. Attempt {state['fail_count']}/{MAX_ATTEMPTS_PER_DAY}.")
                if t_token and c_id:
                    send_telegram(
                        t_token, c_id,
                        f"⚠️ ניסיון סנכרון {state['fail_count']}/{MAX_ATTEMPTS_PER_DAY} נכשל ({today} {now.hour:02d}:xx)\n"
                        "אנסה שוב בשעה הבאה.",
                    )

        time.sleep(LOOP_INTERVAL_SEC)
