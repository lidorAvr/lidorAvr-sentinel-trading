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

SYNC_START_HOUR = 7
SYNC_END_HOUR = 11
MAX_ATTEMPTS_PER_DAY = 5     # raised from 3 — one attempt per hour 07-11
REPORTS_TO_KEEP = 3
LOOP_INTERVAL_SEC = 900

# IBKR Flex Query error classification.
# Keys are integer error codes. Values: (class, Hebrew description).
# class:
#   "temporary"  — report not ready yet, retry next hour
#   "fatal"      — config/auth problem, do not retry today, alert immediately
#   "rate_limit" — too many requests, log only, do not count as attempt
IBKR_ERROR_CLASSES = {
    1001: ("temporary",  "הדוח לא נוצר כרגע — ניסיון מאוחר יותר"),
    1004: ("temporary",  "הדוח לא שלם עדיין"),
    1005: ("temporary",  "נתוני Settlement עדיין לא מוכנים"),
    1006: ("temporary",  "נתוני FIFO P/L עדיין לא מוכנים"),
    1007: ("temporary",  "נתוני MTM P/L עדיין לא מוכנים"),
    1008: ("temporary",  "נתוני MTM ו-FIFO עדיין לא מוכנים"),
    1009: ("temporary",  "עומס בשרתי IBKR"),
    1018: ("rate_limit", "יותר מדי בקשות — Rate Limit"),
    1019: ("temporary",  "הדוח עדיין בתהליך יצירה"),
    1021: ("temporary",  "לא ניתן למשוך את הדוח כרגע"),
    1012: ("fatal",      "Token פג תוקף"),
    1013: ("fatal",      "הגבלת IP — Token לא מורשה מכתובת זו"),
    1014: ("fatal",      "Query ID לא תקין"),
    1015: ("fatal",      "Token לא תקין"),
    1016: ("fatal",      "Account לא תקין"),
    1017: ("fatal",      "Reference Code לא תקין"),
    1020: ("fatal",      "בקשה לא תקינה או לא ניתנת לאימות"),
}


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
        data["nav_updated_at"] = datetime.now().isoformat()
        with open(path, "w") as f:
            json.dump(data, f)
        log(f"NAV Updated: ${data['nav']}")
    except Exception as e:
        log(f"NAV Error: {e}")


def save_report_xml(xml_text):
    """Save raw XML report. Keeps only the last REPORTS_TO_KEEP files."""
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


def parse_flex_error(xml_text):
    """
    Parse IBKR Flex API XML for error codes.
    Returns {"code": int, "class": str, "description": str} if error found,
    or None if the response looks like a success.
    """
    try:
        root = ET.fromstring(xml_text)
        error_elem = root.find(".//ErrorCode")
        if error_elem is not None:
            try:
                code = int(error_elem.text.strip())
            except (ValueError, AttributeError):
                code = -1
            error_class, description = IBKR_ERROR_CLASSES.get(
                code, ("temporary", f"קוד שגיאה לא מוכר: {code}")
            )
            return {"code": code, "class": error_class, "description": description}
        # No error code found — treat as success
        return None
    except ET.ParseError as e:
        return {"code": -1, "class": "temporary", "description": f"XML parse error: {e}"}
    except Exception as e:
        return {"code": -1, "class": "temporary", "description": str(e)}


def get_statement_with_retry(ref_code, token, max_retries=3, wait_sec=60):
    """
    Fetch GetStatement using the same ReferenceCode, retrying up to max_retries times.
    Only one SendRequest was issued — we reuse the same ref_code here.
    Returns (xml_text, None) on success, or (None, error_info) on failure.
    error_info = {"code": int, "class": str, "description": str}
    """
    fetch_url = (
        "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"
    )
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            res = requests.get(f"{fetch_url}?q={ref_code}&t={token}&v=3", timeout=60)
            error = parse_flex_error(res.text)
            if error is None:
                return res.text, None
            last_error = error
            log(f"GetStatement attempt {attempt}/{max_retries}: code={error['code']} ({error['class']}) — {error['description']}")
            # Fatal errors: no point retrying
            if error["class"] == "fatal":
                return None, error
            if attempt < max_retries:
                log(f"Waiting {wait_sec}s before retry...")
                time.sleep(wait_sec)
        except Exception as e:
            last_error = {"code": -1, "class": "temporary", "description": str(e)}
            log(f"GetStatement network error (attempt {attempt}): {e}")
            if attempt < max_retries:
                log(f"Waiting {wait_sec}s before retry...")
                time.sleep(wait_sec)
    return None, last_error


