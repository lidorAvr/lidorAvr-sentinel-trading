import os
import requests
import time
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

load_dotenv('/home/orangepi/sentinel_trading/.env')
IBKR_TOKEN = os.getenv("IBKR_TOKEN")
IBKR_QUERY_ID = os.getenv("IBKR_QUERY_ID")

print("⏳ מושך את הדו\"ח מאינטראקטיב כדי להציג את הטריידים של החודש...")
send_url = "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
res = requests.get(send_url, params={"t": IBKR_TOKEN, "q": IBKR_QUERY_ID, "v": "3"}, timeout=30)
root = ET.fromstring(res.text)

ref_code_elem = root.find(".//ReferenceCode")
if ref_code_elem is None:
    print("⚠️ שגיאה במשיכה. שרת עמוס?")
    exit()

ref_code = ref_code_elem.text
time.sleep(15)

url_get = "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"
res_data = requests.get(url_get, params={"q": ref_code, "t": IBKR_TOKEN, "v": "3"}, timeout=30)

report_root = ET.fromstring(res_data.text)
trades = report_root.findall(".//Trade")

print(f"\n✅ מצאתי {len(trades)} טריידים בדו\"ח!")
print("-" * 40)
for t in trades:
    sym = t.get('symbol', 'N/A')
    action = t.get('buySell', 'N/A')
    date = t.get('tradeDate', 'N/A')
    qty = t.get('quantity', 'N/A')
    price = t.get('tradePrice', 'N/A')
    print(f"📅 [{date}] | פעולה: {action} | כמות: {qty} | מניה: {sym} | מחיר: {price}$")
print("-" * 40)

