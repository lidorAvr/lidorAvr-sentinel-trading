import os
import json
import time
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime

# השתקת אזהרות פנדס
pd.options.mode.chained_assignment = None

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def update_nav_locally(val):
    try:
        path = '/app/sentinel_config.json'
        data = {"total_deposited": 7500.0, "risk_pct_input": 0.5}
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
        data['nav'] = float(val)
        with open(path, 'w') as f:
            json.dump(data, f)
        log(f"💾 NAV Updated: ${data['nav']}")
    except Exception as e:
        log(f"🚨 NAV Error: {e}")

def run_ibkr_sync():
    log("🔍 Sync Cycle Started")
    token = os.getenv("IBKR_TOKEN")
    query_id = os.getenv("IBKR_QUERY_ID", "1501352")
    base_url = "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"

    try:
        res = requests.get(f"{base_url}?t={token}&q={query_id}&v=3")
        root = ET.fromstring(res.text)
        code_elem = root.find(".//code")
        if code_elem is None:
            log(f"🚨 IBKR Error Response: {res.text}")
            return False

        ref_code = code_elem.text
        log(f"✅ Code: {ref_code}. Waiting 15s...")
        time.sleep(15)

        fetch_url = "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"
        report_res = requests.get(f"{fetch_url}?q={ref_code}&t={token}&v=3")
        report_root = ET.fromstring(report_res.text)

        nav_node = report_root.find(".//ChangeInNAV")
        if nav_node is not None:
            v = nav_node.get('endingValue')
            if v: update_nav_locally(v)

        trades = report_root.findall(".//Trade")
        log(f"✅ Found {len(trades)} trades.")
        return True
    except Exception as e:
        log(f"🚨 Sync Error: {e}")
        return False

if __name__ == "__main__":
    log("🛡️ Sentinel v15.0 Active")

    # הודעת התעוררות עם השמות הנכונים מה-env שלך
    try:
        t_token = os.getenv("TELEGRAM_BOT_TOKEN") # עודכן
        c_id = os.getenv("TELEGRAM_ADMIN_ID")     # עודכן

        if t_token and c_id:
            resp = requests.post(f"https://api.telegram.org/bot{t_token}/sendMessage", 
                          json={"chat_id": c_id, "text": "✅ Sentinel Bot מחובר (סנכרון יומי ב-06:00)"})
            if resp.status_code == 200:
                log("✅ הודעת התעוררות נשלחה לטלגרם!")
            else:
                log(f"🚨 Telegram API Error {resp.status_code}: {resp.text}")
        else:
            log("🚨 Telegram credentials not found in environment!")
    except Exception as e:
        log(f"🚨 Telegram Exception: {e}")

    while True:
        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d")

        if now.hour >= 6:
            sync_file = "/app/last_sync_date.txt"
            last_sync = ""
            if os.path.exists(sync_file):
                with open(sync_file, 'r') as f:
                    last_sync = f.read().strip()

            if last_sync != current_date:
                log(f"⏰ Starting daily sync for {current_date}...")
                if run_ibkr_sync():
                    with open(sync_file, 'w') as f:
                        f.write(current_date)
                    log(f"✅ Sync done for today.")

        time.sleep(900)