def run_ibkr_sync():
    """
    Run one IBKR Flex Query sync attempt.
    Returns {"status": "success"|"temporary"|"fatal"|"rate_limit", "code": int|None, "message": str}
    """
    log("Sync Cycle Started")
    token = os.getenv("IBKR_TOKEN")
    query_id = os.getenv("IBKR_QUERY_ID", "1501352")
    base_url = (
        "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
    )

    try:
        # Step 1: SendRequest (one per hourly attempt — never resend within same attempt)
        res = requests.get(f"{base_url}?t={token}&q={query_id}&v=3", timeout=30)

        send_error = parse_flex_error(res.text)
        if send_error:
            log(f"SendRequest error: code={send_error['code']} ({send_error['class']}) — {send_error['description']}")
            return {
                "status": send_error["class"],
                "code": send_error["code"],
                "message": send_error["description"],
            }

        root = ET.fromstring(res.text)
        code_elem = root.find(".//code")
        if code_elem is None:
            log(f"SendRequest: no reference code in response: {res.text[:300]}")
            return {"status": "temporary", "code": 0, "message": "חסר Reference Code בתגובה מ-IBKR"}

        ref_code = code_elem.text
        log(f"SendRequest OK. ReferenceCode: {ref_code}. Waiting 15s before GetStatement...")
        time.sleep(15)

        # Step 2: GetStatement with retry (up to 3x, 60s apart, same ref_code)
        xml_text, error = get_statement_with_retry(ref_code, token)
        if error:
            log(f"GetStatement failed after retries: code={error['code']} ({error['class']}) — {error['description']}")
            return {
                "status": error["class"],
                "code": error["code"],
                "message": error["description"],
            }

        # Step 3: Parse and persist the report
        save_report_xml(xml_text)
        report_root = ET.fromstring(xml_text)

        nav_node = report_root.find(".//ChangeInNAV")
        if nav_node is not None:
            v = nav_node.get("endingValue")
            if v:
                update_nav_locally(v)

        trades = report_root.findall(".//Trade")
        log(f"Sync successful. Found {len(trades)} trades.")
        return {"status": "success", "code": None, "message": f"{len(trades)} trades synced"}

    except Exception as e:
        log(f"Sync Error: {e}")
        return {"status": "temporary", "code": -1, "message": str(e)}


if __name__ == "__main__":
    log("Sentinel v17.0 Active")

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
            result = run_ibkr_sync()
            state["last_attempt_hour"] = now.hour

            status = result["status"]
            code = result["code"]
            message = result["message"]
            code_str = f" (קוד שגיאה: {code})" if code and code > 0 else ""

            if status == "success":
                state["sync_date"] = today
                state["fail_count"] = 0
                save_sync_state(state)
                log("Sync successful!")
                if t_token and c_id:
                    send_telegram(t_token, c_id, f"✅ דוח IBKR התקבל בהצלחה ({today})\n{message}")

            elif status == "fatal":
                # Fatal config/auth error — no point retrying today, alert immediately
                state["fail_date"] = today
                state["fail_count"] = MAX_ATTEMPTS_PER_DAY  # skip all remaining attempts
                state["notified_date"] = today
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
                # Rate limit — do not count as attempt, just log
                log(f"Rate limit hit{code_str}. Not counting as failed attempt.")
                # Do NOT update fail_count or last_attempt_hour — allows retry in same hour
                # (save state without changes to maintain other fields)
                save_sync_state(state)

            else:  # temporary
                state["fail_date"] = today
                state["fail_count"] = fail_count_today + 1
                save_sync_state(state)
                log(f"Sync failed (temporary). Attempt {state['fail_count']}/{MAX_ATTEMPTS_PER_DAY}. {message}")
                if t_token and c_id:
                    send_telegram(
                        t_token, c_id,
                        f"⚠️ ניסיון סנכרון {state['fail_count']}/{MAX_ATTEMPTS_PER_DAY} נכשל ({today} {now.hour:02d}:xx)\n"
                        f"סוג: זמני{code_str}\n"
                        f"סיבה: {message}\n"
                        "אנסה שוב בשעה הבאה.",
                    )

        time.sleep(LOOP_INTERVAL_SEC)
